-- =============================================================================
-- GKTUITION_TUTOR.RAW.QUERY_LOG
-- =============================================================================
-- One row per /query or /image_query invocation. The schema is the
-- intersection of Agent 06's image-query logging concern and Agent 09's
-- text-query logging concern.
--
-- This file is idempotent: CREATE OR REPLACE TABLE rebuilds the table on
-- every dispatch. Re-running it deletes existing rows; if you want to keep
-- history across schema changes, dispatch CREATE TABLE IF NOT EXISTS and
-- handle migrations explicitly. The schema is small enough that REPLACE is
-- the right default for Phase 1.5 — Agent 10 will harden the table when it
-- wires the per-IP / per-day cost firewall checks against it.
--
-- Per the cost firewall in ADR-002, this table is the source of truth for
-- the €5/day kill switch — Agent 10's L5 layer reads from it directly.
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.QUERY_LOG (
    query_id              VARCHAR        NOT NULL,
    q                     VARCHAR        NOT NULL,
    tier                  VARCHAR        NOT NULL,   -- 'anonymous' | 'authenticated_free' | 'paying'
    query_type            VARCHAR        NOT NULL,   -- 'text' | 'image'
    query_class           VARCHAR        NOT NULL,   -- concept | solution_lookup | summary_request | analytical | image_extracted | ambiguous
    model_used            VARCHAR        NOT NULL,   -- cortex.mistral-large2 | anthropic.claude-haiku-4-5 | anthropic.claude-sonnet-4 | cortex.analyst | (none)
    top_slug              VARCHAR,                   -- top citation slug, NULL on guardrail
    top_reranker_score    FLOAT,                     -- 0..1; 0 on guardrail
    from_cache            BOOLEAN        NOT NULL DEFAULT FALSE,
    elapsed_ms            INTEGER        NOT NULL,
    cost_estimate_cents   FLOAT          NOT NULL,
    extracted_question    VARCHAR,                   -- NULL except for query_type='image'
    image_bytes_size      INTEGER,                   -- NULL except for query_type='image'
    extraction_outcome    VARCHAR,                   -- NULL except for query_type='image'
    user_id               VARCHAR,                   -- 'anonymous' for the unauthenticated path
    created_at            TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_query_log PRIMARY KEY (query_id)
)
COMMENT = 'One row per /query or /image_query invocation. Agent 09 + Agent 06 jointly own this schema.';

-- A handful of queries Agent 10 will use to drive the cost firewall:
--   spend so far today
--     SELECT SUM(cost_estimate_cents) FROM GKTUITION_TUTOR.RAW.QUERY_LOG
--      WHERE created_at::DATE = CURRENT_DATE();
--   per-IP rate-limit window
--     (Agent 10 carries the IP column in a sibling RAW.RATE_LIMIT table —
--     intentionally kept separate so PII concentration is bounded.)
--
-- A short trailing select so SnowSQL prints a confirmation after dispatch.
SELECT 'GKTUITION_TUTOR.RAW.QUERY_LOG ready' AS status;
