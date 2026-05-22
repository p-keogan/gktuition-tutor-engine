#!/usr/bin/env bash
#
# Push Fly.io secrets for the gktuition-tutor-api app from a local untracked
# file. Idempotent: re-running with no changes is a no-op (no new release).
#
# The source file is `~/.gktuition_secrets`, a `KEY=VALUE` per line shell-style
# file. Comments (#-prefixed) and blank lines are allowed. The file is never
# committed; it's the local-only source of truth.
#
# Required keys (script aborts if any are missing):
#
#   SF_USER, SF_PRIVATE_KEY_PATH, SF_ACCOUNT, SF_WAREHOUSE, SF_DATABASE
#   ANTHROPIC_API_KEY
#   WP_JWT_SECRET
#
# Optional keys (passed through if present):
#
#   TURNSTILE_SECRET_KEY
#   LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
#
# Idempotency
#
# After a successful push, the SHA-256 of the source file (with values, not
# names, hashed in canonical order) is recorded in `.fly/secrets-applied.sha256`.
# Re-running compares the current SHA against the recorded one. Same hash →
# no-op, no `fly secrets set` call, no machine restart. The `.fly/` directory
# is gitignored.
#
# Usage
#
#   ./scripts/setup_fly_secrets.sh                  # use ~/.gktuition_secrets
#   ./scripts/setup_fly_secrets.sh path/to/file     # use an alternative source
#   FLY_APP_NAME=other-app ./scripts/setup_fly_secrets.sh
#   FORCE=1 ./scripts/setup_fly_secrets.sh          # skip the idempotency check

set -euo pipefail

APP="${FLY_APP_NAME:-gktuition-tutor-api}"
SOURCE="${1:-${HOME}/.gktuition_secrets}"
STATE_DIR=".fly"
STATE_FILE="${STATE_DIR}/secrets-applied.sha256"

if [ ! -f "$SOURCE" ]; then
  cat >&2 <<EOF
error: ${SOURCE} not found.

Create it with one KEY=VALUE per line:

    SF_USER=GKTUITION_APP
    SF_ACCOUNT=xy12345.eu-west-1.aws
    SF_WAREHOUSE=WH_TUTOR
    SF_DATABASE=GKTUITION_TUTOR
    SF_PRIVATE_KEY_PATH=/Users/paul/.snowflake/gktuition_api_rsa.p8
    ANTHROPIC_API_KEY=sk-ant-...
    WP_JWT_SECRET=...

Then re-run this script.
EOF
  exit 1
fi

if ! command -v fly >/dev/null 2>&1; then
  echo "error: 'fly' CLI not found on PATH. Install from https://fly.io/docs/flyctl/" >&2
  exit 1
fi

REQUIRED=(SF_USER SF_PRIVATE_KEY_PATH SF_ACCOUNT SF_WAREHOUSE SF_DATABASE ANTHROPIC_API_KEY WP_JWT_SECRET)
OPTIONAL=(TURNSTILE_SECRET_KEY LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY LANGFUSE_HOST)

# ---------------------------------------------------------------------------
# 1. Parse the source file into a name-sorted KEY=VALUE list.
# ---------------------------------------------------------------------------

# Use Python for parsing — bash word-splitting on values containing '=' or
# spaces is too fragile to trust.
RAW_PAIRS=$(python3 - "$SOURCE" <<'PYEOF'
import os
import sys

path = sys.argv[1]
pairs: dict[str, str] = {}
with open(path) as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.lstrip().startswith("#"):
            continue
        if "=" not in line:
            print(f"warning: ignoring malformed line: {line!r}", file=sys.stderr)
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # Strip exactly one surrounding quote pair if present (so users can
        # write SECRET="value with spaces" without leaking the quotes).
        v = value.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
            v = v[1:-1]
        pairs[key] = v

for k in sorted(pairs):
    # Originally NUL-separated, but Bash 5.x's command substitution strips
    # NUL bytes from `$(...)` capture (with a warning), which caused the
    # entire concatenated payload to land in a single read-loop iteration
    # and parse as one giant key. Switch to newline-separated; values in
    # this file are simple shell-style KEY=VALUE and never contain a
    # literal newline, so this is safe. If a value ever needs to carry a
    # newline (unlikely), encode it base64 at write-time and decode in the
    # consumer.
    print(f"{k}={pairs[k]}")
PYEOF
)

