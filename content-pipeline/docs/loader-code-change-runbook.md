# Loader-code-change runbook

This document covers the case where the **pipeline itself** changed —
not the corpus it walks. The risk profile is different and worse: a
content edit changes one row in `RAW.TUTORIALS`; a loader-code change
can quietly change the *shape* of every row in `RAW.TUTORIALS` and
every embedding under `TUTOR_SEARCH`. The handbook (`content-pipeline-
handbook.md`) covers the safe path; this file covers the audit path.

The pipeline detects loader-code changes automatically: any file under
`gktuition-tutor-engine/snowflake/` showing up in the manifest sets
`loader_code_changed = true`, which causes `run_loaders.py` to STOP
with exit code 3 rather than auto-dispatch. This is the deliberate
brake. The procedure below is what to do when you trip it.

---

## What counts as a loader-code change

* `snowflake/load_tutorials.py`, `snowflake/load_exam_parts.py`, or
  `snowflake/load_summaries.py` — the three Python loaders Agent 14
  drives.
* `snowflake/bootstrap_*.sql` — DDL files. Schema migrations.
* `snowflake/create_*_search_service.sql` — Cortex Search Service
  definitions. Changing the indexed columns or the embedding model
  invalidates every prior retrieval result.
* `snowflake/cortex_analyst/*.yaml` — the semantic model the
  Analyst leg reads.

Edits to `content-pipeline/` itself (the validator, the sync scripts,
this docs folder) are **not** loader-code changes for STOP purposes —
they live outside `snowflake/`. They do still need their own
verification (the pipeline's own test fixtures should be exercised),
but they don't risk invalidating the baseline eval score.

---

## The five-step procedure

### Step 1 — Eyeball the diff

```bash
git diff origin/main..HEAD -- snowflake/
```

For each changed line, ask:

* **Does it change the row dict?** New column, removed column,
  changed key — anything that alters what `build_row()` returns.
* **Does it change the MERGE key?** Anything that touches the
  `ON s.slug = t.slug` clause is essentially a schema rewrite.
* **Does it change the indexing model?** `create_tutor_search_service.sql`
  edits — new `ON` columns, different `WAREHOUSE`, different
  `TARGET_LAG` — reset the embedding baseline.

Innocuous edits (logging, comments, type hints, a more defensive
`_as_list`) don't change the baseline. Risky edits (chunker boundary
changes, new column populations, marks-fallback adjustments) do.

### Step 2 — Re-run every loader in `--dry-run`

```bash
cd gktuition-tutor-engine/snowflake
python load_tutorials.py --dry-run \
    --tutorials-root ../../career-transition-2026/tutorials

python load_exam_parts.py --dry-run \
    --solutions-dir ../../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions

python load_summaries.py --dry-run \
    --tutorials-root ../../career-transition-2026/tutorials
```

The headline numbers — Agent 01's 237 tutorials, Agent 02's 1,213
parts, Agent 02's 20 summaries — should be unchanged unless the
change set explicitly relaxed or tightened the skip rules. A
silent change in those counts is the loudest signal that the
behaviour drifted.

### Step 3 — MERGE into Snowflake

After the dry-runs check out, dispatch the loaders for real. The
MERGE is keyed on the stable IDs (slug / part_id / summary_id), so
existing rows update in place; the `loaded_at` provenance column
shows you the run that last touched each row.

Don't refresh Cortex Search yet — that locks in the new embedding
baseline before you've measured the regression.

### Step 4 — Re-score the eval set

```bash
cd gktuition-tutor-engine/eval
python score_against_cortex_search.py \
    --golden-subset \
    --output ./scores/after-loader-change-$(date +%Y%m%d).json
```

Compare to the DAY_26 baseline (locked at `precision@1 = 0.710`,
`recall@5 = 0.985`, `MRR = 0.835`, `0 errors`).

Deploy gates:

* **PASS:** precision@1 drops no more than 2 percentage points
  (0.690 or higher). Recall@5 unchanged or improves.
* **WARN:** precision@1 drops 2–5 points. Investigate before
  merging — this is a real regression but possibly intentional
  (you tightened the chunker; some recall-shaped queries lose to
  shorter context).
* **STOP:** precision@1 drops more than 5 points OR error count
  rises above zero. Roll back the loader change; do not deploy.

### Step 5 — Now refresh Cortex Search

```bash
python content-pipeline/sync/refresh_cortex.py \
    --services TUTOR_SEARCH,SOLUTIONS_SEARCH,SUMMARY_SEARCH
```

Wait for `last_refreshed_on` to advance (the script polls for you).
Re-run the eval-set scorer once more against the refreshed index;
the post-refresh score is the one that ships.

### Step 6 — Commit, push, manually fire the workflow

The push will trigger `content-sync.yml`. With `loader_code_changed =
true` in the manifest, `run_loaders.py` will STOP — that's expected.
Re-dispatch via the Actions tab → Run workflow with
`force_cortex_refresh = false` (you've already done the refresh) and
the run will succeed because nothing's left to do — the loaders ran
locally, the index is fresh, the audit row is in.

Add a row to `notes.md` with the DAY_NN entry: which loader changed,
which eval score moved, and where the new locked baseline sits.

---

## Common loader-code changes and what they do to the baseline

| Change | Expected baseline movement | Mitigation |
|---|---|---|
| New required field on `TUTORIALS` table | -5 to -15 pts on precision if back-fill is sparse | Back-fill across corpus before deploy |
| Larger `title_plus_phrasings` cap (currently 4,000) | +0 to +1 pts; risk of cap being decorative | Keep the 4,000 cap unless you can show measurable recall gains |
| Chunker change (`load_exam_parts.py`) | ±3 pts on solution_cross_ref bucket | Spot-check 5 known parts pre/post chunk |
| New strand summary (`load_summaries.py`) | SUMMARY_SEARCH precision rises if quality is high; otherwise flat | Eyeball the rendered body |
| New synonym in Cortex Analyst semantic model | None on Cortex Search; +1 to +5 pts on Analyst routing | Re-run the 10 canonical Analyst queries |
| `TARGET_LAG` change on the Cortex Search Services | None on scoring; latency profile changes | Document the new cadence in the handbook |

---

## What this runbook deliberately doesn't cover

* The eval-set runner itself (`score_against_cortex_search.py`). That's
  Agent 05's deliverable. Treat it as a black box.
* Cost monitoring (the €5/day Resource Monitor). Cost is ADR-002's
  domain; if a loader-code change blows the budget, the resource
  monitor cuts you off, not this runbook.
* Anthropic API / Claude Haiku 4.5 routing changes. The orchestrator
  is Agent 09's deliverable; loader changes don't typically affect it
  unless the row dict shape changes (which the handbook flags as the
  highest-risk class).
