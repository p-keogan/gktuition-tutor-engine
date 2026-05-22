-- ============================================================================
-- views.sql
-- ----------------------------------------------------------------------------
-- Cortex Analyst-friendly views over GKTUITION_TUTOR.RAW.EXAM_PARTS.
--
-- Two views, kept independent (no foreign-key relationships in the semantic
-- model) per the AGENT_04 brief:
--
--   1. CORTEX.EXAM_PARTS_FLAT
--        One row per exam part. Adds derived helper columns the analyst
--        layer needs in order to answer trend questions cleanly:
--          • topic_strand          — coarse strand bucket derived from the
--                                    free-form `topic` string and the parent
--                                    folders of `tutorials_referenced`.
--                                    Maps the 1,212 free-form topic strings
--                                    onto the 17 canonical strands used in
--                                    LCHL_exam_trends.md.
--          • tutorial_count        — array length, so "how many tutorials
--                                    does this part cite" is just AVG / SUM.
--          • is_load_bearing       — TRUE if the marking_scheme_note or
--                                    common_pitfalls text flags the part as
--                                    "load-bearing" (matches the methodology
--                                    of LCHL_exam_trends.md).
--          • has_proof_request     — TRUE if question_text begins with
--                                    "Prove" or contains "verify".
--          • is_recent             — year >= 2021 (post-SEC-format-shift).
--
--   2. CORTEX.EXAM_PARTS_BY_TUTORIAL
--        One row per (part × tutorial_slug). Supports tutorial-frequency
--        queries — e.g. "how many times was indices-logs-5 cited on Paper 1
--        since 2020?". Each row also carries `tutorial_strand`, the strand
--        bucket parsed from the slug prefix.
--
-- Idempotent: every CREATE uses OR REPLACE. Safe to rerun.
--
-- Reads from RAW.EXAM_PARTS only. Does not modify RAW.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA CORTEX;


