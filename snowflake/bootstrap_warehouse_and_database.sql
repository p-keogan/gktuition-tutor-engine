-- ============================================================================
-- bootstrap_warehouse_and_database.sql
-- ----------------------------------------------------------------------------
-- Idempotent setup of the warehouse, database, schemas, and resource monitor
-- that the GKTuition Tutor stack depends on.
--
-- Order of operations:
--   1. Resource monitor RM_TUTOR_DAILY       (€5/day spend ceiling; SUSPEND at 100%)
--   2. Warehouse       WH_TUTOR              (XS, auto-suspend 60s, monitored)
--   3. Database        GKTUITION_TUTOR
--   4. Schemas         GKTUITION_TUTOR.RAW
--                      GKTUITION_TUTOR.CORTEX
--
-- Re-runnable: every statement uses CREATE OR REPLACE or CREATE … IF NOT EXISTS
-- so dispatching this script repeatedly is safe and converges on the desired
-- state. Resource monitor + warehouse use CREATE OR REPLACE so notification +
-- threshold changes propagate.
--
-- Required privileges: ACCOUNTADMIN (for resource monitor + warehouse creation).
-- Owner-of-record: the role you run this as. Switch to SYSADMIN for the
-- DATABASE / SCHEMA grants in the final block if you want a non-ACCOUNTADMIN
-- to be able to recreate the table later.
-- ============================================================================

USE ROLE ACCOUNTADMIN;

-- ─── 1. Resource monitor ───────────────────────────────────────────────────
-- €5/day with EUR pricing assumption (~ 5 credits/day on AWS-EU XS).
-- Notify at 80% and 100%. Hard SUSPEND at 100% so a runaway loader cannot
-- overshoot the daily ceiling. The notify-only triggers fire e-mail to all
-- account admins via Snowflake's default notification channel.
CREATE OR REPLACE RESOURCE MONITOR RM_TUTOR_DAILY
    WITH CREDIT_QUOTA = 5
         FREQUENCY = DAILY
         START_TIMESTAMP = IMMEDIATELY
    TRIGGERS
        ON 80 PERCENT DO NOTIFY
        ON 100 PERCENT DO SUSPEND;

-- ─── 2. Warehouse ──────────────────────────────────────────────────────────
-- XS is enough for the AI-tutor query path (one Cortex Search call + one
-- Cortex COMPLETE call per request). Auto-suspend 60s keeps idle cost near
-- zero. Monitored by RM_TUTOR_DAILY above.
CREATE OR REPLACE WAREHOUSE WH_TUTOR
    WITH WAREHOUSE_SIZE = 'XSMALL'
         AUTO_SUSPEND = 60
         AUTO_RESUME = TRUE
         INITIALLY_SUSPENDED = TRUE
         RESOURCE_MONITOR = RM_TUTOR_DAILY
         COMMENT = 'GKTuition AI Tutor warehouse. XS, auto-suspend 60s. Cost-capped via RM_TUTOR_DAILY.';

-- ─── 3. Database ───────────────────────────────────────────────────────────
CREATE DATABASE IF NOT EXISTS GKTUITION_TUTOR
    COMMENT = 'GKTuition AI Tutor — corpus, search services, eval set, query log.';

-- ─── 4. Schemas ────────────────────────────────────────────────────────────
-- RAW    — landing schema for ingested artefacts (TUTORIALS, EXAM_PARTS, …)
-- CORTEX — schema that owns Cortex Search Services and any Cortex Analyst
--          semantic models. Kept separate from RAW so a teardown of search
--          services never threatens the source data.
CREATE SCHEMA IF NOT EXISTS GKTUITION_TUTOR.RAW
    COMMENT = 'Landing zone for the tutorial corpus, exam-parts table, eval set, etc.';

CREATE SCHEMA IF NOT EXISTS GKTUITION_TUTOR.CORTEX
    COMMENT = 'Cortex Search Services and Cortex Analyst semantic models.';

-- ─── Sanity check ──────────────────────────────────────────────────────────
SHOW WAREHOUSES LIKE 'WH_TUTOR';
SHOW RESOURCE MONITORS LIKE 'RM_TUTOR_DAILY';
SHOW DATABASES LIKE 'GKTUITION_TUTOR';
SHOW SCHEMAS IN DATABASE GKTUITION_TUTOR;
