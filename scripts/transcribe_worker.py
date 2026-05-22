#!/usr/bin/env python3
"""
transcribe_worker.py — Standalone Whisper transcription worker.

Called by the Airflow DAG via subprocess so the openai SDK runs in a fresh
Python interpreter, avoiding macOS fork-safety + httpx-after-fork crashes
that occur when openai is imported in an Airflow-forked task process.

Two invocation styles are supported (both produce a single verbose_json
transcript at <output_json_path>):

  1. Single audio file (the common case, unchanged behaviour):
       python transcribe_worker.py <audio.mp3>          <output.json>

  2. Chunk manifest JSON (long videos that were split by audio_utils):
       python transcribe_worker.py <slug.chunks.json>   <output.json>

     The manifest is a JSON list of {path, offset_seconds} dicts. Each
     chunk is transcribed independently; segment timestamps are shifted
     by the chunk's `offset_seconds` before being concatenated, so the
     final stitched transcript has timestamps spanning the original
     (pre-chunking) recording.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Dict

from openai import OpenAI


def transcribe_one(client: OpenAI, audio_path: Path) -> dict:
    """Transcribe a single audio file via Whisper. Returns verbose_json dict."""
    print(
        f"Calling Whisper for {audio_path.name} "
        f"({audio_path.stat().st_size / (1024 * 1024):.1f} MB)"
    )
    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            file=f,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    return response.model_dump()


def stitch(per_chunk: List[Dict], manifest: List[Dict]) -> Dict:
    """Concatenate per-chunk Whisper results into one verbose_json transcript.

    Adjusts each segment's `start`/`end` by the chunk's `offset_seconds` so
    timestamps span the original (pre-chunking) recording.
    """
    text_parts: List[str] = []
    segments: List[Dict] = []
    language = None
    duration = 0.0

    for result, entry in zip(per_chunk, manifest):
        offset = entry["offset_seconds"]
        text_parts.append(result.get("text", "").strip())
        for seg in result.get("segments", []):
            seg["start"] = seg.get("start", 0) + offset
            seg["end"] = seg.get("end", 0) + offset
            segments.append(seg)
        if language is None:
            language = result.get("language")
        duration += result.get("duration", 0)

    return {
        "text": " ".join(p for p in text_parts if p),
        "segments": segments,
        "language": language or "en",
        "duration": duration,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: transcribe_worker.py <audio_path | manifest.json> <output_json_path>",
            file=sys.stderr,
        )
        return 1

    input_path = Path(sys.argv[1])
    raw_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Input not found: {input_path}", file=sys.stderr)
        return 2

    client = OpenAI()

    # Branch on extension: .json => manifest of chunks; else single audio file.
    if input_path.suffix == ".json":
        manifest = json.loads(input_path.read_text())
        if not isinstance(manifest, list) or not manifest:
            print(f"Manifest is empty or malformed: {input_path}", file=sys.stderr)
            return 3
        per_chunk = []
        for i, entry in enumerate(manifest, start=1):
            chunk_path = Path(entry["path"])
            if not chunk_path.exists():
                print(f"Manifest chunk missing: {chunk_path}", file=sys.stderr)
                return 4
            print(f"[chunk {i}/{len(manifest)}] offset={entry['offset_seconds']}s")
            per_chunk.append(transcribe_one(client, chunk_path))
        stitched = stitch(per_chunk, manifest)
    else:
        # Single audio file — preserves the original behaviour exactly.
        stitched = transcribe_one(client, input_path)

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(stitched, indent=2))
    print(f"Wrote {raw_path} ({raw_path.stat().st_size / 1024:.1f} KB, "
          f"{len(stitched.get('segments', []))} segments)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
