-- ============================================================================
-- create_tutor_search_service.sql
-- ----------------------------------------------------------------------------
-- Registers the TUTOR_SEARCH Cortex Search Service over the multi-field
-- TUTORIALS table.
--
-- Multi-field indexing rationale (per DAY_26 architecture review):
--   `title_plus_phrasings` and `body` are embedded as separate text fields,
--   not as one concatenated blob. Each gets its own embedding; retrieval
--   can target either or both. The motivating insight is that student
--   utterances such as
--      "I got two answers for a, which one is right"
--   match `common_student_phrasings` near-verbatim — concatenating that
--   precision signal with ~6 kB of transcript body would dilute it under
--   the recall noise. Keeping them split lets the index rank exact-phrase
--   matches at the top while the body column still backs paragraph-level
--   grounding once a tutorial is selected.
--
-- Attributes:
--   • `slug`              — primary key, returned for citation deep-links.
--   • `title`             — human-readable label for the citation card.
--   • `topic`/`subtopic`  — filterable by strand / sub-strand.
--   • `paper`             — filterable by 1 / 2.
--   • `course_levels`     — multi-value filter ([LCHL], [JCHL], …).
--   • `techniques`        — multi-value filter on kebab-token technique IDs.
--   • `sequence_number`   — sortable for "next tutorial in strand".
--   • `youtube_url`       — included in response so the widget can deep-link.
--   • `gktuition_url`     — paid-tier deep-link target.
--   • `warnings_and_gotchas` — returned alongside hits so the JSON response
--                              contract (ADR-003) can surface load-bearing
--                              misconception text without an extra join.
--
-- Syntax note: this uses the multi-text-column form of `ON …, …`. If the
-- target account has not yet enabled that Cortex Search feature, the
-- fallback is two single-column services (TUTOR_SEARCH_PHRASINGS,
-- TUTOR_SEARCH_BODY) that the FastAPI layer queries in parallel and
-- merges. See snowflake/README.md for the fallback DDL.
--
-- Cost: lives on WH_TUTOR (XS, auto-suspend 60s). Re-embed cadence is
-- `TARGET_LAG = '1 day'` — overnight refresh is more than fine because the
-- corpus is hand-curated, not high-velocity. Tighten to '1 hour' once the
-- DAG-based ingestion lands.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA CORTEX;

CREATE OR REPLACE CORTEX SEARCH SERVICE TUTOR_SEARCH
    ON title_plus_phrasings, body
    ATTRIBUTES slug,
               title,
               topic,
               subtopic,
               paper,
               course_levels,
               techniques,
               sequence_number,
               youtube_url,
               gktuition_url,
               warnings_and_gotchas
    WAREHOUSE = WH_TUTOR
    TARGET_LAG = '1 day'
    COMMENT = 'Per-tutorial Cortex Search Service. Multi-field index over title_plus_phrasings (precision route) and body (recall route).'
    AS (
        SELECT slug,
               video_id,
               title,
               title_plus_phrasings,
               body,
               warnings_and_gotchas,
               techniques,
               course_levels,
               paper,
               topic,
               subtopic,
               sequence_number,
               duration_seconds,
               youtube_url,
               gktuition_url,
               prerequisites,
               forward_links,
               xref,
               log_tables,
               syllabus_strand,
               syllabus_section,
               syllabus_reference,
               exam_appearances,
               learning_work,
               companion_practice_questions
          FROM GKTUITION_TUTOR.RAW.TUTORIALS
    );

-- ─── Sanity check ──────────────────────────────────────────────────────────
SHOW CORTEX SEARCH SERVICES LIKE 'TUTOR_SEARCH' IN SCHEMA GKTUITION_TUTOR.CORTEX;
DESC CORTEX SEARCH SERVICE GKTUITION_TUTOR.CORTEX.TUTOR_SEARCH;

-- ─── Smoke test: the canonical "I got two answers for a" query ────────────
-- Top-1 must be `the-line-4-area-of-triangle`. If it isn't, the multi-field
-- ordering or the title_plus_phrasings build is wrong.
SELECT PARSE_JSON(
    SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'GKTUITION_TUTOR.CORTEX.TUTOR_SEARCH',
        OBJECT_CONSTRUCT(
            'query', 'I got two answers for a, which one is right',
            'columns', ARRAY_CONSTRUCT('slug', 'title'),
            'limit', 3
        )::VARCHAR
    )
)['results'] AS top_hits;
