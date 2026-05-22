-- =====================================================================
-- bootstrap_content_change_log.sql
-- ---------------------------------------------------------------------
-- Audit table for the content-edit propagation pipeline.
-- Every run of `content-pipeline/sync/run_loaders.py` appends one row.
--
-- Owned by Agent 14 (the content-edit pipeline). Disjoint from the
-- Agents 01/02/04 schemas — this table is metadata about the pipeline,
-- not corpus content.
--
-- Idempotent: CREATE OR REPLACE wipes and rebuilds. Re-run only when
-- the column set changes (rare).
-- =====================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG (
    -- ─── Identity ──────────────────────────────────────────────────
    change_id                   VARCHAR        NOT NULL,
    git_commit_sha              VARCHAR,           -- HEAD at the time of the push
    triggered_by                VARCHAR,           -- 'human:<user>' | 'github-action:<actor>'
    triggered_at                TIMESTAMP_NTZ  NOT NULL,

    -- ─── What changed ──────────────────────────────────────────────
    files_changed               ARRAY,             -- repo-relative paths
    loaders_run                 ARRAY,             -- ['load_tutorials', 'load_exam_parts', ...]

    -- ─── What the loaders did ──────────────────────────────────────
    rows_inserted               NUMBER,            -- sum across loaders that ran
    rows_updated                NUMBER,
    rows_unchanged              NUMBER,            -- reserved; Snowflake MERGE
                                                  -- doesn't surface a third bucket
                                                  -- but the column is here for
                                                  -- future use
    duration_ms                 NUMBER,            -- total wall-clock across all loaders

    -- ─── Downstream effects ───────────────────────────────────────
    cortex_refresh_triggered    BOOLEAN,           -- true iff refresh_cortex.py ran

    -- ─── Free-form ────────────────────────────────────────────────
    notes                       VARCHAR,           -- 'ok' on a clean run;
                                                  -- 'FAILURES: load_tutorials(exit=1)'
                                                  -- on a partial failure

    CONSTRAINT pk_content_change_log PRIMARY KEY (change_id)
)
COMMENT = $$
Append-only audit log for content-edit propagations.

Every push to main that touches `tutorials/**/*.md` results in one
row here, even if the manifest indicated nothing to load (still
useful for "did the GitHub Action fire today?" forensics).

Query patterns the operator will reach for:

  -- "what changed this week"
  SELECT triggered_at, files_changed, loaders_run, rows_inserted, rows_updated
    FROM RAW.CONTENT_CHANGE_LOG
   WHERE triggered_at >= DATEADD(day, -7, CURRENT_TIMESTAMP())
   ORDER BY triggered_at DESC;

  -- "did this commit make it through"
  SELECT *
    FROM RAW.CONTENT_CHANGE_LOG
   WHERE git_commit_sha = '<sha>';

  -- "what's been failing"
  SELECT triggered_at, notes, files_changed
    FROM RAW.CONTENT_CHANGE_LOG
   WHERE notes ILIKE 'FAILURES%'
   ORDER BY triggered_at DESC
   LIMIT 50;

Owner: content-pipeline/sync/run_loaders.py (Agent 14).
$$;

-- Sanity check — show the columns.
DESC TABLE GKTUITION_TUTOR.RAW.CONTENT_CHANGE_LOG;
