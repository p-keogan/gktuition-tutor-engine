-- ============================================================================
-- bootstrap_eval_table.sql
-- ----------------------------------------------------------------------------
-- Defines GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET — the offline retrieval-quality
-- evaluation table that backs score_against_cortex_search.py and the Week 13
-- "≥80% precision@1" milestone.
--
-- Each row is a (question_text, expected_slug) pair, bootstrapped without
-- human curation from two corpus sources:
--
--   • source = 'phrasings'           — every entry in every tutorial's
--                                       common_student_phrasings[] frontmatter
--                                       field becomes one row. The
--                                       expected_slug is that tutorial's own
--                                       slug. Each phrasing is, by definition,
--                                       a retrieval target the tutorial claims
--                                       to answer.
--
--   • source = 'solution_cross_ref'  — every (EXAM_PARTS row × tutorial in its
--                                       tutorials_referenced[]) pair. The
--                                       question_text is the exam part's
--                                       prompt; the expected_slug is the
--                                       cross-referenced tutorial.
--
-- Authored by Agent 05 per PLAN_PIVOT_DAY_26 (multi-agent architecture
-- overhaul). The Week 13 milestone of "≥ 200 hand-curated golden questions"
-- collapses to "filter ~200 from this auto-generated set of ≥ 1,500",
-- swapping a multi-week curation slog for a quick filtering pass.
--
-- Idempotency: CREATE OR REPLACE wipes and rebuilds the table shell. The
-- Python loader's MERGE (build_eval_set.py, keyed on eval_id) is what makes
-- the row-level load idempotent. Re-run this SQL only when the schema itself
-- changes.
--
-- Required privileges: ACCOUNTADMIN (or any role with USAGE on the database
-- and CREATE TABLE on the RAW schema). Reuses the warehouse / database /
-- schemas Agent 01 already stood up (WH_TUTOR, GKTUITION_TUTOR, RAW).
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET (
    -- ─── Primary key ───────────────────────────────────────────────────────
    -- Synthetic, stable, human-readable. Two patterns:
    --   phr_{tutorial_slug}_{NNN}            — phrasings rows (NNN = 001+)
    --   xref_{part_id}_{expected_slug}       — solution-cross-ref rows
    -- Examples:
    --   phr_the-line-4-area-of-triangle_007
    --   xref_2024_main_P1_Q1a_algebra-17-surd-equations
    eval_id                  VARCHAR        NOT NULL,

    -- ─── Eval-pair payload ────────────────────────────────────────────────
    -- The natural-language query a student might issue (phrasing) or the
    -- exam-paper prompt (cross-ref). Sent verbatim to the Cortex Search
    -- Service at scoring time.
    question_text            TEXT           NOT NULL,
    -- The tutorial slug we *expect* to be returned in the top-K. Always a
    -- slug from RAW.TUTORIALS (i.e. a canonical tutorial — never a
    -- Paper-Proofs cross-ref file).
    expected_slug            VARCHAR        NOT NULL,

    -- ─── Provenance ───────────────────────────────────────────────────────
    -- Which bootstrap channel emitted the row. Always one of:
    --   'phrasings' | 'solution_cross_ref'
    source                   VARCHAR        NOT NULL,
    -- For solution_cross_ref: { part_id, year, paper, sitting,
    -- question_number, sub_part, n_tutorials_for_part }.
    -- For phrasings: { phrasing_index, topic, paper }.
    source_metadata          VARIANT,
    -- Auto-tiered difficulty for stratified golden-subset selection.
    --   'auto-easy'   — short phrasings; cross-refs from recent main sittings
    --   'auto-medium' — longer phrasings; cross-refs from mid-history papers
    --   'auto-hard'   — deferred sittings, multi-tutorial parts (>2 refs),
    --                   phrasings from low-frequency strands
    -- The phrasings rows default to 'auto-easy' for the simplest tier and
    -- 'auto-medium' once they exceed ~60 characters. Cross-refs default to
    -- 'auto-medium' and bump to 'auto-hard' under the rules above.
    difficulty               VARCHAR,

    -- ─── Curation flags ───────────────────────────────────────────────────
    -- Set TRUE once a human has eyeballed the pair and confirmed it makes
    -- sense (no obvious mismatch). Defaults to FALSE so the auto-rows are
    -- distinguishable from the curated ones.
    is_manually_reviewed     BOOLEAN        DEFAULT FALSE,
    -- Marked TRUE by select_golden_subset.py for the ~200-row subset that
    -- backs the Week 13 ≥ 80% precision@1 milestone. The full set is for
    -- breadth analysis; the golden subset is the headline number.
    is_in_golden_subset      BOOLEAN        DEFAULT FALSE,

    -- ─── Provenance ───────────────────────────────────────────────────────
    created_at               TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_eval_golden_set PRIMARY KEY (eval_id)
)
COMMENT = $$
Offline retrieval-quality evaluation set for the GKTuition AI tutor.

One row per (question_text, expected_slug) pair. Two bootstrap sources:
  • 'phrasings'           — common_student_phrasings[] × tutorial.slug
  • 'solution_cross_ref'  — EXAM_PARTS.question_text × tutorials_referenced[]

Idempotent MERGE keyed on eval_id (build_eval_set.py).

Scoring (score_against_cortex_search.py) computes per-row precision@1,
recall@5, and MRR against TUTOR_SEARCH (phrasings) and SOLUTIONS_SEARCH
(cross-refs), aggregating overall and by source / topic.

is_in_golden_subset = TRUE marks the ~200-row golden subset selected by
select_golden_subset.py for the Week 13 milestone. Stratified ~50 easy /
~100 medium / ~50 hard.
$$;

-- ─── Sanity check ──────────────────────────────────────────────────────────
DESC TABLE GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET;
