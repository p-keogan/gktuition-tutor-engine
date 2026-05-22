-- ============================================================================
-- bootstrap_exam_parts_table.sql
-- ----------------------------------------------------------------------------
-- Defines GKTUITION_TUTOR.RAW.EXAM_PARTS — one row per (year × paper × sitting
-- × question × sub-part) cell from the tutorial-style solutions corpus at
-- `tutorials/LCHL_Maths_Exams/Solutions/*.md`. The 30 source files (11 years
-- of main P1+P2 + 4 years of deferred P1+P2) carry ~1,213 `### Q…` headings
-- between them; one heading == one row here.
--
-- Authored by Agent 02 per PLAN_PIVOT_DAY_26 (multi-agent architecture
-- overhaul). The motivating insight: tutorials, exam-paper solutions, and
-- strand cram-summaries have substantively different student intents and
-- belong in three distinct Cortex Search Services. EXAM_PARTS backs
-- `CORTEX.SOLUTIONS_SEARCH` (see create_solutions_search_service.sql) —
-- queries like "how was 2024 P2 Q5 solved" rank against `solution_text` /
-- `question_text` here without contending with the tutorial corpus.
--
-- Multi-field indexing decision: three searchable text columns
-- (`solution_text`, `question_text`, `common_pitfalls`) are kept separate
-- rather than concatenated into one blob, mirroring Agent 01's
-- `title_plus_phrasings`/`body` split on TUTORIALS. A student utterance like
-- "I keep getting the sign wrong on the perpendicular distance formula" hits
-- the pitfalls embedding precisely; embedding it alongside ~6 kB of solution
-- prose would bury it. SOLUTIONS_SEARCH embeds each column independently.
--
-- Idempotent: CREATE OR REPLACE rebuilds the table shell. The loader's MERGE
-- (load_exam_parts.py, keyed on part_id) is what makes row-level loads
-- idempotent. Re-run this DDL only when the schema itself needs to change.
--
-- Required privileges: ACCOUNTADMIN (or any role with USAGE on the database
-- and CREATE TABLE on the RAW schema). The boilerplate `USE ROLE` /
-- `USE WAREHOUSE` block matches bootstrap_tutorials_table.sql.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.EXAM_PARTS (
    -- ─── Primary key ───────────────────────────────────────────────────────
    -- Synthetic, stable, human-readable. Format:
    --   {year}_{sitting}_P{paper}_Q{question_number}{sub_part_path}
    -- where the sub-part path concatenates the letter and any Roman numeral
    -- with no parentheses (so it's filename-safe).
    --   Examples:
    --     2025_main_P1_Q1a       — Q1(a) of 2025 main Paper 1
    --     2024_main_P2_Q5biii    — Q5(b)(iii) of 2024 main Paper 2
    --     2015_main_P1_Q2        — Q2 of 2015 main Paper 1 (no sub-parts)
    --     2023_df_P1_Q4a         — Q4(a) of the 2023 deferred Paper 1
    part_id                         VARCHAR        NOT NULL,

    -- ─── Identity / filterable scalars ─────────────────────────────────────
    year                            NUMBER(4,0)    NOT NULL,   -- 2015–2025
    paper                           NUMBER(1,0)    NOT NULL,   -- 1 or 2
    sitting                         VARCHAR        NOT NULL,   -- 'main' or 'df'
    question_number                 NUMBER(2,0)    NOT NULL,   -- 1–10
    -- Human-friendly sub-part label, e.g. 'a', 'b(i)', 'b(ii)'.
    -- NULL when the question is not sub-divided (only 2015 P1 Q2 today).
    sub_part                        VARCHAR,
    section                         VARCHAR,                   -- 'A' (Q1–Q6) or 'B' (Q7–Q10)
    marks                           NUMBER(3,0),               -- per-part marks (see loader for fallback rules)

    -- ─── Topic tagging ────────────────────────────────────────────────────
    -- `topic` is the human-readable phrase from the part's **Topic:** line,
    -- e.g. 'modulus inequality', 'factor theorem + polynomial long division'.
    -- `secondary_topics` carries the strand names of every tutorial linked
    -- from the **Tutorials:** line (derived from the parent folder, e.g.
    -- LCHL_Algebra → 'Algebra').
    topic                           VARCHAR,
    secondary_topics                ARRAY,

    -- ─── Cross-references (graph traversal) ───────────────────────────────
    -- Tutorial slugs cited on the **Tutorials:** line, in document order.
    -- Same slugs that get written to the appended
    -- `## Cross-references (machine-readable)` YAML block on each source
    -- .md file (idempotently rewritten by load_exam_parts.py).
    tutorials_referenced            ARRAY,

    -- ─── Searchable text columns (embedded separately by SOLUTIONS_SEARCH) ─
    question_text                   TEXT,                       -- the exam prompt
    solution_text                   TEXT,                       -- the tutorial-style worked solution
    common_pitfalls                 TEXT,                       -- 🎯 / 🚨 blockquote callouts, concatenated
    marking_scheme_note             TEXT,                       -- text under `#### Marking-scheme cross-check`

    -- ─── Provenance ───────────────────────────────────────────────────────
    source_path                     VARCHAR,                    -- absolute path of the source .md
    loaded_at                       TIMESTAMP_NTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_exam_parts PRIMARY KEY (part_id)
)
COMMENT = $$
LCHL exam-paper solutions, one row per sub-part across 30 papers
(2015–2025 main + 2022–2025 deferred). Backs the SOLUTIONS_SEARCH Cortex
Search Service.

Searchable text columns (embedded separately by SOLUTIONS_SEARCH):
  • solution_text   — full tutorial-style worked solution prose
  • question_text   — the exam-paper question prompt
  • common_pitfalls — concatenated 🎯/🚨 callouts on the part

Filterable attributes: part_id, year, paper, sitting, question_number,
sub_part, section, marks, topic, secondary_topics, tutorials_referenced.

Loader: snowflake/load_exam_parts.py
  • Idempotent MERGE keyed on part_id.
  • Also (re)writes the `## Cross-references (machine-readable)` YAML
    block at the bottom of each source .md so downstream consumers
    don't have to re-parse the markdown link syntax.

Out of scope for Agent 02:
  • RAW.TUTORIALS.exam_appearances backfill          — owned by Agent 03.
  • Cortex Analyst semantic model on EXAM_PARTS      — owned by Agent 04.
  • Eval-set seeding from EXAM_PARTS cross-refs       — owned by Agent 05.
$$;

-- ─── Sanity check ──────────────────────────────────────────────────────────
DESC TABLE GKTUITION_TUTOR.RAW.EXAM_PARTS;
