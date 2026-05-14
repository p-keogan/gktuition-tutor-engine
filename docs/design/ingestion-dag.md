# Ingestion DAG — Design

> **Status:** Design committed; build starts DAY_22 (Sunday).
> **Orchestrator:** Apache Airflow 2.9, run locally in `standalone` mode.
> **Cost target:** ≤€2.50 per batch run (full corpus ≈ 2 batches).
> **Companion:** see ADR-001 (vector store), ADR-002 (cost firewall), ADR-003 (system architecture).

## (a) Inputs

**YouTube URL list:** maintained as a hand-curated batch file at `dags/inputs/corpus_v1.txt`. One entry per line, format `<youtube_url> <slug>`. Lives in the public repo — URLs are public-safe; slugs are public-safe. Spine-derived auto-generation is a Phase 2 nice-to-have; v1 stays manual because the file gives explicit control over which videos enter each batch run.

**Postprocessing rules:** loaded at task-execution time from `tutorials/postprocessing-rules.md` (public repo). Rules added between DAG runs apply automatically on the next run — no DAG redeploy needed.

**Run parameters (DAG conf):**
- `batch_file` (string, default `"dags/inputs/corpus_v1.txt"`) — path to URL list. Override for ad-hoc smaller batches.
- `single_video_url` + `single_video_slug` (both string, default null) — if set, process just this one video. For dev / smoke-testing.
- `force_repostprocess` (bool, default `false`) — when true, skip the postprocess idempotency check and re-clean every transcript. Used when a new postprocessing rule lands and you want it applied to existing transcripts.

## (b) Tasks

Four sequential tasks per video, written using Airflow's TaskFlow API (decorators) for type safety. Parallelised across the URL list via dynamic task mapping (Airflow 2.3+).

- **`download_audio`:** `yt-dlp` pulls audio as mp3 to `data/audio/<slug>.mp3`. If the resulting file is >24 MB, `ffmpeg` recompresses to mono / 16 kHz / 32 kbps before the next task (Whisper API has a 25 MB hard limit).
- **`transcribe`:** Whisper API call (`whisper-1` model, `verbose_json` response format with per-segment timestamps). Raw JSON to `data/transcripts/raw/<slug>.json`.
- **`postprocess`:** loads `tutorials/postprocessing-rules.md`, applies each rule to the raw transcript, emits cleaned markdown to `data/transcripts/clean/<slug>.md`.
- **`store`:** copies `data/transcripts/clean/<slug>.md` to `~/code/gktuition-prod/transcripts/<slug>.md`. **The public repo never sees a transcript file.** Only the run-stats summary log lands publicly.

## (c) Idempotency strategy — slug-based dedupe

Each task short-circuits if its output already exists, keeping re-runs cheap and recoverable from mid-batch crashes:

- **`download_audio`:** if `data/audio/<slug>.mp3` exists → skip. (Audio download is cheap but slow; skip wins us minutes per re-run.)
- **`transcribe`:** if `data/transcripts/raw/<slug>.json` exists → skip. **This is the load-bearing skip — Whisper costs real money.**
- **`postprocess`:** by default, if `data/transcripts/clean/<slug>.md` exists AND its mtime > `tutorials/postprocessing-rules.md` mtime → skip. When the rules file is newer (new rules added since last run), re-run. Overridable via the `force_repostprocess` DAG parameter.
- **`store`:** no idempotency check — overwriting `gktuition-prod/transcripts/<slug>.md` is cheap and safe.

The mtime-based postprocess check is what enables the "added a new rule, re-clean every transcript overnight" workflow. No special re-run DAG needed.

## (d) Failure handling — retry policy + dead-letter

Per-task config:

```python
default_args = {
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "execution_timeout": timedelta(minutes=10),  # individual task ceiling
}
```

- On first failure: wait 2 min, retry once.
- On second failure: task ends `failed`; downstream tasks of the same video mark `upstream_failed`; **the DAG continues processing other videos** (the dynamic-task-mapping pattern isolates failures per video, not per DAG run).
- Failure metadata written to `data/dead-letter/<slug>.error` with timestamp + task name + exception text + stack trace tail.
- A terminal `summarise_run` task (run regardless of upstream success, via `trigger_rule="all_done"`) prints `"X succeeded, Y failed"` + the full list of dead-letter files. Also commits a sanitised run-stats log to the public repo at `docs/ingestion-runs/<YYYY-MM-DD>.md` (numbers only — no transcript content).

## (e) Cost estimate per run

| Component | Cost |
|---|---|
| `yt-dlp` audio download | €0 |
| Whisper transcription | €0.006/min × ~10 min avg = **~€0.06 per video** |
| `ffmpeg` recompression | €0 |
| Airflow itself | €0 (local) |
| Storage (local disk) | €0 |

**Per-batch projections** (assuming €0.06/video):
- 25-video batch: **~€1.50** ✓ within €2.50 target
- 40-video batch: **~€2.40** ✓ within target
- 80-video full corpus: ~€4.80 — too high for one run

**Decision:** split the full corpus into **two batches of ~40 videos each**, run on separate days. Bound the worst-case wasted spend if something goes wrong mid-batch. Each batch costs <€2.50; total full-corpus spend ≈€5 spread over the two runs.

## (f) Open questions

1. **Snowflake `RAW.QUERY_LOG` schema for ingestion observability.** The DAG should write run-level stats (videos attempted, succeeded, failed, total Whisper cost) somewhere queryable for trend analysis. Snowflake adds dependency; local SQLite is simpler. **Lean: SQLite for v1, migrate to Snowflake when retrieval-side work needs an integrated observability dashboard.**

2. **Parallelism cap.** Whisper's default rate limit is 50 req/min. Setting `max_active_tasks_per_dag = 5` keeps us well within bounds. **Lean: start at 3 to be conservative; raise to 5 after the first 25-video run if no rate-limit errors.**

3. **Audio cache eviction.** `data/audio/` will accumulate ~80 mp3s at ~6 MB each = ~500 MB. Local disk is fine but stale audio for videos we're confident in (cleaned transcript stable) could be archived/deleted. **Lean: defer — disk is cheap and re-downloading is free.**

4. **Whisper rate-limit handling.** Currently no explicit backoff for 429 errors beyond Airflow's task-level retry. **Lean: rely on the retry; add explicit exponential backoff only if we see 429s in practice on the first batch.**

5. **Public stats log format.** What goes in `docs/ingestion-runs/<date>.md`? At minimum: video count, success rate, total cost, average cost/video, top 3 postprocessing rules by firing count. Worth confirming the shape before the first commit so it's stable across runs.

## Next steps

- DAY_22 (Sun): scaffold `dags/ingestion_dag.py` with `download_audio` task only.
- DAY_23 (Mon): add `transcribe`.
- DAY_24 (Tue): add `postprocess`.
- DAY_25 (Wed): first 25-video batch run.
- DAY_26 (Thu): second batch (40 videos) + Snowflake foundation stand-up.