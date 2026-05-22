#!/usr/bin/env python3
"""Bootstrap GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET from the corpus + EXAM_PARTS.

Two bootstrap sources land in the same table. Both are deterministic and
idempotent — re-running emits byte-identical row dicts, the MERGE is keyed on
the synthetic ``eval_id``.

* ``--source tutorials``  — walk ``tutorials/LCHL_*/*.md``, parse each YAML
  frontmatter, emit one row per entry in ``common_student_phrasings[]``. The
  ``expected_slug`` is the tutorial's own ``slug``.
* ``--source solutions``  — read EXAM_PARTS (live Snowflake) **or** parse the
  ``## Cross-references (machine-readable)`` YAML blocks Agent 02 appended to
  every solutions ``.md`` (``--from-files``). Emit one row per
  (part × tutorial in ``tutorials_referenced[]``); the part's question prompt
  is the ``question_text``; the referenced tutorial slug is the
  ``expected_slug``.
* ``--source all``        — default: both of the above.

Usage
-----
::

    # Both sources, parse cross-refs from disk (no Snowflake creds needed):
    python build_eval_set.py --from-files

    # Only the phrasings half:
    python build_eval_set.py --source tutorials --from-files

    # Walk + parse only; print counts; don't MERGE; still write the CSV:
    python build_eval_set.py --dry-run --from-files

    # Live (reads EXAM_PARTS from Snowflake) + writes back to RAW.EVAL_GOLDEN_SET:
    python build_eval_set.py --source all

Outputs
-------
* MERGE into ``GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET`` (unless ``--dry-run``).
* CSV at ``gktuition-tutor-engine/eval/eval_golden_set.csv`` (always — this is
  the portable artefact committed to the repo so the eval can run without
  Snowflake access).

Environment variables (live mode only)
--------------------------------------
::

    SNOWFLAKE_ACCOUNT     required
    SNOWFLAKE_USER        required
    SNOWFLAKE_PASSWORD    or SNOWFLAKE_PRIVATE_KEY_PATH
    SNOWFLAKE_ROLE        default = 'ACCOUNTADMIN'
    SNOWFLAKE_WAREHOUSE   default = 'WH_TUTOR'
    SNOWFLAKE_DATABASE    default = 'GKTUITION_TUTOR'
    SNOWFLAKE_SCHEMA      default = 'RAW'

Design notes
------------
* Difficulty tiering is intentionally coarse — it's only used by
  ``select_golden_subset.py`` for stratified sampling, not by the scoring
  surface. Easy = the trivial case; medium = the realistic everyday case;
  hard = deferred sittings, multi-tutorial parts (>2 refs), or phrasings
  from low-frequency strands.
* ``expected_slug`` is validated against the set of slugs walked from the
  tutorial corpus. Rows whose expected slug doesn't correspond to a real
  tutorial are dropped with a WARN log — this catches stale cross-references
  to renamed tutorials.
* Source-file parsing reuses ``snowflake/load_exam_parts.py`` (its
  ``parse_solutions_file`` already chunks parts and extracts
  ``tutorials_referenced`` from the markdown links). We import it via the
  sibling directory; no duplication.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

# ───────────────────────────────────────────────────────────────────────────
# Path setup — allow importing the Agent 02 parser from sibling snowflake/
# ───────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
SNOWFLAKE_DIR = REPO_ROOT / "snowflake"
if str(SNOWFLAKE_DIR) not in sys.path:
    sys.path.insert(0, str(SNOWFLAKE_DIR))

# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_eval_set")


# ───────────────────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────────────────
DEFAULT_TUTORIALS_ROOT = (
    REPO_ROOT.parent / "career-transition-2026" / "tutorials"
)
DEFAULT_SOLUTIONS_DIR = (
    REPO_ROOT.parent / "career-transition-2026" / "tutorials" /
    "LCHL_Maths_Exams" / "Solutions"
)
CSV_OUT = HERE / "eval_golden_set.csv"

# A phrasing longer than this is bumped from auto-easy to auto-medium.
EASY_PHRASING_CHAR_CAP = 60

# Strands considered "low-frequency" for hard-tier promotion of phrasings.
# Inferred from the AGENT_02 trends report — the strands with the fewest
# exam appearances historically also have the smallest tutorial sets.
LOW_FREQUENCY_TOPICS = {
    "induction",
    "number-theory",
    "trigonometry-3",
    "trigonometry-4",
    "complex-numbers-de-moivre",  # narrow sub-strand of the broader CN strand
    "financial-maths",
}

# Deferred sittings auto-promote cross-ref difficulty to hard.
DEFERRED_SITTING = "df"

# YAML frontmatter splitter — same regex Agent 01 + 02 use.
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Three tutorials author modulus signs as bare `- |z1 z2| = ...` list items
# in YAML, which PyYAML interprets as a block-scalar header and rejects. We
# apply the same pre-processing Agent 01's load_tutorials.py uses: wrap such
# list-item values in single quotes before parsing. Per the prompt, no source
# .md file is modified.
_BARE_PIPE_LIST_ITEM = re.compile(r"^(\s*-\s+)(\|[^\n]+)$", re.MULTILINE)
_BLOCK_SCALAR_HEADER = re.compile(r"^\|[\+\-]?\d*\s*$")


def _preprocess_yaml(fm_raw: str) -> str:
    """Wrap bare-pipe list-item values in single quotes so PyYAML treats them
    as strings rather than block-scalar literals. See Agent 01's note."""
    def _quote(match: re.Match[str]) -> str:
        prefix, value = match.group(1), match.group(2)
        if _BLOCK_SCALAR_HEADER.match(value):
            return match.group(0)  # genuine block-scalar header
        escaped = value.replace("'", "''")
        return f"{prefix}'{escaped}'"

    return _BARE_PIPE_LIST_ITEM.sub(_quote, fm_raw)

