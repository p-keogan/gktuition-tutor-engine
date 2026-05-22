#!/usr/bin/env bash
# manual_ingest.sh — Run the full DAG pipeline for ONE video, end-to-end, in
# the current shell. No airflow, no scheduler, no worker forking. Mirrors the
# four DAG tasks (download_audio → transcribe → postprocess → store) exactly,
# preserving the same idempotency rules so anything already on disk is reused.
#
# Usage:
#     ./manual_ingest.sh <youtube_url> <slug>
#
# Example:
#     ./manual_ingest.sh https://www.youtube.com/watch?v=RXliDSWfVIg \
#         lchl-p2-geometry-001-axioms-theorems-corollaries
#
# Requirements (same as the DAG):
#   - $OPENAI_API_KEY exported
#   - yt-dlp + ffmpeg on PATH
#   - The career-transition-2026 venv-py312 (for openai + audio_utils)
set -euo pipefail

if [ "$#" -ne 2 ]; then
  echo "Usage: $0 <youtube_url> <slug>" >&2
  exit 1
fi
URL="$1"
SLUG="$2"

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "ERROR: OPENAI_API_KEY is not set." >&2
  exit 2
fi

# ── Paths (mirror ingestion_dag.py exactly) ──────────────────────────────────
AUDIO_DIR="$HOME/code/career-transition-2026/data/audio"
RAW_DIR="$HOME/code/career-transition-2026/data/transcripts/raw"
CLEAN_DIR="$HOME/code/career-transition-2026/data/transcripts/clean"
STORE_DIR="$HOME/code/gktuition-prod/transcripts/clean"
DAGS_DIR="$HOME/code/gktuition-tutor-engine/dags"
WORKER="$HOME/code/gktuition-tutor-engine/scripts/transcribe_worker.py"
PYTHON="$HOME/code/career-transition-2026/.venv-py312/bin/python"

WHISPER_LIMIT_MB=24

mkdir -p "$AUDIO_DIR" "$RAW_DIR" "$CLEAN_DIR" "$STORE_DIR"

AUDIO="$AUDIO_DIR/$SLUG.mp3"

echo
echo "════════════════════════════════════════════════════════════════════"
echo "  manual_ingest:  $SLUG"
echo "════════════════════════════════════════════════════════════════════"

# ── Step 1 — download_audio ─────────────────────────────────────────────────
echo
echo "── [1/4] download_audio ────────────────────────────────────────────"
if [ -f "$AUDIO" ]; then
  echo "[idempotency] $AUDIO already exists; skipping yt-dlp"
else
  yt-dlp -x --audio-format mp3 -o "$AUDIO_DIR/$SLUG.%(ext)s" "$URL"
fi

size_mb() { python3 -c "import os,sys; print(os.path.getsize(sys.argv[1])/(1024*1024))" "$1"; }
SIZE=$(size_mb "$AUDIO")
printf "Audio size: %.1f MB\n" "$SIZE"

# Recompress if > 24 MB
if (( $(echo "$SIZE > $WHISPER_LIMIT_MB" | bc -l) )); then
  echo "Audio > ${WHISPER_LIMIT_MB} MB; recompressing to 32 kbps mono 16 kHz"
  COMPRESSED="$AUDIO_DIR/$SLUG.compressed.mp3"
  ffmpeg -y -i "$AUDIO" -ac 1 -ar 16000 -b:a 32k "$COMPRESSED" </dev/null
  mv "$COMPRESSED" "$AUDIO"
  SIZE=$(size_mb "$AUDIO")
  printf "After recompression: %.1f MB\n" "$SIZE"
fi

# Chunk fallback if STILL > 24 MB
INPUT_FOR_WHISPER="$AUDIO"
if (( $(echo "$SIZE > $WHISPER_LIMIT_MB" | bc -l) )); then
  echo "Still > ${WHISPER_LIMIT_MB} MB; chunking via audio_utils"
  MANIFEST=$("$PYTHON" - <<PYEOF
import sys
sys.path.insert(0, "$DAGS_DIR")
from pathlib import Path
from audio_utils import chunk_audio_for_whisper
m = chunk_audio_for_whisper(Path("$AUDIO"), "$SLUG", Path("$AUDIO_DIR"))
print(m)
PYEOF
)
  INPUT_FOR_WHISPER="$MANIFEST"
  echo "Manifest: $INPUT_FOR_WHISPER"
fi

# ── Step 2 — transcribe ─────────────────────────────────────────────────────
echo
echo "── [2/4] transcribe ────────────────────────────────────────────────"
RAW="$RAW_DIR/$SLUG.json"
if [ -f "$RAW" ]; then
  echo "[idempotency] $RAW already exists; skipping Whisper"
else
  "$PYTHON" "$WORKER" "$INPUT_FOR_WHISPER" "$RAW"
fi

# ── Step 3 — postprocess ────────────────────────────────────────────────────
echo
echo "── [3/4] postprocess ───────────────────────────────────────────────"
CLEAN="$CLEAN_DIR/$SLUG.md"
"$PYTHON" - <<PYEOF
import json
from pathlib import Path
slug = "$SLUG"
raw = Path("$RAW")
clean = Path("$CLEAN")
data = json.loads(raw.read_text())
lines = [f"# Transcript: {slug}", ""]
for segment in data["segments"]:
    mm, ss = divmod(int(segment["start"]), 60)
    text = segment["text"].strip()
    lines.append(f"**[{mm:02d}:{ss:02d}]** {text}")
    lines.append("")
clean.write_text("\n".join(lines))
print(f"Wrote {clean} ({clean.stat().st_size / 1024:.1f} KB, "
      f"{len(data['segments'])} segments)")
PYEOF

# ── Step 4 — store ──────────────────────────────────────────────────────────
echo
echo "── [4/4] store ─────────────────────────────────────────────────────"
DEST="$STORE_DIR/$SLUG.md"
if [ -f "$DEST" ]; then
  echo "[idempotency] $DEST already exists; skipping copy (preserves hand-corrections)"
else
  cp "$CLEAN" "$DEST"
  echo "Copied to $DEST"
fi

echo
echo "✓ DONE — $SLUG"
echo
