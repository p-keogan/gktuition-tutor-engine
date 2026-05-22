-- ============================================================================
-- create_summary_search_service.sql
-- ----------------------------------------------------------------------------
-- Registers `GKTUITION_TUTOR.CORTEX.SUMMARY_SEARCH` — the Cortex Search
-- Service over RAW.SUMMARIES.
--
-- Single-field index (per DAY_26 architecture review):
--   Summary sheets are short, dense, and uniform in voice; the precision
--   vs. recall split that motivates Agent 01's multi-field TUTOR_SEARCH
--   doesn't apply here. One embedding column (`body`) is the right shape.
--
-- Attributes promoted as filterable metadata:
--   • `summary_id`                 — primary key.
--   • `strand_name`                — human-readable label, e.g. "The Line".
--   • `strand_folder`              — directory name, e.g. "LCHL_The_Line".
--   • `top_tutorials_by_frequency` — multi-value filter; lets the FastAPI
--                                    orchestrator pivot from a summary hit
--                                    straight into the related tutorials
--                                    in one round trip.
--
-- Typical orchestrator pattern: a student utterance with the cram-intent
-- phrasing ("I'm cramming The Line tonight") routes here; the top hit's
-- `top_tutorials_by_frequency` array then seeds the follow-up TUTOR_SEARCH
-- call without needing a Cortex Analyst pass.
--
-- Cost: lives on WH_TUTOR (XS, auto-suspend 60s, monitored by
-- RM_TUTOR_DAILY). TARGET_LAG = '1 day' is plenty — strand summaries are
-- regenerated only when the corpus or LCHL_exam_trends.md changes.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA CORTEX;

CREATE OR REPLACE CORTEX SEARCH SERVICE SUMMARY_SEARCH
    ON body
    ATTRIBUTES summary_id,
               strand_name,
               strand_folder,
               top_tutorials_by_frequency
    WAREHOUSE = WH_TUTOR
    TARGET_LAG = '1 day'
    COMMENT = 'Per-strand cram-summary Cortex Search Service. Single-field index over the full markdown body.'
    AS (
        SELECT * FROM GKTUITION_TUTOR.RAW.SUMMARIES
    );

-- ─── Sanity check ──────────────────────────────────────────────────────────
SHOW CORTEX SEARCH SERVICES LIKE 'SUMMARY_SEARCH' IN SCHEMA GKTUITION_TUTOR.CORTEX;
DESC CORTEX SEARCH SERVICE GKTUITION_TUTOR.CORTEX.SUMMARY_SEARCH;

-- ─── Smoke test: "I'm cramming The Line tonight…" ──────────────────────────
-- The top hit's `strand_name` must equal "The Line". If it doesn't, either
-- the body extractor stripped the wrong section or the index isn't yet
-- populated (TARGET_LAG = '1 day' — initial indexing takes a few minutes).
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'GKTUITION_TUTOR.CORTEX.SUMMARY_SEARCH',
        OBJECT_CONSTRUCT(
            'query', 'I''m cramming The Line tonight what do I need to know',
            'columns', ARRAY_CONSTRUCT('summary_id', 'strand_name'),
            'limit', 3
        )::VARCHAR
    )
)['results'] AS top_hits;