# Column order — kept aligned with bootstrap_eval_table.sql so the
# INSERT / MERGE column lists match.
COLS_SCALAR = [
    "eval_id",
    "question_text",
    "expected_slug",
    "source",
    "difficulty",
]
COLS_VARIANT = [
    "source_metadata",
]
COLS_BOOL = [
    "is_manually_reviewed",
    "is_in_golden_subset",
]
ALL_COLS = COLS_SCALAR + COLS_VARIANT + COLS_BOOL


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class EvalRow:
    eval_id: str
    question_text: str
    expected_slug: str
    source: str
    source_metadata: dict[str, Any]
    difficulty: str
    is_manually_reviewed: bool = False
    is_in_golden_subset: bool = False


@dataclass
class BuildReport:
    tutorials_walked: int = 0
    tutorials_with_phrasings: int = 0
    phrasings_rows: int = 0
    exam_parts_seen: int = 0
    xref_rows_total: int = 0
    xref_rows_dropped_stale_slug: int = 0
    csv_rows_written: int = 0
    snowflake_inserted: int = 0
    snowflake_updated: int = 0
    valid_tutorial_slugs: set[str] = field(default_factory=set)


# ───────────────────────────────────────────────────────────────────────────
# YAML / corpus helpers
# ───────────────────────────────────────────────────────────────────────────
def split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    """Return (yaml_dict, body) or None if there's no YAML frontmatter."""
    m = FM_RE.match(text)
    if not m:
        return None
    fm_raw = _preprocess_yaml(m.group(1))
    try:
        data = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(
            f"YAML frontmatter is not a mapping (got {type(data).__name__})"
        )
    return data, m.group(2)


def _as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def slugify_part(s: str) -> str:
    """Filename-safe form for embedding into eval_id values."""
    return re.sub(r"[^a-z0-9_-]", "", s.lower().replace(" ", "-"))