# ---------------------------------------------------------------------------
# 2. Validate required keys are present.
# ---------------------------------------------------------------------------

declare -A PAIRS
while IFS= read -r kv; do
  [ -z "$kv" ] && continue
  k="${kv%%=*}"
  v="${kv#*=}"
  PAIRS[$k]="$v"
done < <(printf '%s\n' "$RAW_PAIRS")

missing=()
for k in "${REQUIRED[@]}"; do
  if [ -z "${PAIRS[$k]+isset}" ] || [ -z "${PAIRS[$k]}" ]; then
    missing+=("$k")
  fi
done
if [ ${#missing[@]} -gt 0 ]; then
  echo "error: missing required keys: ${missing[*]}" >&2
  echo "(expected in ${SOURCE})" >&2
  exit 2
fi

# SF_PRIVATE_KEY_PATH is special: the value is a local path. Read the file
# contents and push the materialised key as SF_PRIVATE_KEY so the Fly app
# doesn't need a filesystem lookup at boot.
sf_key_path="${PAIRS[SF_PRIVATE_KEY_PATH]}"
sf_key_path="${sf_key_path/#~/$HOME}"
if [ ! -f "$sf_key_path" ]; then
  echo "error: SF_PRIVATE_KEY_PATH points to a file that doesn't exist: $sf_key_path" >&2
  exit 3
fi
SF_PRIVATE_KEY_CONTENT=$(cat "$sf_key_path")

# ---------------------------------------------------------------------------
# 3. Idempotency check — compute a stable digest of the final payload.
# ---------------------------------------------------------------------------

mkdir -p "$STATE_DIR"
if ! grep -qsxF "$STATE_DIR/" .gitignore 2>/dev/null; then
  # Append to .gitignore so the state directory is never committed.
  if [ -f .gitignore ]; then
    echo "${STATE_DIR}/" >> .gitignore
  else
    echo "${STATE_DIR}/" > .gitignore
  fi
fi

build_payload() {
  # Emit final KEY=VALUE pairs, name-sorted, NUL-terminated.
  for k in "${REQUIRED[@]}"; do
    if [ "$k" = "SF_PRIVATE_KEY_PATH" ]; then
      printf 'SF_PRIVATE_KEY=%s\0' "$SF_PRIVATE_KEY_CONTENT"
    else
      printf '%s=%s\0' "$k" "${PAIRS[$k]}"
    fi
  done
  for k in "${OPTIONAL[@]}"; do
    if [ -n "${PAIRS[$k]:-}" ]; then
      printf '%s=%s\0' "$k" "${PAIRS[$k]}"
    fi
  done
}

current_digest=$(build_payload | shasum -a 256 | awk '{print $1}')

if [ "${FORCE:-0}" != "1" ] && [ -f "$STATE_FILE" ]; then
  applied_digest=$(cat "$STATE_FILE")
  if [ "$applied_digest" = "$current_digest" ]; then
    echo "secrets unchanged (digest $current_digest) — no-op"
    exit 0
  fi
fi

# ---------------------------------------------------------------------------
# 4. Apply via `fly secrets set` — one batch call for atomicity.
# ---------------------------------------------------------------------------

echo "Applying secrets to Fly app: ${APP}"
echo "  required keys: ${REQUIRED[*]}"
present_optional=()
for k in "${OPTIONAL[@]}"; do
  [ -n "${PAIRS[$k]:-}" ] && present_optional+=("$k")
done
if [ ${#present_optional[@]} -gt 0 ]; then
  echo "  optional keys present: ${present_optional[*]}"
fi

# Use --stage so the secrets are committed in a single release rather than
# one per key. The deploy that follows will pick them up.
fly_args=(secrets set --app "$APP" --stage)
while IFS= read -r -d $'\0' kv; do
  fly_args+=("$kv")
done < <(build_payload)

fly "${fly_args[@]}"

# Trigger a deploy so the staged secrets take effect. `fly deploy` without
# `--image` rebuilds; we don't want that here. `fly machine update` would
# work but is per-machine. The simplest reliable path is `fly secrets deploy`.
fly secrets deploy --app "$APP"

# Record the digest only after a successful apply.
echo "$current_digest" > "$STATE_FILE"
echo "done. digest recorded at $STATE_FILE"