-- ─── 1. EXAM_PARTS_FLAT ────────────────────────────────────────────────────
-- One row per part. The derived columns are deterministic functions of the
-- RAW columns; they exist so the semantic model can expose clean dimensions
-- without forcing the LLM to invent regex on every query.
--
-- DAY_27 (2026-05-22) update — parent-question fallback for topic_strand:
--   The per-row CASE below returns NULL (rather than 'uncategorised') when
--   no strand pattern matches, then `topic_strand` COALESCEs the row's own
--   value with a windowed MAX over the same (year, paper, sitting,
--   question_number) group. This catches deep sub-parts (Q8(d), Q3(b)(i),
--   etc.) where the chunker created a discrete row but the markdown carried
--   the **Topic:** / **Tutorials:** metadata only on the first sub-part.
--   With the loader's question-level inheritance fix (DAY_27 patch in
--   snowflake/load_exam_parts.py) the window-fallback becomes a no-op for
--   freshly-loaded data; it stays in place as belt-and-braces for any row
--   that slipped through and to ensure the view degrades gracefully if a
--   future content edit reintroduces the gap.
CREATE OR REPLACE VIEW GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT AS
WITH per_row AS (
    SELECT
        p.*,
        -- Per-row strand — NULL when no pattern matches (was 'uncategorised'
        -- before the DAY_27 fix). Falling through to NULL lets the outer
        -- COALESCE pick up a sibling's strand via the window-MAX below.
        CASE
            -- Paper 1 strands ---------------------------------------------------
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%algebra-%'
              OR p.topic ILIKE '%factor theorem%'
              OR p.topic ILIKE '%modulus%'
              OR p.topic ILIKE '%inequality%'
              OR p.topic ILIKE '%surd%'
              OR p.topic ILIKE '%simultaneous%'
              OR p.topic ILIKE '%polynomial%'
              OR p.topic ILIKE '%discriminant%'
              OR p.topic ILIKE '%quadratic%'                                  THEN 'algebra'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%differentiation-%'
              OR p.topic ILIKE '%differentiat%'
              OR p.topic ILIKE '%derivative%'
              OR p.topic ILIKE '%turning point%'
              OR p.topic ILIKE '%rate of change%'
              OR p.topic ILIKE '%first principles%'                           THEN 'differentiation'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%integration-%'
              OR p.topic ILIKE '%integrat%'
              OR p.topic ILIKE '%antideriv%'
              OR p.topic ILIKE '%average value%'                              THEN 'integration'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%sequences-series-%'
              OR p.topic ILIKE '%sequence%'
              OR p.topic ILIKE '%series%'
              OR p.topic ILIKE '%geometric%'
              OR p.topic ILIKE '%arithmetic%'                                 THEN 'sequences-series'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%indices-logs-%'
              OR p.topic ILIKE '%indices%'
              OR p.topic ILIKE '%logs%'
              OR p.topic ILIKE '%logarithm%'                                  THEN 'indices-logs'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%complex-numbers-%'
              OR p.topic ILIKE '%complex number%'
              OR p.topic ILIKE '%de moivre%'
              OR p.topic ILIKE '%argand%'
              OR p.topic ILIKE '%polar form%'                                 THEN 'complex-numbers'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%functions-graphs-%'
              OR p.topic ILIKE '%function%'
              OR p.topic ILIKE '%composite%'
              OR p.topic ILIKE '%injective%'
              OR p.topic ILIKE '%inverse function%'                           THEN 'functions-graphs'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%financial-maths-%'
              OR p.topic ILIKE '%financial%'
              OR p.topic ILIKE '%annuit%'
              OR p.topic ILIKE '%amortisation%'
              OR p.topic ILIKE '%compound interest%'                          THEN 'financial-maths'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%induction-%'
              OR p.topic ILIKE '%induction%'                                  THEN 'induction'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%number-theory-%'
              OR p.topic ILIKE '%number theory%'
              OR p.topic ILIKE '%irrational proof%'
              OR p.topic ILIKE '%root 2%'                                     THEN 'number-theory'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%paper-1-proofs-%' THEN 'paper-1-proofs'

            -- Paper 2 strands ---------------------------------------------------
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%probability-%'
              OR p.topic ILIKE '%probabilit%'
              OR p.topic ILIKE '%bernoulli%'
              OR p.topic ILIKE '%expected value%'                             THEN 'probability'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%statistics-%'
              OR p.topic ILIKE '%statistic%'
              OR p.topic ILIKE '%z-score%'
              OR p.topic ILIKE '%z score%'
              OR p.topic ILIKE '%confidence interval%'
              OR p.topic ILIKE '%hypothesis test%'
              OR p.topic ILIKE '%standard normal%'                            THEN 'statistics'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%trigonometry-1-%'
              OR p.topic ILIKE '%trig 1%'
              OR p.topic ILIKE '%sine rule%'
              OR p.topic ILIKE '%cosine rule%'
              OR p.topic ILIKE '%pythagoras%'
              OR p.topic ILIKE '%sohcahtoa%'                                  THEN 'trigonometry-1'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%trigonometry-2-%' THEN 'trigonometry-2'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%trigonometry-3-%' THEN 'trigonometry-3'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%trigonometry-4-%' THEN 'trigonometry-4'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%the-line-%'
              OR p.topic ILIKE '%the line%'
              OR p.topic ILIKE '%perpendicular distance%'
              OR p.topic ILIKE '%slope%'                                      THEN 'the-line'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%the-circle-%'
              OR p.topic ILIKE '%the circle%'
              OR p.topic ILIKE '%tangent to a circle%'                        THEN 'the-circle'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%geometry-1-%'
              OR p.topic ILIKE '%geometry%'
              OR p.topic ILIKE '%similar triangle%'
              OR p.topic ILIKE '%theorem 1%'                                  THEN 'geometry-1'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%avm-1-%'
              OR p.topic ILIKE '%cone%'
              OR p.topic ILIKE '%cylinder%'
              OR p.topic ILIKE '%sphere%'
              OR p.topic ILIKE '%volume%'                                     THEN 'avm-1'
            WHEN ARRAY_TO_STRING(p.tutorials_referenced, ',') ILIKE '%paper-2-proofs-%' THEN 'paper-2-proofs'

            ELSE NULL  -- DAY_27: NULL (not 'uncategorised') so the
                        -- window-COALESCE below can fall back to a sibling.
        END                                                                   AS _row_strand
    FROM GKTUITION_TUTOR.RAW.EXAM_PARTS p
)
SELECT
    -- ─── Identity (verbatim from RAW) ──────────────────────────────────────
    p.part_id,
    p.year,
    p.paper,
    p.sitting,
    p.question_number,
    p.sub_part,
    p.section,
    p.marks,

    -- ─── Free-form topic tagging (verbatim) ────────────────────────────────
    p.topic                                   AS topic_raw,
    p.secondary_topics,
    p.tutorials_referenced,

    -- ─── Searchable text columns (verbatim) ────────────────────────────────
    p.question_text,
    p.solution_text,
    p.common_pitfalls,
    p.marking_scheme_note,

    -- ─── Derived helper columns ────────────────────────────────────────────
    -- topic_strand: own value, else a sibling's, else 'uncategorised'.
    -- The MAX is over a (year, paper, sitting, question_number) window —
    -- i.e. all sub-parts of one question. NULLs are ignored by MAX, so a
    -- deep sub-part that matched nothing inherits the strand of its first
    -- pattern-matching sibling.
    COALESCE(
        p._row_strand,
        MAX(p._row_strand) OVER (
            PARTITION BY p.year, p.paper, p.sitting, p.question_number
        ),
        'uncategorised'
    )                                                                         AS topic_strand,

    -- Convenience: paper-and-strand combined key, useful for grouping. ------
    -- Reuses the same window-fallback as topic_strand above so the two
    -- columns stay consistent for every row.
    p.paper || ':' || COALESCE(
        p._row_strand,
        MAX(p._row_strand) OVER (
            PARTITION BY p.year, p.paper, p.sitting, p.question_number
        ),
        'uncategorised'
    )                                                                     AS paper_strand_key,

    -- Tutorial-count metric — useful for "average tutorials cited per part". -
    COALESCE(ARRAY_SIZE(p.tutorials_referenced), 0)                       AS tutorial_count,

    -- Load-bearing flag — the methodology section of LCHL_exam_trends.md
    -- defines a part as "load-bearing" if the literal phrase appears in the
    -- per-part commentary. We surface the same signal here for analytics.
    (COALESCE(p.common_pitfalls, '') ILIKE '%load-bearing%'
       OR COALESCE(p.marking_scheme_note, '') ILIKE '%load-bearing%'
       OR COALESCE(p.solution_text, '') ILIKE '%load-bearing%')           AS is_load_bearing,

    -- Proof-request flag — the five prescribed P1 proofs + the five P2
    -- prescribed theorems make "Prove that..." questions a distinct class.
    (COALESCE(p.question_text, '') ILIKE 'prove %'
       OR COALESCE(p.question_text, '') ILIKE '%verify%'
       OR COALESCE(p.question_text, '') ILIKE '%show that%')              AS has_proof_request,

    -- Format-shift flag — the SEC moved from ~35 parts/paper to ~45 parts
    -- in 2021. Anything from 2021 onwards is on the new format; this is the
    -- division most cross-year trend questions implicitly want.
    (p.year >= 2021)                                                      AS is_recent,

    -- Provenance (verbatim) -------------------------------------------------
    p.source_path,
    p.loaded_at
