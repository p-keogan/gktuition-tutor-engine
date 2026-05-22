-- ============================================================================
-- create_solutions_search_service.sql
-- ----------------------------------------------------------------------------
-- Registers `GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH` — the Cortex Search
-- Service over RAW.EXAM_PARTS.
--
-- Multi-field indexing (per DAY_26 architecture review):
--   Three text columns are indexed simultaneously, each with its own
--   embedding, so retrieval can target the right signal for the right intent:
--     • `solution_text`   — full tutorial-style worked solution (recall route)
--     • `question_text`   — the exam-paper prompt              (precision route)
--     • `common_pitfalls` — 🎯/🚨 pitfall callouts              (misconception route)
--   This mirrors Agent 01's `title_plus_phrasings` + `body` split on
--   TUTOR_SEARCH. Concatenating these three fields into one blob would
--   bury exact-prompt and pitfall matches under several kB of solution prose.
--
-- Attributes promoted as filterable metadata:
--   • `part_id`              — primary key for citation deep-links.
--   • `year` / `paper` / `sitting`
--   • `question_number` / `sub_part` / `section`
--   • `marks`               — per-part mark allocation.
--   • `topic`               — primary topic (the **Topic:** line).
--   • `secondary_topics`    — multi-value filter on strand names.
--   • `tutorials_referenced` — multi-value filter for graph traversal:
--                             pivot from "this exam part" → "the tutorials
--                             that teach it" in one round trip.
--
-- Typical orchestrator pattern (from the FastAPI handler):
--   Pre-filter on year/paper/sitting/question_number when the student's
--   utterance is paper-specific ("how was 2024 P2 Q5 solved"), then let
--   embedding similarity rank the parts within that slice. For broader
--   queries ("modulus inequality") drop the filters and let the full
--   1,213-part index do the work.
--
-- Syntax note: this uses the multi-text-column `ON …, …, …` form. If the
-- target account has not enabled that Cortex Search feature yet, see the
-- fallback DDL pattern documented in snowflake/README.md (three single-
-- column services, RRF-merged in the FastAPI layer).
--
-- Cost: lives on WH_TUTOR (XS, auto-suspend 60s, monitored by
-- RM_TUTOR_DAILY). TARGET_LAG = '1 day' is plenty for a hand-curated
-- corpus — re-embedding happens at most once overnight.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA CORTEX;

CREATE OR REPLACE CORTEX SEARCH SERVICE SOLUTIONS_SEARCH
    ON solution_text, question_text, common_pitfalls
    ATTRIBUTES part_id,
               year,
               paper,
               sitting,
               question_number,
               sub_part,
               section,
               marks,
               topic,
               secondary_topics,
               tutorials_referenced
    WAREHOUSE = WH_TUTOR
    TARGET_LAG = '1 day'
    COMMENT = 'Per-exam-part Cortex Search Service. Multi-field index over solution_text (recall), question_text (precision), common_pitfalls (misconception).'
    AS (
        SELECT * FROM GKTUITION_TUTOR.RAW.EXAM_PARTS
    );

-- ─── Sanity check ──────────────────────────────────────────────────────────
SHOW CORTEX SEARCH SERVICES LIKE 'SOLUTIONS_SEARCH' IN SCHEMA GKTUITION_TUTOR.CORTEX;
DESC CORTEX SEARCH SERVICE GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH;

-- ─── Smoke test: "how was 2024 P2 Q5 solved" ───────────────────────────────
-- The top hit's `part_id` must start with `2024_main_P2_Q5`. If it doesn't,
-- either the chunker has mis-keyed those rows, or the multi-text-column ON
-- syntax isn't enabled on the account (fallback DDL in README.md).
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH',
        OBJECT_CONSTRUCT(
            'query', 'how was 2024 P2 Q5 solved',
            'columns', ARRAY_CONSTRUCT('part_id', 'topic', 'question_text'),
            'limit', 3
        )::VARCHAR
    )
)['results'] AS top_hits;
