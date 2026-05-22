-- ============================================================================
-- bootstrap_summaries_table.sql
-- ----------------------------------------------------------------------------
-- Defines GKTUITION_TUTOR.RAW.SUMMARIES — one row per strand cram-sheet,
-- sourced from `tutorials/LCHL_<Strand>/_SUMMARY-exam-cram.md`. (The leading
-- underscore is enforced by the canonical filename; the loader still accepts
-- both `_SUMMARY-*.md` and `SUMMARY-*.md` to absorb any future drift in the
-- convention.)
--
-- Authored by Agent 02 per PLAN_PIVOT_DAY_26. Per the architecture review,
-- strand summaries serve a distinct student intent — "I'm cramming X tonight,
-- give me the triage map" — that's poorly served by competing in the same
-- embedding space as either per-tutorial content or per-question solutions.
-- This table backs `CORTEX.SUMMARY_SEARCH`
-- (see create_summary_search_service.sql) so that intent gets its own index.
--
-- The corpus currently has 20 strand summaries (Agent 01's delivery note
-- corroborates this count). The prompt headline of "17" predates the
-- expansion of the Trigonometry strand into Trig 1–4 and the addition of
-- AVM 1 + Induction summaries.
--
-- Idempotent: CREATE OR REPLACE rebuilds the table shell. The loader's MERGE
-- (load_summaries.py, keyed on summary_id) is what makes row-level loads
-- idempotent. Re-run this DDL only when the schema itself needs to change.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.SUMMARIES (
    -- ─── Primary key ───────────────────────────────────────────────────────
    -- Strand-derived slug, e.g. 'summary-the-line', 'summary-algebra',
    -- 'summary-trigonometry-1'. Built by lowercasing the folder name,
    -- replacing '_' with '-', stripping the 'lchl-' prefix, then prepending
    -- 'summary-'. Idempotent across re-runs.
    summary_id                      VARCHAR        NOT NULL,

    -- ─── Identity ─────────────────────────────────────────────────────────
    -- `strand_name` is the human label from the file's H1 line, e.g.
    -- "Algebra", "The Line", "Trigonometry 2 (Unit Circle)".
    -- `strand_folder` is the matching directory name, e.g. "LCHL_The_Line".
    strand_name                     VARCHAR        NOT NULL,
    strand_folder                   VARCHAR        NOT NULL,

    -- ─── Searchable text ──────────────────────────────────────────────────
    -- Full markdown body below the (optional) H1 line. This is the only
    -- text column SUMMARY_SEARCH indexes. Queries like
    --     "I'm cramming The Line tonight what do I need to know"
    -- embed directly against this column.
    body                            TEXT           NOT NULL,

    -- ─── Filterable attributes ────────────────────────────────────────────
    -- Slugs of the top-cited tutorials, in rank order, extracted from the
    -- "📊 Top X tutorials by exam frequency" table inside the summary.
    -- Filterable in SUMMARY_SEARCH so the FastAPI orchestrator can pivot
    -- directly from a summary hit into the related TUTORIALS rows.
    top_tutorials_by_frequency      ARRAY,

    -- ─── Structured metadata (VARIANT — JSON, schema-flexible) ────────────
    -- `exam_frequency_data` mirrors the "📊 Top tutorials by exam frequency"
    -- table. One object per row in that table:
    --   { "rank": 1, "tutorial": "the-line-1", "p2_citations": 28,
    --     "what_it_tests": "Slope, distance, midpoint, …" }
    exam_frequency_data             VARIANT,

    -- `recommended_time_split` mirrors the "⏱ Suggested time split (90 min)"
    -- table. One object per row:
    --   { "activity": "…", "time_text": "20 min", "minutes": 20,
    --     "why": "…" }
    recommended_time_split          VARIANT,

    -- ─── Provenance ───────────────────────────────────────────────────────
    source_path                     VARCHAR,
    loaded_at                       TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_summaries PRIMARY KEY (summary_id)
)
COMMENT = $$
LCHL strand cram-summary sheets, one row per strand. Backs the
SUMMARY_SEARCH Cortex Search Service.

Distinct student intent: "I'm cramming X tonight, give me the triage map."
Keeping summaries in their own search service (rather than mixing them
into TUTOR_SEARCH or SOLUTIONS_SEARCH) keeps the embedding space tight
to that intent and gives the FastAPI orchestrator a clean fan-out path.

Searchable text column (embedded by SUMMARY_SEARCH):
  • body — full markdown of the cram sheet

Filterable attributes: summary_id, strand_name, strand_folder,
top_tutorials_by_frequency.

Structured metadata stored as VARIANT so the JSON shape can evolve
without ALTER TABLE churn:
  • exam_frequency_data    — top-tutorials frequency table, as a list of dicts
  • recommended_time_split — 90-minute time-split table, as a list of dicts

Loader: snowflake/load_summaries.py (idempotent MERGE keyed on summary_id).
$$;

-- ─── Sanity check ──────────────────────────────────────────────────────────
DESC TABLE GKTUITION_TUTOR.RAW.SUMMARIES;
