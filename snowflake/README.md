# `snowflake/` — DDL and loaders for the GKTuition AI Tutor

Everything Snowflake-side that the AI tutor depends on lives in this folder.
Dispatch the files in the documented order; each step is idempotent.

## Layout

| File | Owner | Purpose |
|---|---|---|
| `bootstrap_warehouse_and_database.sql` | Agent 01 | Account-level objects: `WH_TUTOR`, `GKTUITION_TUTOR` database, `RAW` + `CORTEX` schemas, `RM_TUTOR_DAILY` resource monitor. |
| `bootstrap_tutorials_table.sql` | Agent 01 | `GKTUITION_TUTOR.RAW.TUTORIALS` — the per-tutorial table that powers `TUTOR_SEARCH`. |
| `load_tutorials.py` | Agent 01 | Walks `tutorials/LCHL_*/*.md`, parses YAML, MERGEs into `RAW.TUTORIALS`. |
| `create_tutor_search_service.sql` | Agent 01 | Registers `CORTEX.TUTOR_SEARCH` as a multi-field service over `title_plus_phrasings` + `body`. |
| `bootstrap_exam_parts_table.sql` | Agent 02 | `GKTUITION_TUTOR.RAW.EXAM_PARTS` and `SUMMARIES` — one row per `### Q…` boundary in `LCHL_Maths_Exams/Solutions/`. |
| `load_exam_parts.py` | Agent 02 | Loader for the above. |
| `create_solutions_search_service.sql` | Agent 02 | `SOLUTIONS_SEARCH` + `SUMMARY_SEARCH`. |
| `bootstrap_eval_table.sql` | Agent 05 | `GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET`. |
| `seed_eval_set.py` | Agent 05 | Bootstraps the eval set from `common_student_phrasings` + solution cross-refs. |

## Dispatch order (end-to-end build)

```
                ┌──────────────────────────────────────────────┐
                │ 1. bootstrap_warehouse_and_database.sql      │
                │    (warehouse, database, schemas, RM)        │
                └────────────────────┬─────────────────────────┘
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
┌────────────────────────┐ ┌─────────────────────────┐ ┌────────────────────────┐
│ 2a. bootstrap_         │ │ 2b. (Agent 02)          │ │ 2c. (Agent 05)         │
│     tutorials_table.sql│ │   bootstrap_exam_       │ │   bootstrap_eval_      │
│                        │ │   parts_table.sql       │ │   table.sql            │
└──────────┬─────────────┘ └────────────┬────────────┘ └──────────┬─────────────┘
           │                            │                         │
           ▼                            ▼                         ▼
┌────────────────────────┐ ┌─────────────────────────┐ ┌────────────────────────┐
│ 3a. load_tutorials.py  │ │ 3b. (Agent 02)          │ │ 3c. (Agent 05)         │
│     (this folder)      │ │   load_exam_parts.py    │ │   seed_eval_set.py     │
└──────────┬─────────────┘ └────────────┬────────────┘ └────────────────────────┘
           │                            │
           ▼                            ▼
┌────────────────────────┐ ┌─────────────────────────┐
│ 4a. create_tutor_      │ │ 4b. (Agent 02)          │
│     search_service.sql │ │   create_solutions_     │
│                        │ │   search_service.sql    │
└────────────────────────┘ └─────────────────────────┘
```

In English:

1. **Bootstrap the account-level objects** — once per fresh account or after a teardown.
2. **Create the empty tables** — once per schema change.
3. **Load data** — every time the corpus changes. Idempotent.
4. **Register / refresh the Cortex Search Services** — once per schema or definition change. Re-embedding is automatic on the `TARGET_LAG` cadence.

## Running Agent 01's slice end-to-end

```bash
# 0. From a Snowflake worksheet (ACCOUNTADMIN role)
\!source bootstrap_warehouse_and_database.sql
\!source bootstrap_tutorials_table.sql

# 1. From a local shell with the project's Python 3.12 venv active and
#    SNOWFLAKE_* env vars set (see load_tutorials.py docstring).
source ../../career-transition-2026/.venv-py312/bin/activate
python load_tutorials.py \
    --tutorials-root ../../career-transition-2026/tutorials

# 2. Back in the worksheet — register the search service.
\!source create_tutor_search_service.sql
```

`load_tutorials.py --dry-run` walks + parses the corpus and prints counts
without touching Snowflake — useful as a fast sanity-check after editing
a tutorial's YAML.

## Required Snowflake permissions

The bootstrap SQL files all start with `USE ROLE ACCOUNTADMIN` because:

* `RM_TUTOR_DAILY` requires ACCOUNTADMIN (resource monitors are account-level).
* `WH_TUTOR` warehouse creation likewise.
* `CREATE CORTEX SEARCH SERVICE` requires `CREATE CORTEX SEARCH SERVICE` on
  the schema — easiest to dispatch as ACCOUNTADMIN for v1, then refactor to
  a dedicated `TUTOR_ENGINEER` role once the schema stabilises.

`load_tutorials.py` runs under whatever role its `SNOWFLAKE_ROLE` env var
points at (default `ACCOUNTADMIN`). To run it under a less-privileged role,
grant: `USAGE on WH_TUTOR`, `USAGE on GKTUITION_TUTOR`, `USAGE on RAW`,
`SELECT, INSERT, UPDATE on RAW.TUTORIALS`, `CREATE TABLE on RAW`.

## Multi-text-column ON syntax — fallback if not yet enabled in the account

`create_tutor_search_service.sql` uses

```sql
ON title_plus_phrasings, body
```

If the target account has not yet enabled Cortex Search's multi-text-column
feature, the syntax raises a parser error. Fallback: create two
single-column services and merge results in the FastAPI layer.

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE TUTOR_SEARCH_PHRASINGS
    ON title_plus_phrasings
    ATTRIBUTES <…same list…>
    WAREHOUSE = WH_TUTOR
    TARGET_LAG = '1 day'
    AS (SELECT * FROM GKTUITION_TUTOR.RAW.TUTORIALS);

CREATE OR REPLACE CORTEX SEARCH SERVICE TUTOR_SEARCH_BODY
    ON body
    ATTRIBUTES <…same list…>
    WAREHOUSE = WH_TUTOR
    TARGET_LAG = '1 day'
    AS (SELECT * FROM GKTUITION_TUTOR.RAW.TUTORIALS);
```

The FastAPI router queries both, then reciprocally-ranks the two result
lists (RRF) before returning. Defer this until Snowflake actually rejects
the multi-column form on the target account.

## Cost controls

* `RM_TUTOR_DAILY` (€5/day) suspends `WH_TUTOR` at 100% of quota. The Cortex
  Search Service uses the same warehouse for index maintenance, so the
  ceiling applies to embedding refreshes too.
* `WH_TUTOR` auto-suspends after 60 s of idle.
* `TARGET_LAG = '1 day'` keeps re-embedding to a single overnight pass.