def walk_tutorial_slugs(tutorials_root: Path) -> dict[str, dict[str, Any]]:
    """Walk ``LCHL_*/*.md`` and return a {slug: frontmatter_dict} map for every
    file that carries a top-level ``slug``. This is the source of truth for
    "is this a real tutorial that can be an expected_slug?".

    Mirrors Agent 01's skip rules: ``_SUMMARY-*.md``, ``README.md``, and any
    file without a ``slug`` field is excluded.
    """
    result: dict[str, dict[str, Any]] = {}
    if not tutorials_root.is_dir():
        raise FileNotFoundError(f"tutorials root not found: {tutorials_root}")

    for strand_dir in sorted(tutorials_root.glob("LCHL_*")):
        if not strand_dir.is_dir():
            continue
        for md in sorted(strand_dir.glob("*.md")):
            name = md.name
            if name.startswith("_SUMMARY-") or name == "README.md":
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except OSError as exc:
                log.warning("read error on %s: %s", md, exc)
                continue
            try:
                parsed = split_frontmatter(text)
            except ValueError as exc:
                log.warning("YAML error in %s: %s", md, exc)
                continue
            if parsed is None:
                continue
            fm, _ = parsed
            slug = fm.get("slug")
            if not slug:
                continue
            fm["__source_path__"] = str(md)
            result[slug] = fm

    return result


# ───────────────────────────────────────────────────────────────────────────
# Phrasings → rows
# ───────────────────────────────────────────────────────────────────────────
def _classify_phrasing_difficulty(phrasing: str, topic: str | None) -> str:
    """Tier a phrasing into auto-easy / auto-medium / auto-hard.

    * Hard:    topic is in LOW_FREQUENCY_TOPICS.
    * Medium:  phrasing exceeds EASY_PHRASING_CHAR_CAP characters.
    * Easy:    everything else.
    """
    if topic and topic in LOW_FREQUENCY_TOPICS:
        return "auto-hard"
    if len(phrasing) > EASY_PHRASING_CHAR_CAP:
        return "auto-medium"
    return "auto-easy"


def build_phrasings_rows(
    tutorial_frontmatters: dict[str, dict[str, Any]],
    report: BuildReport,
) -> list[EvalRow]:
    """One EvalRow per (tutorial × common_student_phrasings entry)."""
    rows: list[EvalRow] = []

    for slug in sorted(tutorial_frontmatters):
        fm = tutorial_frontmatters[slug]
        report.tutorials_walked += 1
        phrasings = _as_list(fm.get("common_student_phrasings"))
        if not phrasings:
            continue
        report.tutorials_with_phrasings += 1

        topic = fm.get("topic")
        paper = fm.get("paper")

        # Deduplicate within a tutorial (the corpus has occasional repeats)
        # while preserving order.
        seen_local: set[str] = set()
        idx = 0
        for raw in phrasings:
            phrasing = str(raw).strip()
            if not phrasing or phrasing in seen_local:
                continue
            seen_local.add(phrasing)
            idx += 1
            difficulty = _classify_phrasing_difficulty(phrasing, topic)
            rows.append(
                EvalRow(
                    eval_id=f"phr_{slug}_{idx:03d}",
                    question_text=phrasing,
                    expected_slug=slug,
                    source="phrasings",
                    source_metadata={
                        "phrasing_index": idx,
                        "topic": topic,
                        "paper": paper,
                    },
                    difficulty=difficulty,
                )
            )
        report.phrasings_rows += idx

    return rows


# ───────────────────────────────────────────────────────────────────────────
# Solution cross-refs → rows (from-files mode)
# ───────────────────────────────────────────────────────────────────────────
def _classify_xref_difficulty(
    sitting: str,
    n_tutorials: int,
    year: int,
) -> str:
    """Tier a cross-ref pair into auto-easy / auto-medium / auto-hard.

    * Hard:    deferred sitting OR n_tutorials > 2.
    * Medium:  recent main sitting (year >= 2022).
    * Easy:    older main sitting with a single linked tutorial.
    """
    if sitting == DEFERRED_SITTING:
        return "auto-hard"
    if n_tutorials > 2:
        return "auto-hard"
    if year >= 2022 and n_tutorials >= 2:
        return "auto-medium"
    if year >= 2022:
        return "auto-medium"
    if n_tutorials >= 2:
        return "auto-medium"
    return "auto-easy"


