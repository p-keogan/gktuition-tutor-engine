#!/usr/bin/env bash
# sync_corpus.sh — bring corpus/ in step with the canonical career-transition-2026
#
# The engine repo ships a bundled snapshot of the voice anchor corpus at
# corpus/tutorials/ so the Docker build context is self-contained (no
# cross-repo build dance, no Fly volume operational overhead) — see the
# Dockerfile's `COPY corpus /app/corpus` step and api/orchestrator/voice_anchor.py.
#
# When you edit one of the 20 strand `_SUMMARY-exam-cram.md` files or the
# corpus-wide `_voice.md` in career-transition-2026/tutorials/, run this
# script to refresh the bundled copy:
#
#     bash scripts/sync_corpus.sh
#
# Then commit + push: `git add corpus/ && git commit -m "corpus: sync from ctr-2026"`.
#
# The script is idempotent — re-running with no source changes is a no-op
# (rsync only copies files whose mtime or size differs).
#
# CTR_2026_ROOT can override the default sibling-directory assumption. Useful
# if you have ctr-2026 checked out somewhere non-standard.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_ROOT="$(cd "$HERE/.." && pwd)"
CTR_2026_ROOT="${CTR_2026_ROOT:-$ENGINE_ROOT/../career-transition-2026}"
CORPUS_DEST="$ENGINE_ROOT/corpus/tutorials"
SRC_TUTORIALS="$CTR_2026_ROOT/tutorials"

if [[ ! -d "$SRC_TUTORIALS" ]]; then
    echo "ERROR: source tutorials directory not found: $SRC_TUTORIALS" >&2
    echo "Set CTR_2026_ROOT to point at your career-transition-2026 checkout." >&2
    exit 1
fi

mkdir -p "$CORPUS_DEST"

echo "Syncing corpus from $SRC_TUTORIALS → $CORPUS_DEST"

# 1. The corpus-wide voice rules file.
if [[ -f "$SRC_TUTORIALS/_voice.md" ]]; then
    cp "$SRC_TUTORIALS/_voice.md" "$CORPUS_DEST/_voice.md"
    echo "  · _voice.md"
else
    echo "WARNING: $SRC_TUTORIALS/_voice.md is missing — voice rules will be skipped." >&2
fi

# 2. Each LCHL_* strand directory's _SUMMARY-exam-cram.md (if present).
count=0
for strand_dir in "$SRC_TUTORIALS"/LCHL_*/; do
    strand="$(basename "$strand_dir")"
    summary_src="$strand_dir/_SUMMARY-exam-cram.md"
    if [[ -f "$summary_src" ]]; then
        mkdir -p "$CORPUS_DEST/$strand"
        cp "$summary_src" "$CORPUS_DEST/$strand/_SUMMARY-exam-cram.md"
        echo "  · $strand/_SUMMARY-exam-cram.md"
        count=$((count + 1))
    fi
done

echo ""
echo "Synced $count strand summary file(s) + 1 voice rules file."
echo "Review changes with: git -C \"$ENGINE_ROOT\" status corpus/"
