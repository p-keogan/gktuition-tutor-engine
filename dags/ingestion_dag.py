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
TRANSCRIPTS_CLEAN_DIR = DATA_ROOT / "transcripts" / "clean"
POSTPROCESSING_RULES = HOME / "code" / "career-transition-2026" / "tutorials" / "postprocessing-rules.md"
STORE_DIR = HOME / "code" / "gktuition-prod" / "transcripts" / "clean"


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

@task(
    retries=1,
    retry_delay=timedelta(minutes=1),
    execution_timeout=timedelta(minutes=2),
)
def postprocess(raw_path: str) -> str:
    """Convert Whisper raw JSON to timestamped markdown transcript.

    Output: data/transcripts/clean/<slug>.md
    Format: "**[MM:SS]** segment text" per Whisper segment.

    Idempotent: skips if clean file exists AND its mtime is newer than the
    postprocessing rules file. When new rules are added (rules-file mtime
    advances), the clean file is regenerated automatically — enabling
    overnight "I added a new rule, re-clean all transcripts" workflows.

    v1 scope: format conversion only. Rule application (Americanisation
    fixes, Cert-family variants, etc.) lands in v2.
    """
    import json

    raw = Path(raw_path)
    slug = raw.stem
    TRANSCRIPTS_CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    clean_path = TRANSCRIPTS_CLEAN_DIR / f"{slug}.md"

    # Idempotency: skip if clean file exists AND rules haven't changed since
    if clean_path.exists():
        rules_mtime = (
            POSTPROCESSING_RULES.stat().st_mtime
            if POSTPROCESSING_RULES.exists()
            else 0
        )
        if clean_path.stat().st_mtime > rules_mtime:
            print(f"[idempotency] {clean_path} is newer than rules; skipping")
            return str(clean_path)
        print(f"Rules file newer than clean file; regenerating")

    data = json.loads(raw.read_text())

    lines = [f"# Transcript: {slug}", ""]
    for segment in data["segments"]:
        mm, ss = divmod(int(segment["start"]), 60)
        text = segment["text"].strip()
        lines.append(f"**[{mm:02d}:{ss:02d}]** {text}")
        lines.append("")

    clean_path.write_text("\n".join(lines))
    print(f"Wrote {clean_path} ({clean_path.stat().st_size / 1024:.1f} KB)")
    return str(clean_path)


@task(
    retries=1,
    retry_delay=timedelta(minutes=1),
    execution_timeout=timedelta(minutes=1),
)
def store(clean_path: str) -> str:
    """Copy the cleaned transcript to the private gktuition-prod repo.

    Output: gktuition-prod/transcripts/clean/<slug>.md

    Idempotent: skips if the destination already exists. This intentionally
    preserves hand-corrections made directly in the private repo. To force
    a re-copy after a postprocess re-run, delete the destination first.
    """
    import shutil

    clean = Path(clean_path)
    slug = clean.stem
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = STORE_DIR / f"{slug}.md"

    if dest_path.exists():
        print(f"[idempotency] {dest_path} already exists; skipping copy "
              f"(preserves hand-corrections)")
        return str(dest_path)

    shutil.copy2(clean, dest_path)
    print(f"Copied to {dest_path}")
    return str(dest_path)

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
    raw_paths = transcribe.expand(audio_path=audio_paths)
    clean_paths = postprocess.expand(raw_path=raw_paths)
    store.expand(clean_path=clean_paths)


ingestion_dag()