def build_xref_rows_from_files(
    solutions_dir: Path,
    valid_slugs: set[str],
    report: BuildReport,
) -> list[EvalRow]:
    """Parse every solutions ``.md`` via Agent 02's ``parse_solutions_file``
    and emit one EvalRow per (part × tutorial)."""
    try:
        import load_exam_parts as lep  # type: ignore  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "Could not import load_exam_parts. Ensure the eval/ directory is a "
            "sibling of snowflake/ in gktuition-tutor-engine/."
        ) from exc

    if not solutions_dir.is_dir():
        raise FileNotFoundError(f"solutions dir not found: {solutions_dir}")

    rows: list[EvalRow] = []
    files = sorted(
        p for p in solutions_dir.glob("*.md")
        if p.name not in lep.SKIP_NAMES and not p.name.startswith(lep.SKIP_PREFIXES)
    )
    log.info("Parsing %d solutions files via load_exam_parts.parse_solutions_file",
             len(files))

    for path in files:
        try:
            parts = lep.parse_solutions_file(path)
        except Exception as exc:  # noqa: BLE001
            log.warning("Skipping %s: %s", path.name, exc)
            continue
        for part in parts:
            report.exam_parts_seen += 1
            if not part.question_text or not part.tutorials_referenced:
                continue
            n_refs = len(part.tutorials_referenced)
            difficulty = _classify_xref_difficulty(
                sitting=part.sitting, n_tutorials=n_refs, year=part.year
            )
            for slug in part.tutorials_referenced:
                if slug not in valid_slugs:
                    # Cross-ref to a non-canonical slug (e.g. a Paper-Proofs
                    # file Agent 01 deliberately skips, or a renamed tutorial).
                    # Drop with a counted WARN — keeps the eval set honest.
                    report.xref_rows_dropped_stale_slug += 1
                    continue
                rows.append(
                    EvalRow(
                        eval_id=f"xref_{part.part_id}_{slug}",
                        question_text=part.question_text,
                        expected_slug=slug,
                        source="solution_cross_ref",
                        source_metadata={
                            "part_id": part.part_id,
                            "year": part.year,
                            "paper": part.paper,
                            "sitting": part.sitting,
                            "question_number": part.question_number,
                            "sub_part": part.sub_part,
                            "n_tutorials_for_part": n_refs,
                            "topic": part.topic,
                        },
                        difficulty=difficulty,
                    )
                )

    report.xref_rows_total = len(rows)
    return rows


def build_xref_rows_from_snowflake(
    valid_slugs: set[str],
    report: BuildReport,
) -> list[EvalRow]:
    """Read EXAM_PARTS via the Snowflake connector and emit one EvalRow per
    (part × tutorial). Schema matches ``bootstrap_exam_parts_table.sql``."""
    try:
        import snowflake.connector  # noqa: PLC0415
        # The bulk-insert SQL uses qmark `?` placeholders rather than the
        # connector's default pyformat `%s`. Set process-wide before connect.
        snowflake.connector.paramstyle = "qmark"
    except ImportError as exc:
        raise RuntimeError(
            "snowflake-connector-python is required for --source solutions "
            "without --from-files. Install it or use --from-files."
        ) from exc

    conn_kwargs = _build_conn_kwargs()
    log.info("Reading EXAM_PARTS from Snowflake (account=%s)",
             conn_kwargs.get("account"))
    conn = snowflake.connector.connect(**conn_kwargs)
    try:
        cs = conn.cursor()
        try:
            cs.execute(
                """
                SELECT part_id, year, paper, sitting, question_number, sub_part,
                       question_text, topic, tutorials_referenced
                FROM GKTUITION_TUTOR.RAW.EXAM_PARTS
                WHERE question_text IS NOT NULL
                  AND tutorials_referenced IS NOT NULL
                """
            )
            rows: list[EvalRow] = []
            for (
                part_id, year, paper, sitting, qnum, sub_part,
                question_text, topic, tutorials_raw,
            ) in cs:
                report.exam_parts_seen += 1
                tutorials_referenced = (
                    json.loads(tutorials_raw)
                    if isinstance(tutorials_raw, str) else (tutorials_raw or [])
                )
                if not tutorials_referenced:
                    continue
                n_refs = len(tutorials_referenced)
                difficulty = _classify_xref_difficulty(
                    sitting=sitting, n_tutorials=n_refs, year=int(year)
                )
                for slug in tutorials_referenced:
                    if slug not in valid_slugs:
                        report.xref_rows_dropped_stale_slug += 1
                        continue
                    rows.append(
                        EvalRow(
                            eval_id=f"xref_{part_id}_{slug}",
                            question_text=question_text,
                            expected_slug=slug,
                            source="solution_cross_ref",
                            source_metadata={
                                "part_id": part_id,
                                "year": int(year),
                                "paper": int(paper),
                                "sitting": sitting,
                                "question_number": int(qnum),
                                "sub_part": sub_part,
                                "n_tutorials_for_part": n_refs,
                                "topic": topic,
                            },
                            difficulty=difficulty,
                        )
                    )
        finally:
            cs.close()
    finally:
        conn.close()

    report.xref_rows_total = len(rows)
    return rows


