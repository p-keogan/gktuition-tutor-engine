-- =============================================================================
-- GKTUITION_TUTOR.CORTEX.QUERY_CACHE  +  GKTUITION_TUTOR.RAW.DAILY_SPEND
-- =============================================================================
-- Agent 10 (cost firewall, L3 + L5). Idempotent DDL:
--   * CREATE TABLE IF NOT EXISTS preserves history across re-dispatches.
--   * Both tables are intentionally small. QUERY_CACHE TTL is 30 days,
--     enforced at read-time (delete-on-stale) by the L3 layer, so the table
--     never grows past the working set. DAILY_SPEND holds one row per
--     (tier, date) pair — at most 4 rows per day across the project's life.
--
-- These tables sit alongside RAW.QUERY_LOG (Agent 09) and reuse the same
-- warehouse + database the orchestrator already provisions. No new
-- account-level objects.
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;

-- -----------------------------------------------------------------------------
-- L3: QUERY_CACHE
-- -----------------------------------------------------------------------------
USE SCHEMA CORTEX;

CREATE TABLE IF NOT EXISTS GKTUITION_TUTOR.CORTEX.QUERY_CACHE (
    cache_key       VARCHAR(64)    NOT NULL,    -- sha256 hex digest
    response_json   VARIANT        NOT NULL,    -- full QueryResponse payload
    model_used      VARCHAR        NOT NULL,    -- model used at cache write
    hits            NUMBER(38,0)   NOT NULL DEFAULT 0,
    last_hit_at     TIMESTAMP_NTZ,
    created_at      TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_query_cache PRIMARY KEY (cache_key)
)
COMMENT = 'L3 semantic cache. Keyed on sha256(norm_query + slugs + model + tier).';

-- The L3 layer reads + UPDATEs hit-counter on every hit. The DELETE-on-stale
-- path runs synchronously inside the request that observes the stale row, so
-- no scheduled cleanup is required for the working set we expect.

-- -----------------------------------------------------------------------------
-- L5: DAILY_SPEND
-- -----------------------------------------------------------------------------
USE SCHEMA RAW;

CREATE TABLE IF NOT EXISTS GKTUITION_TUTOR.RAW.DAILY_SPEND (
    tier         VARCHAR        NOT NULL,    -- 'anonymous' | 'authenticated_free' | 'paying'
    spend_date   DATE           NOT NULL,    -- UTC day
    spend_eur    NUMBER(12,6)   NOT NULL DEFAULT 0,
    updated_at   TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_daily_spend PRIMARY KEY (tier, spend_date)
)
COMMENT = 'L5 client-side spend tracker. Three nested caps fire off this table.';

-- Sanity check after dispatch.
SELECT 'GKTUITION_TUTOR.CORTEX.QUERY_CACHE + RAW.DAILY_SPEND ready' AS status;
