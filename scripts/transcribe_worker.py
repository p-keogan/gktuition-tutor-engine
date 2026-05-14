#!/usr/bin/env python3
"""
transcribe_worker.py — Standalone Whisper transcription worker.

Called by the Airflow DAG via subprocess so the openai SDK runs in a fresh
Python interpreter, avoiding macOS fork-safety + httpx-after-fork crashes
that occur when openai is imported in an Airflow-forked task process.

Usage:
    python transcribe_worker.py <audio_path> <output_json_path>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openai import OpenAI


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: transcribe_worker.py <audio_path> <output_json_path>",
              file=sys.stderr)
        return 1

    audio_path = Path(sys.argv[1])
    raw_path = Path(sys.argv[2])

    if not audio_path.exists():
        print(f"Audio not found: {audio_path}", file=sys.stderr)
        return 2

    print(f"Calling Whisper for {audio_path.name} "
          f"({audio_path.stat().st_size / (1024 * 1024):.1f} MB)")

    client = OpenAI()
    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            file=f,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(json.dumps(response.model_dump(), indent=2))
    print(f"Wrote {raw_path} ({raw_path.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())