# ───────────────────────────────────────────────────────────────────────────
# CSV writer (committed artefact)
# ───────────────────────────────────────────────────────────────────────────
CSV_FIELDS = [
    "eval_id",
    "question_text",
    "expected_slug",
    "source",
    "source_metadata",
    "difficulty",
    "is_manually_reviewed",
    "is_in_golden_subset",
]


def write_csv(rows: list[EvalRow], path: Path) -> int:
    """Overwrite ``path`` with the canonical CSV form of ``rows``.

    Sorted by eval_id for stable diffs."""
    sorted_rows = sorted(rows, key=lambda r: r.eval_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in sorted_rows:
            writer.writerow(
                {
                    "eval_id": r.eval_id,
                    "question_text": r.question_text,
                    "expected_slug": r.expected_slug,
                    "source": r.source,
                    "source_metadata": json.dumps(r.source_metadata, sort_keys=True),
                    "difficulty": r.difficulty,
                    "is_manually_reviewed": "TRUE" if r.is_manually_reviewed else "FALSE",
                    "is_in_golden_subset": "TRUE" if r.is_in_golden_subset else "FALSE",
                }
            )
    return len(sorted_rows)


# ───────────────────────────────────────────────────────────────────────────
# Snowflake MERGE — mirrors load_tutorials.py's staging-table pattern
# ───────────────────────────────────────────────────────────────────────────
def _build_conn_kwargs() -> dict[str, Any]:
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    if not account or not user:
        raise RuntimeError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set for live runs. "
            "Use --dry-run if you only want CSV output."
        )
    kw: dict[str, Any] = {
        "account": account,
        "user": user,
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "WH_TUTOR"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "GKTUITION_TUTOR"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "RAW"),
        "client_session_keep_alive": False,
    }
    if pk_path := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        kw["private_key_file"] = pk_path
        kw["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT")
    elif password := os.environ.get("SNOWFLAKE_PASSWORD"):
        kw["password"] = password
    else:
        raise RuntimeError(
            "Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH must be set."
        )
    return kw


def _row_to_params(row: EvalRow) -> list[Any]:
    return [
        row.eval_id,
        row.question_text,
        row.expected_slug,
        row.source,
        row.difficulty,
        json.dumps(row.source_metadata or {}),
        bool(row.is_manually_reviewed),
        bool(row.is_in_golden_subset),
    ]


def _build_staging_insert_sql(staging_fqn: str, n_rows: int) -> str:
    """One INSERT ... SELECT ... FROM VALUES (?,?, ...), (?,?, ...) — VARIANT
    columns wrapped in PARSE_JSON, mirroring load_exam_parts.py."""
    select_exprs: list[str] = []
    column_names: list[str] = []
    idx = 1
    for c in COLS_SCALAR:
        select_exprs.append(f"${idx}")
        column_names.append(c)
        idx += 1
    for c in COLS_VARIANT:
        select_exprs.append(f"PARSE_JSON(${idx})")
        column_names.append(c)
        idx += 1
    for c in COLS_BOOL:
        select_exprs.append(f"${idx}")
        column_names.append(c)
        idx += 1

    ncols = len(ALL_COLS)
    row_placeholder = "(" + ",".join(["?"] * ncols) + ")"
    values_clause = ",\n    ".join([row_placeholder] * n_rows)

    return f"""
INSERT INTO {staging_fqn} ({", ".join(column_names)})
SELECT {", ".join(select_exprs)}
FROM VALUES
    {values_clause}
"""


