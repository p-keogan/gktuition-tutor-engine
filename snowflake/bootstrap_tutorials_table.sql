-- ============================================================================
-- bootstrap_tutorials_table.sql
-- ----------------------------------------------------------------------------
-- Defines GKTUITION_TUTOR.RAW.TUTORIALS — the per-tutorial table that powers
-- the TUTOR_SEARCH Cortex Search Service and is the JOIN target for every
-- citation that the AI tutor returns.
--
-- Multi-field indexing decision (per architecture review, DAY_26 pivot):
--   `title_plus_phrasings` and `body` are kept as separate searchable text
--   columns rather than one concatenated blob. The Cortex Search Service
--   embeds each column independently, so a student utterance like
--      "I got two answers for a, which one is right"
--   hits `title_plus_phrasings` near-verbatim (precision route) while the
--   `body` embedding handles paragraph-level grounding once a tutorial is
--   selected (recall route). Concatenating both into one blob would dilute
--   the student-phrasing signal under 4–6 kB of transcript-grade prose.
--
-- Forward-looking columns (`exam_appearances`, `learning_work`,
-- `companion_practice_questions`) default to empty arrays. Per SCHEMA.md
-- these are populated incrementally — Agent 03 backfills exam_appearances
-- from EXAM_PARTS cross-references; learning_work + companion_practice_*
-- are hand-curated in YAML.
--
-- Idempotent: CREATE OR REPLACE wipes and rebuilds. The Python loader's MERGE
-- is what makes the *load* idempotent. Re-running this SQL drops existing
-- rows — only do it when the schema itself changes.
-- ============================================================================

USE ROLE ACCOUNTADMIN;
USE WAREHOUSE WH_TUTOR;
USE DATABASE GKTUITION_TUTOR;
USE SCHEMA RAW;

CREATE OR REPLACE TABLE GKTUITION_TUTOR.RAW.TUTORIALS (
    -- ─── Primary key ───────────────────────────────────────────────────────
    slug                            VARCHAR        NOT NULL,

    -- ─── Identity (YAML `video_id`, `title`) ───────────────────────────────
    video_id                        VARCHAR        NOT NULL,
    title                           VARCHAR        NOT NULL,

    -- ─── Searchable text columns ──────────────────────────────────────────
    -- `title_plus_phrasings` is short, dense, student-language: title +
    -- keywords[] + common_student_phrasings[], newline-joined, hard-capped
    -- at 4000 characters. This is the precision-retrieval column.
    title_plus_phrasings            TEXT           NOT NULL,
    -- `body` is the full markdown content below the YAML frontmatter — the
    -- recall column for paragraph-grounded answers.
    body                            TEXT           NOT NULL,
    -- `warnings_and_gotchas` carries content_warnings[] as a third
    -- searchable field. Kept separate because pedagogical warnings (🚨, 🎯)
    -- are the only place explicit misconception language lives, and
    -- diluting them with the body embedding hides them.
    warnings_and_gotchas            TEXT,

    -- ─── Filterable attributes ────────────────────────────────────────────
    -- Cortex Search supports filtering on top-level attributes; arrays
    -- become multi-value filters at search time. Kebab-tokens throughout.
    techniques                      ARRAY,          -- techniques_taught ∪ techniques_used
    course_levels                   ARRAY,          -- e.g. ['LCHL']
    paper                           NUMBER(1,0),    -- 1 or 2
    topic                           VARCHAR,        -- e.g. 'coordinate-geometry-line'
    subtopic                        VARCHAR,        -- e.g. 'area-of-triangle-coordinate-geometry'
    sequence_number                 NUMBER(4,0),    -- position within strand
    duration_seconds                NUMBER(6,0),
    youtube_url                     VARCHAR,
    gktuition_url                   VARCHAR,

    -- ─── Cross-references (for graph traversal at response-build time) ────
    prerequisites                   ARRAY,          -- list of video_ids
    forward_links                   ARRAY,          -- list of video_ids
    xref                            ARRAY,          -- list of video_ids

    -- ─── Log tables (full structured payload per SCHEMA) ──────────────────
    log_tables                      VARIANT,

    -- ─── Syllabus tagging ─────────────────────────────────────────────────
    syllabus_strand                 NUMBER(2,0),
    syllabus_section                VARCHAR,
    syllabus_reference              VARCHAR,

    -- ─── Forward-looking fields (per SCHEMA.md DAY_19, ADR-003) ───────────
    -- These three columns are declared NOW so Agents 03 + future curation
    -- can populate them without a schema migration. Default empty array.
    exam_appearances                VARIANT,        -- backfilled by Agent 03
    learning_work                   VARIANT,        -- hand-curated in YAML
    companion_practice_questions    VARIANT,        -- hand-curated, schoolbook strategy

    -- ─── Provenance ───────────────────────────────────────────────────────
    source_path                     VARCHAR,
    loaded_at                       TIMESTAMP_NTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP(),

    CONSTRAINT pk_tutorials PRIMARY KEY (slug)
)
COMMENT = $$
GKTuition tutorial corpus, one row per canonical LCHL tutorial.

Searchable text columns (embedded separately by TUTOR_SEARCH):
  • title_plus_phrasings — title + keywords[] + common_student_phrasings[]
                           (precision route, ≤ 4000 chars)
  • body                 — full markdown below the YAML frontmatter
                           (recall route, paragraph grounding)
  • warnings_and_gotchas — content_warnings[] newline-joined
                           (load-bearing misconception language)

Filterable attributes: slug, title, topic, subtopic, paper, course_levels,
techniques, sequence_number, youtube_url, gktuition_url.

Forward-looking columns default to empty arrays — populated incrementally
per SCHEMA.md (Agent 03 backfills exam_appearances; learning_work and
companion_practice_questions are hand-curated).

Loader: snowflake/load_tutorials.py (idempotent MERGE keyed on slug).
$$;

-- ─── Sanity check ──────────────────────────────────────────────────────────
DESC TABLE GKTUITION_TUTOR.RAW.TUTORIALS;