FROM per_row p;


-- ─── 2. EXAM_PARTS_BY_TUTORIAL ────────────────────────────────────────────
-- One row per (exam part × cited tutorial). Use this view for any question
-- of the form "how often is tutorial X cited on Paper N since YYYY".
-- Keeping it independent of EXAM_PARTS_FLAT (no joins by default) is
-- intentional: the semantic model declares no relationships between the two
-- tables, which prevents Cortex Analyst from accidentally double-counting
-- parts when a question already targets the by-tutorial grain.
CREATE OR REPLACE VIEW GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL AS
SELECT
    p.part_id,
    p.year,
    p.paper,
    p.sitting,
    p.question_number,
    p.sub_part,
    p.section,
    p.marks,

    -- The exploded tutorial slug — one row per slug per part. --------------
    f.value::STRING                           AS tutorial_slug,

    -- Strand bucket derived from the slug prefix. The slugs are namespaced
    -- by strand (e.g. `differentiation-15-turning-points-max-min`), so a
    -- simple SPLIT_PART on '-' for the first 1-2 segments is reliable.
    CASE
        WHEN f.value::STRING ILIKE 'algebra-%'                  THEN 'algebra'
        WHEN f.value::STRING ILIKE 'differentiation-%'          THEN 'differentiation'
        WHEN f.value::STRING ILIKE 'integration-%'              THEN 'integration'
        WHEN f.value::STRING ILIKE 'sequences-series-%'         THEN 'sequences-series'
        WHEN f.value::STRING ILIKE 'indices-logs-%'             THEN 'indices-logs'
        WHEN f.value::STRING ILIKE 'complex-numbers-%'          THEN 'complex-numbers'
        WHEN f.value::STRING ILIKE 'functions-graphs-%'         THEN 'functions-graphs'
        WHEN f.value::STRING ILIKE 'financial-maths-%'          THEN 'financial-maths'
        WHEN f.value::STRING ILIKE 'induction-%'                THEN 'induction'
        WHEN f.value::STRING ILIKE 'number-theory-%'            THEN 'number-theory'
        WHEN f.value::STRING ILIKE 'paper-1-proofs-%'           THEN 'paper-1-proofs'
        WHEN f.value::STRING ILIKE 'probability-%'              THEN 'probability'
        WHEN f.value::STRING ILIKE 'statistics-%'               THEN 'statistics'
        WHEN f.value::STRING ILIKE 'trigonometry-1-%'           THEN 'trigonometry-1'
        WHEN f.value::STRING ILIKE 'trigonometry-2-%'           THEN 'trigonometry-2'
        WHEN f.value::STRING ILIKE 'trigonometry-3-%'           THEN 'trigonometry-3'
        WHEN f.value::STRING ILIKE 'trigonometry-4-%'           THEN 'trigonometry-4'
        WHEN f.value::STRING ILIKE 'the-line-%'                 THEN 'the-line'
        WHEN f.value::STRING ILIKE 'the-circle-%'               THEN 'the-circle'
        WHEN f.value::STRING ILIKE 'geometry-1-%'               THEN 'geometry-1'
        WHEN f.value::STRING ILIKE 'avm-1-%'                    THEN 'avm-1'
        WHEN f.value::STRING ILIKE 'paper-2-proofs-%'           THEN 'paper-2-proofs'
        ELSE 'uncategorised'
    END                                       AS tutorial_strand,

    p.topic                                   AS topic_raw,
    p.source_path,
    p.loaded_at
FROM GKTUITION_TUTOR.RAW.EXAM_PARTS p,
     LATERAL FLATTEN(input => p.tutorials_referenced) f;


-- ─── Sanity checks ────────────────────────────────────────────────────────
-- These run only on a row-count basis; they don't assert anything that
-- depends on data Agent 02 hasn't loaded yet. They're cheap so leaving them
-- in is fine.
SELECT 'EXAM_PARTS_FLAT row count'        AS check_name, COUNT(*) AS n FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
UNION ALL
SELECT 'EXAM_PARTS_BY_TUTORIAL row count' AS check_name, COUNT(*) AS n FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_BY_TUTORIAL
UNION ALL
SELECT 'Distinct topic_strand values'     AS check_name, COUNT(DISTINCT topic_strand) AS n FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT
UNION ALL
SELECT 'Uncategorised parts (should be small / zero)' AS check_name,
       COUNT(*) FILTER (WHERE topic_strand = 'uncategorised') AS n
  FROM GKTUITION_TUTOR.CORTEX.EXAM_PARTS_FLAT;