def _build_merge_sql(staging_fqn: str, target_fqn: str) -> str:
    """One MERGE keyed on eval_id. is_manually_reviewed + is_in_golden_subset
    are deliberately NOT overwritten on UPDATE — those flags are owned by the
    human curator + select_golden_subset.py respectively, and a re-bootstrap
    shouldn't blow them away."""
    update_cols = [
        c for c in (COLS_SCALAR + COLS_VARIANT)
        if c not in ("eval_id",)
    ]
    set_clause = ",\n                ".join(f"t.{c} = s.{c}" for c in update_cols)

    insert_cols_csv = ", ".join(ALL_COLS + ["created_at"])
    insert_vals = [f"s.{c}" for c in ALL_COLS]
    insert_vals.append("CURRENT_TIMESTAMP()")
    insert_vals_csv = ", ".join(insert_vals)

    return f"""
MERGE INTO {target_fqn} t
USING {staging_fqn} s
   ON t.eval_id = s.eval_id
 WHEN MATCHED THEN UPDATE SET
                {set_clause}
 WHEN NOT MATCHED THEN INSERT ({insert_cols_csv})
                VALUES ({insert_vals_csv})
"""


def merge_to_snowflake(rows: list[EvalRow], report: BuildReport) -> None:
    if not rows:
        log.warning("Nothing to MERGE; skipping Snowflake connection.")
        return
    try:
        import snowflake.connector  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "snowflake-connector-python is required for live MERGEs."
        ) from exc

    conn_kwargs = _build_conn_kwargs()
    target_fqn = "GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET"
    staging_fqn = "EVAL_GOLDEN_SET_STAGING"

    log.info("Connecting to Snowflake account=%s as user=%s",
             conn_kwargs["account"], conn_kwargs["user"])
    conn = snowflake.connector.connect(**conn_kwargs)
    try:
        cs = conn.cursor()
        try:
            cs.execute(f"USE WAREHOUSE {conn_kwargs['warehouse']}")
            cs.execute(f"USE DATABASE {conn_kwargs['database']}")
            cs.execute(f"USE SCHEMA {conn_kwargs['schema']}")

            log.info("(Re)creating transient staging table %s", staging_fqn)
            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
            cs.execute(f"CREATE TRANSIENT TABLE {staging_fqn} LIKE {target_fqn}")

            log.info("Bulk-inserting %d rows into staging (single INSERT)",
                     len(rows))
            insert_sql = _build_staging_insert_sql(staging_fqn, len(rows))
            params: list[Any] = []
            for r in rows:
                params.extend(_row_to_params(r))
            cs.execute(insert_sql, params)

            log.info("Running MERGE %s → %s", staging_fqn, target_fqn)
            cs.execute(_build_merge_sql(staging_fqn, target_fqn))
            merge_result = cs.fetchall()
            inserted = updated = 0
            if merge_result and len(merge_result[0]) >= 2:
                inserted = int(merge_result[0][0] or 0)
                updated = int(merge_result[0][1] or 0)
            log.info("MERGE complete: %d inserted, %d updated", inserted, updated)
            report.snowflake_inserted = inserted
            report.snowflake_updated = updated

            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
        finally:
            cs.close()
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# Orchestration
# ───────────────────────────────────────────────────────────────────────────
def build_all_rows(
    source: str,
    tutorials_root: Path,
    solutions_dir: Path,
    from_files: bool,
    report: BuildReport,
) -> list[EvalRow]:
    """Return the combined list of rows for the chosen source(s). Validates
    expected_slug against the walked tutorial set."""
    log.info("Walking tutorials root %s", tutorials_root)
    fms = walk_tutorial_slugs(tutorials_root)
    valid_slugs = set(fms.keys())
    report.valid_tutorial_slugs = valid_slugs
    log.info("Tutorials with a slug: %d", len(valid_slugs))

    rows: list[EvalRow] = []
    if source in ("tutorials", "all"):
        log.info("Building phrasings rows…")
        rows.extend(build_phrasings_rows(fms, report))
        log.info(
            "Phrasings rows: %d  (from %d tutorials with non-empty phrasings)",
            report.phrasings_rows, report.tutorials_with_phrasings,
        )

    if source in ("solutions", "all"):
        if from_files:
            log.info("Building solution-cross-ref rows from disk (--from-files)…")
            rows.extend(
                build_xref_rows_from_files(solutions_dir, valid_slugs, report)
            )
        else:
            log.info("Building solution-cross-ref rows from EXAM_PARTS (Snowflake)…")
            rows.extend(
                build_xref_rows_from_snowflake(valid_slugs, report)
            )
        log.info(
            "Cross-ref rows: %d  (from %d EXAM_PARTS rows; %d dropped due to stale slug)",
            report.xref_rows_total, report.exam_parts_seen,
            report.xref_rows_dropped_stale_slug,
        )

    return rows


