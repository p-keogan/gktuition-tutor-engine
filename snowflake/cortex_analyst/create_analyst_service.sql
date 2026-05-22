-- ============================================================================
-- create_analyst_service.sql
-- ----------------------------------------------------------------------------
-- Registers the `lchl_exam_analytics` Cortex Analyst service per ADR-004
-- Decision 2.
--
-- Dispatch order (idempotent):
--   1. Create the views (`views.sql`) so the base tables exist.
--   2. Create a Snowflake internal stage that holds the semantic model YAML.
--   3. Upload `semantic_model.yaml` to the stage (PUT — must run from
--      SnowSQL or the Snowflake Python connector; the worksheet UI cannot
--      execute PUT statements directly).
--   4. Verify the file is on the stage with LIST.
--   5. (Optional) Smoke-test the model by hitting the Cortex Analyst REST
--      endpoint with one of the verified queries from `semantic_model.yaml`.
--
-- Snowflake's Cortex Analyst surface uses a **stage-hosted semantic model**.
-- The service is invoked by REST against the warehouse + database + stage +
-- file path; there is no `CREATE CORTEX ANALYST SERVICE` DDL — registration
-- is implicit on first call. This script therefore stages the YAML rather
-- than running a CREATE statement that doesn't exist in the product.
--
-- Re-runnable: the stage uses CREATE OR REPLACE; the PUT overwrites the file.
-- A second run leaves the system in a state byte-identical to the first.
--
-- If a future Snowflake release ships explicit CREATE CORTEX ANALYST DDL
-- (it has been alluded to in roadmap notes but is not GA at the time of
-- writing), the equivalent block is documented in commented form at the
-- bottom of this file. Swap to whichever path the deployment Snowflake
-- account supports.
--
-- Required role: ACCOUNTADMIN (for the stage creation) or any role with
-- USAGE on the database/schema/warehouse plus CREATE STAGE on the schema.
-- Required Snowflake account features: Cortex Analyst enabled. Currently
-- available on AWS-EU (which this project is on) — no extra setup needed.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA CORTEX;


-- ─── 1. Base views must already exist ────────────────────────────────────
-- These are created by `views.sql`. We assert their existence (cheap, fails
-- fast with a clear message if a step was skipped) rather than re-creating
-- them here.
SELECT 'EXAM_PARTS_FLAT exists'        AS check_name, COUNT(*) AS row_count FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
UNION ALL
SELECT 'EXAM_PARTS_BY_TUTORIAL exists' AS check_name, COUNT(*) AS row_count FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL;


-- ─── 2. Internal stage that holds the semantic model YAML ────────────────
-- The stage lives in the CORTEX schema next to the search services. Server-
-- side encryption + directory listing enabled so the analyst service can
-- read the file by path.
CREATE OR REPLACE STAGE GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE
    DIRECTORY = (ENABLE = TRUE)
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    COMMENT = $$
Holds the `lchl_exam_analytics` Cortex Analyst semantic model YAML. The
analyst REST endpoint reads the model from this stage at the path
`semantic_model.yaml`. Per ADR-004 Decision 2.
$$;


-- ─── 3. PUT the semantic model file onto the stage ───────────────────────
-- Run from SnowSQL or a Snowflake Python connector session:
--
--   snowsql -a <account> -u <user> -r ACCOUNTADMIN -w WH_TUTOR \
--           -d GKTUITION_TUTOR -s CORTEX \
--           -f create_analyst_service.sql
--
-- and then in the same SnowSQL session execute:
--
--   PUT file://./semantic_model.yaml
--       @GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE
--       OVERWRITE = TRUE
--       AUTO_COMPRESS = FALSE;
--
-- (PUT cannot run from the worksheet UI — the file system is the local
-- machine running SnowSQL or the connector, not the Snowflake side.)
--
-- The PUT below is commented out because the YAML file lives next to this
-- SQL on the developer machine; dispatching it through a worksheet would
-- fail at the file:// resolution. Uncomment when running via SnowSQL.

/*
PUT file://./semantic_model.yaml
    @GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE
    OVERWRITE = TRUE
    AUTO_COMPRESS = FALSE;
*/


-- ─── 4. Verify the file landed ───────────────────────────────────────────
-- Should return one row with `name = lchl_exam_analytics_stage/semantic_model.yaml`
-- (or similar — depends on the exact stage layout) and `size` > 0.
LIST @GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE;


-- ─── 5. Smoke test — invoke the Analyst REST endpoint ────────────────────
-- The Cortex Analyst REST API is at
--   POST https://<account>.snowflakecomputing.com/api/v2/cortex/analyst/message
-- with a JSON body containing the question and a pointer to the staged
-- semantic model. There is no SQL equivalent for the actual invocation.
--
-- Sample curl for a manual smoke test:
/*
curl -X POST \
     -H "Authorization: Bearer ${SNOWFLAKE_OAUTH_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{
       "messages": [{
         "role": "user",
         "content": [{
           "type": "text",
           "text": "How often has integration by parts appeared on Paper 1 in the last five years?"
         }]
       }],
       "semantic_model_file": "@GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE/semantic_model.yaml"
     }' \
     "https://${SNOWFLAKE_ACCOUNT}.snowflakecomputing.com/api/v2/cortex/analyst/message"
*/
--
-- The response includes a `sql` block. Validate against the warehouse
-- without re-invoking Analyst (saves credits + avoids paid LLM calls in
-- tests) by piping that SQL through:
--
--   EXECUTE IMMEDIATE $$<the returned SQL>$$;


-- ─── Grants ──────────────────────────────────────────────────────────────
-- The FastAPI service role needs USAGE on stage + the database/schema to
-- invoke Analyst. Adjust the role name to whatever the orchestrator uses.
-- Commented out by default — flip on per environment.
/*
GRANT USAGE ON DATABASE GKTUITION_TUTOR              TO ROLE TUTOR_API_ROLE;
GRANT USAGE ON SCHEMA   GKTUITION_TUTOR.CORTEX       TO ROLE TUTOR_API_ROLE;
GRANT READ  ON STAGE    GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE
                                                     TO ROLE TUTOR_API_ROLE;
GRANT SELECT ON VIEW    GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
                                                     TO ROLE TUTOR_API_ROLE;
GRANT SELECT ON VIEW    GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL
                                                     TO ROLE TUTOR_API_ROLE;
GRANT USAGE ON WAREHOUSE WH_TUTOR                    TO ROLE TUTOR_API_ROLE;
*/


-- ============================================================================
-- Forward-compatible alternative (commented) — if Snowflake ships explicit
-- CREATE CORTEX ANALYST SERVICE DDL in a future release, replace the stage-
-- based flow above with the following. The shape mirrors the existing
-- CREATE CORTEX SEARCH SERVICE syntax that Agents 01 and 02 use.
-- ============================================================================
/*
CREATE OR REPLACE CORTEX ANALYST SERVICE LCHL_EXAM_ANALYTICS
    SEMANTIC_MODEL = '@GKTUITION_TUTOR.CORTEX.LCHL_EXAM_ANALYTICS_STAGE/semantic_model.yaml'
    WAREHOUSE      = WH_TUTOR
    COMMENT        = 'Text-to-SQL over LCHL exam-parts. ADR-004 Decision 2.';
*/
