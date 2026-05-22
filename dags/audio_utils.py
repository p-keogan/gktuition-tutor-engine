"""
audio_utils.py — Audio chunking helper for the ingestion DAG.

Used by `download_audio` as a fallback when the existing 32kbps recompression
still leaves an audio file over Whisper's 25 MB hard limit (i.e. very long
videos — roughly 100+ minutes at the current recompression settings).

The chunking pipeline:
  1. Split the audio into ~15-minute segments via ffmpeg.
  2. Write a manifest JSON listing each chunk's path and its
     `offset_seconds` (so the transcribe step can stitch segment timestamps
     back to the original recording's timeline).
  3. Return the manifest path; the downstream `transcribe` task detects the
     `.json` extension and routes through the chunked-transcription path
     in `transcribe_worker.py`.

Companion files:
  - dags/ingestion_dag.py        — calls `chunk_audio_for_whisper()` from download_audio
  - scripts/transcribe_worker.py — reads the manifest, stitches the result
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Dict


# Chunk size for the segment muxer. 15 minutes at the DAG's current 32 kbps
# mono recompression target is ~3.6 MB — well under Whisper's 25 MB ceiling.
CHUNK_DURATION_SECONDS: int = 15 * 60


def chunk_audio_for_whisper(audio_path: Path, slug: str, audio_dir: Path) -> Path:
    """Split `audio_path` into ~15-min chunks and write a manifest file.

    Chunks land at `audio_dir / f"{slug}-chunks" / "chunk-NNN.mp3"`. The
    manifest is written to `audio_dir / f"{slug}.chunks.json"` and contains
    a JSON list of `{path, offset_seconds}` dicts.

    Removes the original full-length `audio_path` after chunking succeeds.
    Returns the manifest path.
    """
    chunk_dir = audio_dir / f"{slug}-chunks"
    chunk_dir.mkdir(exist_ok=True)
    chunk_pattern = str(chunk_dir / "chunk-%03d.mp3")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-f", "segment",
                "-segment_time", str(CHUNK_DURATION_SECONDS),
                "-c", "copy",        # no re-encoding — already at target bitrate
                chunk_pattern,
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"ffmpeg chunking failed for {audio_path}:\n"
            f"  stderr: {exc.stderr.decode(errors='replace')[:2000]}"
        ) from exc

    chunks = sorted(chunk_dir.glob("chunk-*.mp3"))
    if not chunks:
        raise RuntimeError(
            f"Chunking produced no output files in {chunk_dir}. "
            f"Verify ffmpeg installation and that {audio_path} is a valid mp3."
        )

    manifest: List[Dict] = [
        {
            "path": str(chunk),
            "offset_seconds": i * CHUNK_DURATION_SECONDS,
        }
        for i, chunk in enumerate(chunks)
    ]
    manifest_path = audio_dir / f"{slug}.chunks.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Original full-length file is no longer needed; the chunks fully cover it.
    audio_path.unlink(missing_ok=True)

    print(
        f"Chunked {slug} into {len(chunks)} pieces "
        f"(manifest: {manifest_path.name})"
    )
    return manifest_path
