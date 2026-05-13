# pipelines/spike/

The end-to-end ingestion spike for the GKTuition AI Tutor. One Python file,
one YouTube video → one timestamped transcript. Proves the pipeline shape
before it gets parallelised into an Airflow DAG.

## What it does

```
YouTube URL  ──►  yt-dlp  ──►  mp3 audio  ──►  ffmpeg (if >24 MB)
                                                   │
                                                   ▼
                                          OpenAI Whisper API
                                                   │
                                                   ▼
                                  timestamped markdown transcript
```

## Run it

```bash
# One-time setup
brew install yt-dlp ffmpeg
pip install "openai>=1.0"
export OPENAI_API_KEY="sk-..."

# Run from this directory
python spike_one_video.py \
  "https://www.youtube.com/watch?v=xQ7lviqrdnM" \
  jchl-algebra-011-factorising-5
```

Output lands in `transcripts/<slug>.md`. Audio is cached in `audio/` and
gitignored.

## What's intentionally not here yet

- Parallelism — production will use Airflow with one DAG run per video
- Postprocessing rules — domain-specific text normalisation (handled later)
- The structured tutorial scaffold — generated downstream from the transcript
- Eval harness integration — separate concern

## Cost

A 10-minute video costs roughly $0.06 in Whisper. The full ~550-video
corpus, end-to-end, is in the ~$30 range.

## Sample output

See [`../../examples/sample-output-truncated.md`](../../examples/sample-output-truncated.md) for the first ~30 lines of a real run.
