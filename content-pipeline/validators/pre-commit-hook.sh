#!/usr/bin/env bash
# ----------------------------------------------------------------------
# pre-commit-hook.sh — fail-fast YAML validator for tutorial edits
# ----------------------------------------------------------------------
# Runs `validators/yaml_frontmatter.py --staged` against the staged set
# of `.md` files. Rejects the commit if any tutorial fails the schema
# contract that downstream Snowflake loaders rely on.
#
# Install one of two ways:
#
#   (A) Symlink into the repo's hook directory (per-clone):
#         ln -s ../../content-pipeline/validators/pre-commit-hook.sh \
#               .git/hooks/pre-commit
#         chmod +x .git/hooks/pre-commit
#
#   (B) Repository-wide hooksPath (recommended; survives re-clones):
#         git config core.hooksPath content-pipeline/validators
#         # then rename / copy this file to be discoverable as
#         #   content-pipeline/validators/pre-commit
#         cp content-pipeline/validators/pre-commit-hook.sh \
#            content-pipeline/validators/pre-commit
#         chmod +x content-pipeline/validators/pre-commit
#
# To skip the hook in a true emergency:
#   git commit --no-verify
# ----------------------------------------------------------------------
set -euo pipefail

# Locate the validator. The hook can be invoked from anywhere git puts
# its hook context (typically the repo root). We resolve the path
# relative to *this file*, not relative to $PWD.
HOOK_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VALIDATOR="$HOOK_DIR/yaml_frontmatter.py"

if [[ ! -f "$VALIDATOR" ]]; then
    echo "❌ pre-commit: validator not found at $VALIDATOR" >&2
    echo "   Reinstall the hook per content-pipeline/validators/pre-commit-hook.sh" >&2
    exit 1
fi

# Pick a Python interpreter. Prefer python3, fall back to python.
PYTHON_BIN="${PYTHON:-}"
if [[ -z "$PYTHON_BIN" ]]; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN=python3
    elif command -v python >/dev/null 2>&1; then
        PYTHON_BIN=python
    else
        echo "❌ pre-commit: no python interpreter on PATH" >&2
        echo "   Export PYTHON=/path/to/python before committing." >&2
        exit 1
    fi
fi

# Run the validator against the staged set.
# Exit code 0 = pass; 1 = hard rule violation; 2 = invocation error.
if ! "$PYTHON_BIN" "$VALIDATOR" --staged; then
    rc=$?
    echo "" >&2
    echo "❌ pre-commit: YAML frontmatter validation failed." >&2
    echo "   Fix the diagnostics above and re-run \`git commit\`." >&2
    echo "" >&2
    echo "   To skip this hook in a true emergency (e.g. urgent hotfix):" >&2
    echo "      git commit --no-verify" >&2
    echo "" >&2
    exit "$rc"
fi

exit 0
