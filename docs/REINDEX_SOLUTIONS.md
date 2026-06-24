# Reindexing exam solutions into SOLUTIONS_SEARCH

**Why:** the AI tutor routes "stuck on 2024 P2 Q7(a)"-style queries to the
`GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH` Cortex service (correct), but that
service was empty/stale for recent years — the worked solutions in
`career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions/` (which include
`2024_P2_solutions.md`, `2025_P2_solutions.md`, etc.) hadn't been loaded into
`RAW.EXAM_PARTS`. Re-running the loader fixes it.

Pipeline: `Solutions/*.md` → **`load_exam_parts.py`** → `RAW.EXAM_PARTS`
(idempotent MERGE on `part_id`) → **`SOLUTIONS_SEARCH`** (Cortex Search over
that table; auto re-embeds within `TARGET_LAG = '1 day'`).

---

## Prerequisites (run on your machine, with Snowflake access)

```bash
pip install "snowflake-connector-python[pandas]"   # if not already installed

# Snowflake creds (same account the Fly engine uses). Password OR key-pair.
export SNOWFLAKE_ACCOUNT="<your account, e.g. abc12345.eu-west-1>"
export SNOWFLAKE_USER="<user>"
export SNOWFLAKE_PASSWORD="<password>"          # or: export SNOWFLAKE_PRIVATE_KEY_PATH=...
export SNOWFLAKE_ROLE="ACCOUNTADMIN"
export SNOWFLAKE_WAREHOUSE="WH_TUTOR"
export SNOWFLAKE_DATABASE="GKTUITION_TUTOR"
export SNOWFLAKE_SCHEMA="RAW"
```

## Step 0 — see what's currently indexed (confirms the gap)

In a Snowflake worksheet:

```sql
-- How many parts, and which years are present?
SELECT year, COUNT(*) AS parts
FROM GKTUITION_TUTOR.RAW.EXAM_PARTS
GROUP BY year ORDER BY year;
```

If 2024/2025 are missing (or the table is empty / doesn't exist), that's the gap.

## Step 1 — dry run (parse only, no writes)

```bash
cd /Users/paul/code/gktuition-tutor-engine/snowflake
python load_exam_parts.py --dry-run \
  --solutions-dir ../../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions
```

Confirm it walks all ~30 files and reports the part count (~1,200+) with no parse errors.

## Step 2 — load into RAW.EXAM_PARTS (live)

`--no-write-crossrefs` keeps it from editing your source `.md` files (pure index load):

```bash
python load_exam_parts.py --no-write-crossrefs \
  --solutions-dir ../../career-transition-2026/tutorials/LCHL_Maths_Exams/Solutions
```

This MERGEs every part keyed on `part_id`, so it's safe to re-run (new years inserted, existing rows updated).

## Step 3 — refresh the search service

`SOLUTIONS_SEARCH` re-embeds automatically within its `TARGET_LAG` (1 day). To
force it immediately, re-run the service definition (re-embeds the whole table —
fine for ~1,200 parts):

```bash
# from the snowflake/ dir, via snowsql or a worksheet:
snowsql -f create_solutions_search_service.sql
```

(If you don't have snowsql, just paste `create_solutions_search_service.sql`
into a Snowflake worksheet and run it.)

## Step 4 — smoke test

The bottom of `create_solutions_search_service.sql` runs this; the top hit's
`part_id` should start with `2024_main_P2_Q5`:

```sql
SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
  'GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH',
  OBJECT_CONSTRUCT('query','how was 2024 P2 Q7 solved',
                   'columns', ARRAY_CONSTRUCT('part_id','topic','question_text'),
                   'limit', 3)::VARCHAR))['results'];
```

Then ask the tutor "I'm stuck on 2024 P2 Q7(a)" — it should now retrieve and
walk through the solution instead of asking you to paste the question.

---

### Notes
- The engine reads `SOLUTIONS_SEARCH` live; no engine redeploy is needed once the index is refreshed.
- `content-pipeline/sync/run_loaders.py` can orchestrate this (detects changed
  content and calls the right loader) if you'd rather run the whole pipeline,
  but the direct `load_exam_parts.py` call above is the targeted fix.
- Coverage to expect after load: 2015–2025, both papers, including DF (deferred) sittings.