def _check_no_duplicate_ids(rows: list[EvalRow]) -> None:
    """Eval_id is the MERGE key; duplicates would silently coalesce. Fail
    fast on collisions."""
    seen: set[str] = set()
    dupes: list[str] = []
    for r in rows:
        if r.eval_id in seen:
            dupes.append(r.eval_id)
        seen.add(r.eval_id)
    if dupes:
        sample = ", ".join(dupes[:10])
        raise RuntimeError(
            f"Duplicate eval_id detected ({len(dupes)} collisions). "
            f"Sample: {sample}. Inspect the source data or eval_id construction."
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    ap.add_argument(
        "--source",
        choices=("tutorials", "solutions", "all"),
        default="all",
        help="Which bootstrap channel(s) to emit rows from. Default: all.",
    )
    ap.add_argument(
        "--from-files",
        action="store_true",
        help=("For --source solutions/all, parse cross-references from the "
              "solutions .md files on disk rather than from EXAM_PARTS in "
              "Snowflake. Lets the build run without Snowflake credentials."),
    )
    ap.add_argument(
        "--tutorials-root",
        type=Path,
        default=DEFAULT_TUTORIALS_ROOT,
        help="Path to the tutorials/ directory containing LCHL_*/ folders.",
    )
    ap.add_argument(
        "--solutions-dir",
        type=Path,
        default=DEFAULT_SOLUTIONS_DIR,
        help="Path to the LCHL_Maths_Exams/Solutions/ folder.",
    )
    ap.add_argument(
        "--csv-out",
        type=Path,
        default=CSV_OUT,
        help="CSV output path (overwritten each run). Default: eval/eval_golden_set.csv",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Build rows, write the CSV, but don't MERGE into Snowflake.",
    )
    args = ap.parse_args(argv)

    report = BuildReport()
    tutorials_root = args.tutorials_root.resolve()
    solutions_dir = args.solutions_dir.resolve()

    try:
        rows = build_all_rows(
            source=args.source,
            tutorials_root=tutorials_root,
            solutions_dir=solutions_dir,
            from_files=args.from_files,
            report=report,
        )
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 2
    except RuntimeError as exc:
        log.error("%s", exc)
        return 1

    log.info("Total rows built: %d", len(rows))
    _check_no_duplicate_ids(rows)
    log.info("No duplicate eval_id values.")

    n_written = write_csv(rows, args.csv_out.resolve())
    report.csv_rows_written = n_written
    log.info("CSV written: %d rows → %s", n_written, args.csv_out)

    if args.dry_run:
        log.info("--dry-run: skipping Snowflake MERGE.")
    else:
        merge_to_snowflake(rows, report)

    # Summary block — easy to read in CI logs.
    log.info("──────── summary ────────")
    log.info("phrasings rows         : %d", report.phrasings_rows)
    log.info("cross-ref rows         : %d", report.xref_rows_total)
    log.info("dropped (stale slug)   : %d", report.xref_rows_dropped_stale_slug)
    log.info("csv rows               : %d", report.csv_rows_written)
    if not args.dry_run:
        log.info("snowflake inserted     : %d", report.snowflake_inserted)
        log.info("snowflake updated      : %d", report.snowflake_updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
