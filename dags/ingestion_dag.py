"""
ingestion_dag.py — GKTuition AI Tutor ingestion pipeline.

Reads a URL list from gktuition-prod/inputs/corpus_v1.txt (one line per
video: "<youtube_url> <slug>"), runs the ingestion pipeline for each
video in parallel via dynamic task mapping.

Phase 1: download_audio only.
Phase 2: adds transcribe + postprocess + store.

Companion design doc: docs/design/ingestion-dag.md
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

from airflow.decorators import dag, task


# ── Paths ─────────────────────────────────────────────────────────────────
HOME = Path.home()
CORPUS_FILE = HOME / "code" / "gktuition-prod" / "inputs" / "corpus_v1.txt"
DATA_ROOT = HOME / "code" / "career-transition-2026" / "data"
AUDIO_DIR = DATA_ROOT / "audio"
TRANSCRIPTS_RAW_DIR = DATA_ROOT / "transcripts" / "raw"
WORKER_SCRIPT_TRANSCRIBE = (
    HOME / "code" / "gktuition-tutor-engine" / "scripts" / "transcribe_worker.py"
)
WORKER_PYTHON = (
    HOME / "code" / "career-transition-2026" / ".venv-py312" / "bin" / "python"
)


# Whisper API hard limit is 25 MB. Recompress before sending if >24 MB.
WHISPER_SIZE_LIMIT_MB = 24


class VideoEntry(TypedDict):
    youtube_url: str
    slug: str


# ── Tasks ─────────────────────────────────────────────────────────────────
@task
def read_corpus_list() -> list[VideoEntry]:
    """Parse a '<youtube_url> <slug>' newline-separated batch file."""
    entries: list[VideoEntry] = []
    for raw_line in CORPUS_FILE.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"Malformed line in {CORPUS_FILE}: {raw_line!r}")
        entries.append({"youtube_url": parts[0], "slug": parts[1]})
    if not entries:
        raise ValueError(f"No video entries found in {CORPUS_FILE}")
    print(f"Read {len(entries)} entries from {CORPUS_FILE}")
    return entries


@task(
    retries=1,
    retry_delay=timedelta(minutes=2),
    execution_timeout=timedelta(minutes=10),
)
def download_audio(entry: VideoEntry) -> str:
    """Pull audio from YouTube via yt-dlp; recompress if >24 MB.

    Idempotent: skips download if data/audio/<slug>.mp3 already exists.
    Returns the local audio file path.
    """
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    slug = entry["slug"]
    audio_path = AUDIO_DIR / f"{slug}.mp3"

    if audio_path.exists():
        print(f"[idempotency] {audio_path} already exists; skipping download")
        return str(audio_path)

    output_template = str(AUDIO_DIR / f"{slug}.%(ext)s")
    subprocess.run(
        [
            "yt-dlp", "-x", "--audio-format", "mp3",
            "-o", output_template, entry["youtube_url"],
        ],
        check=True,
    )

    # Recompress if oversized for the Whisper API
    size_mb = audio_path.stat().st_size / (1024 * 1024)
    if size_mb > WHISPER_SIZE_LIMIT_MB:
        print(f"Audio is {size_mb:.1f} MB > {WHISPER_SIZE_LIMIT_MB} MB; recompressing")
        compressed = audio_path.with_name(f"{slug}.compressed.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(audio_path),
                "-ac", "1", "-ar", "16000", "-b:a", "32k", str(compressed),
            ],
            check=True,
        )
        compressed.replace(audio_path)
        print(f"Recompressed to {audio_path.stat().st_size / (1024 * 1024):.1f} MB")

    return str(audio_path)

@task(
    retries=1,
    retry_delay=timedelta(minutes=2),
    execution_timeout=timedelta(minutes=15),
)
def transcribe(audio_path: str) -> str:
    """Transcribe audio via Whisper. Calls transcribe_worker.py as a subprocess
    so the openai SDK runs in a fresh Python interpreter — avoids macOS
    fork-safety + httpx-after-fork crashes that happen when openai is
    imported in Airflow's worker process.

    Idempotent: skips if data/transcripts/raw/<slug>.json already exists.
    Returns the local raw-JSON path.
    """
    audio = Path(audio_path)
    slug = audio.stem
    TRANSCRIPTS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = TRANSCRIPTS_RAW_DIR / f"{slug}.json"

    if raw_path.exists():
        print(f"[idempotency] {raw_path} already exists; skipping Whisper")
        return str(raw_path)

    print(f"Invoking transcribe worker for {slug}")
    subprocess.run(
        [
            str(WORKER_PYTHON),
            str(WORKER_SCRIPT_TRANSCRIBE),
            str(audio_path),
            str(raw_path),
        ],
        check=True,
    )
    return str(raw_path)

# ── DAG definition ────────────────────────────────────────────────────────
@dag(
    dag_id="ingestion_dag",
    description="GKTuition AI Tutor — YouTube → Whisper transcript ingestion",
    start_date=datetime(2026, 5, 14),
    schedule=None,             # manually triggered
    catchup=False,
    tags=["gktuition", "ingestion"],
    max_active_tasks=3,        # gentle on yt-dlp + Whisper API rate limits
)
def ingestion_dag():
    entries = read_corpus_list()
    audio_paths = download_audio.expand(entry=entries)
    transcribe.expand(audio_path=audio_paths)


ingestion_dag()