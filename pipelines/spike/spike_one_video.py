#!/usr/bin/env python3
"""
spike_one_video.py — end-to-end ingestion spike.

Pulls a single YouTube tutorial video, transcribes it with OpenAI Whisper,
and writes a timestamped markdown transcript. The "hello world" of the
GKTuition AI Tutor ingestion pipeline; the production version will
parallelise this across the full corpus via Airflow.

Usage:
    python spike_one_video.py <youtube_url> <slug>

Example:
    python spike_one_video.py \\
        "https://www.youtube.com/watch?v=xQ7lviqrdnM" \\
        jchl-algebra-011-factorising-5

Requirements:
    - yt-dlp and ffmpeg installed and on PATH (`brew install yt-dlp ffmpeg`)
    - OPENAI_API_KEY environment variable
    - openai>=1.0 in the Python environment
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from openai import OpenAI

AUDIO_DIR = Path("audio")
TRANSCRIPT_DIR = Path("transcripts")
# Whisper API hard limit is 25 MB. Recompress to mono / 16 kHz / 32 kbps
# before sending if we're above 24 MB. Whisper downsamples to 16 kHz mono
# internally anyway, so this is lossless from the model's perspective.
WHISPER_SIZE_LIMIT_MB = 24


def download_audio(url: str, slug: str) -> Path:
    """Pull audio from YouTube as mp3 via yt-dlp."""
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_template = str(AUDIO_DIR / f"{slug}.%(ext)s")
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "-o", output_template, url],
        check=True,
    )
    return AUDIO_DIR / f"{slug}.mp3"


def recompress_if_oversize(audio_path: Path) -> Path:
    """If the mp3 is above the Whisper limit, re-encode it down."""
    size_mb = audio_path.stat().st_size / (1024 * 1024)
    if size_mb <= WHISPER_SIZE_LIMIT_MB:
        return audio_path

    compressed = audio_path.with_name(f"{audio_path.stem}.compressed.mp3")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(audio_path),
            "-ac", "1", "-ar", "16000", "-b:a", "32k",
            str(compressed),
        ],
        check=True,
    )
    return compressed


def transcribe(audio_path: Path) -> dict:
    """Send audio to Whisper; return the verbose-JSON response as a dict."""
    client = OpenAI()
    with audio_path.open("rb") as f:
        response = client.audio.transcriptions.create(
            file=f,
            model="whisper-1",
            response_format="verbose_json",
            timestamp_granularities=["segment"],
        )
    return response.model_dump()


def write_transcript(result: dict, slug: str) -> Path:
    """Write a timestamped markdown transcript."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = TRANSCRIPT_DIR / f"{slug}.md"
    with output_path.open("w") as f:
        f.write(f"# Transcript: {slug}\n\n")
        for segment in result["segments"]:
            mm, ss = divmod(int(segment["start"]), 60)
            f.write(f"**[{mm:02d}:{ss:02d}]** {segment['text'].strip()}\n\n")
    return output_path


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python spike_one_video.py <youtube_url> <slug>")
    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY is not set.")

    url, slug = sys.argv[1], sys.argv[2]

    print(f"[1/3] Downloading audio for {slug}")
    audio = download_audio(url, slug)

    print(f"[2/3] Preparing audio (recompress if >{WHISPER_SIZE_LIMIT_MB} MB)")
    audio = recompress_if_oversize(audio)

    print("[3/3] Transcribing with Whisper")
    result = transcribe(audio)
    transcript_path = write_transcript(result, slug)

    print(f"Done: {transcript_path}")


if __name__ == "__main__":
    main()
