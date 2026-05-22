#!/usr/bin/env python3
"""Load every canonical LCHL tutorial markdown file into
GKTUITION_TUTOR.RAW.TUTORIALS via an idempotent MERGE.

Usage
-----
    # Run end-to-end against Snowflake (uses env-var credentials):
    python load_tutorials.py --tutorials-root ../../career-transition-2026/tutorials

    # Inspect what would be loaded without touching Snowflake:
    python load_tutorials.py --tutorials-root ../../career-transition-2026/tutorials --dry-run

Environment variables (live mode only)
--------------------------------------
    SNOWFLAKE_ACCOUNT    required (e.g. abc12345.eu-west-1)
    SNOWFLAKE_USER       required
    SNOWFLAKE_PASSWORD   one of {PASSWORD, PRIVATE_KEY_PATH} required
    SNOWFLAKE_PRIVATE_KEY_PATH         (optional, keypair auth)
    SNOWFLAKE_AUTHENTICATOR            default = 'snowflake'
    SNOWFLAKE_ROLE                     default = 'ACCOUNTADMIN'
    SNOWFLAKE_WAREHOUSE                default = 'WH_TUTOR'
    SNOWFLAKE_DATABASE                 default = 'GKTUITION_TUTOR'
    SNOWFLAKE_SCHEMA                   default = 'RAW'

Design notes
------------
* YAML frontmatter is parsed with PyYAML (the .venv-py312 already ships it;
  python-frontmatter is not available, so the `---`-delimiter scan is open-coded).
* Files skipped (with a WARN log, NOT a parse failure):
    - `_SUMMARY-*.md`     — strand summaries, indexed in a separate table.
    - `README.md`         — folder-level docs, no YAML frontmatter.
    - any file whose YAML has no top-level `slug` field — e.g. the
      `LCHL_Paper_{1,2}_Proofs/proof-*.md` cross-reference variant, which
      points at a canonical tutorial elsewhere and would otherwise dilute
      retrieval. Surfaced in delivery notes as a known schema variance.
* Load strategy: a single bulk INSERT into a transient staging table (one
  SQL statement with N-row VALUES), followed by a single MERGE into the
  target. No row-by-row inserts. Idempotent on the `slug` primary key.
* VARIANT / ARRAY columns are JSON-serialised in Python and `PARSE_JSON()`-ed
  in SQL — the connector's standard binding pattern for semi-structured.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_tutorials")

# ───────────────────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────────────────
TITLE_PLUS_PHRASINGS_CAP = 4_000  # characters; per spec
FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)

# Regex used by `_preprocess_yaml`. Matches a list-item line whose value begins
# with a bare `|` — e.g. `  - |z1 z2| = |z1| |z2|` or `  - |AC| = √2`. YAML
# interprets a leading `|` as a block-scalar literal indicator; tutorial
# authors used it for modulus signs. We wrap such values in single quotes so
# PyYAML treats them as ordinary strings. We deliberately do NOT touch lines
# where the value is a genuine block-scalar header (`- |`, `- |+`, `- |-`,
# `- |<digit>` optionally followed by whitespace).
_BARE_PIPE_LIST_ITEM = re.compile(r"^(\s*-\s+)(\|[^\n]+)$", re.MULTILINE)
_BLOCK_SCALAR_HEADER = re.compile(r"^\|[\+\-]?\d*\s*$")

# Order matters: this is the column order used by both the INSERT and the
# MERGE. Keep aligned with bootstrap_tutorials_table.sql.
COLS_SCALAR = [
    "slug",
    "video_id",
    "title",
    "title_plus_phrasings",
    "body",
    "warnings_and_gotchas",
    "paper",
    "topic",
    "subtopic",
    "sequence_number",
    "duration_seconds",
    "youtube_url",
    "gktuition_url",
    "syllabus_strand",
    "syllabus_section",
    "syllabus_reference",
    "source_path",
]
COLS_VARIANT = [
    "techniques",
    "course_levels",
    "prerequisites",
    "forward_links",
    "xref",
    "log_tables",
    "exam_appearances",
    "learning_work",
    "companion_practice_questions",
]
ALL_COLS = COLS_SCALAR + COLS_VARIANT  # order used in INSERT / MERGE


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class LoadReport:
    walked: int = 0
    parsed: int = 0
    skipped_summary: int = 0
    skipped_readme: int = 0
    skipped_out_of_schema: list[Path] = field(default_factory=list)
    parse_errors: list[tuple[Path, str]] = field(default_factory=list)
    loaded: int = 0  # populated after the MERGE


# ───────────────────────────────────────────────────────────────────────────
# Frontmatter parsing
# ───────────────────────────────────────────────────────────────────────────
def _preprocess_yaml(fm_raw: str) -> str:
    """Patch known YAML pitfalls without touching the source `.md` file.

    Currently handles a single case: list items whose value begins with `|`
    (bare modulus pipes like `- |z1 z2| = |z1| |z2|`). YAML treats a bare `|`
    as a block-scalar literal indicator; wrapping such values in single
    quotes makes them strings without changing semantics."""
    def _quote(match: re.Match[str]) -> str:
        prefix, value = match.group(1), match.group(2)
        if _BLOCK_SCALAR_HEADER.match(value):
            return match.group(0)  # genuine block-scalar header
        escaped = value.replace("'", "''")
        return f"{prefix}'{escaped}'"

    return _BARE_PIPE_LIST_ITEM.sub(_quote, fm_raw)


def split_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    """Return (yaml_dict, body) or None if the file lacks YAML frontmatter."""
    m = FM_RE.match(text)
    if not m:
        return None
    fm_raw, body = m.group(1), m.group(2)
    fm_raw = _preprocess_yaml(fm_raw)
    try:
        data = yaml.safe_load(fm_raw)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"YAML frontmatter is not a mapping (got {type(data).__name__})")
    return data, body


# ───────────────────────────────────────────────────────────────────────────
# Per-tutorial row build
# ───────────────────────────────────────────────────────────────────────────
def _as_list(v: Any) -> list[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _join_capped(parts: list[str], cap: int) -> str:
    out: list[str] = []
    used = 0
    for p in parts:
        s = str(p).strip()
        if not s:
            continue
        add = (1 if out else 0) + len(s)  # newline separator
        if used + add > cap:
            break
        out.append(s)
        used += add
    return "\n".join(out)


def build_row(fm: dict[str, Any], body: str, source_path: Path) -> dict[str, Any]:
    """Translate the YAML frontmatter + body into the TUTORIALS row dict."""
    slug = fm["slug"]  # mandatory; KeyError raised by caller if missing
    title = fm.get("title", "")

    keywords = _as_list(fm.get("keywords"))
    phrasings = _as_list(fm.get("common_student_phrasings"))
    title_plus_phrasings = _join_capped([title, *keywords, *phrasings], TITLE_PLUS_PHRASINGS_CAP)

    warnings = _as_list(fm.get("content_warnings"))
    warnings_and_gotchas = "\n".join(str(w) for w in warnings) if warnings else None

    # Combined techniques (kebab tokens). Preserve order; deduplicate.
    seen: set[str] = set()
    techniques: list[str] = []
    for t in _as_list(fm.get("techniques_taught")) + _as_list(fm.get("techniques_used")):
        if t and t not in seen:
            seen.add(t)
            techniques.append(t)

    source = fm.get("source")
    if not isinstance(source, dict):
        source = {}

    # Schema variance: some older tutorials carry `syllabus` as a list of
    # section refs (multi-section coverage), newer ones as a single dict.
    # Collapse to scalars: take the first entry's strand + section, and use
    # whichever of `reference`/`notes`/joined `learning_outcomes` is available
    # for the reference column.
    raw_syllabus = fm.get("syllabus")
    if isinstance(raw_syllabus, list) and raw_syllabus:
        first = raw_syllabus[0] if isinstance(raw_syllabus[0], dict) else {}
        syllabus = {
            "strand": first.get("strand"),
            "section": first.get("section"),
            "reference": (
                first.get("reference")
                or first.get("notes")
                or ("; ".join(_as_list(first.get("learning_outcomes"))) or None)
            ),
        }
    elif isinstance(raw_syllabus, dict):
        syllabus = raw_syllabus
    else:
        syllabus = {}

    return {
        "slug": slug,
        "video_id": fm.get("video_id"),
        "title": title,
        "title_plus_phrasings": title_plus_phrasings,
        "body": body,
        "warnings_and_gotchas": warnings_and_gotchas,
        # filterable scalars
        "paper": fm.get("paper"),
        "topic": fm.get("topic"),
        "subtopic": fm.get("subtopic"),
        "sequence_number": fm.get("sequence_number"),
        "duration_seconds": fm.get("duration_seconds"),
        "youtube_url": source.get("youtube_url"),
        "gktuition_url": source.get("gktuition_url"),
        "syllabus_strand": syllabus.get("strand"),
        "syllabus_section": syllabus.get("section"),
        "syllabus_reference": syllabus.get("reference"),
        "source_path": str(source_path),
        # variant / array
        "techniques": techniques,
        "course_levels": _as_list(fm.get("course_levels")),
        "prerequisites": _as_list(fm.get("prerequisites")),
        "forward_links": _as_list(fm.get("forward_links")),
        "xref": _as_list(fm.get("xref")),
        "log_tables": _as_list(fm.get("log_tables")),
        "exam_appearances": _as_list(fm.get("exam_appearances")),
        "learning_work": _as_list(fm.get("learning_work")),
        "companion_practice_questions": _as_list(fm.get("companion_practice_questions")),
    }


# ───────────────────────────────────────────────────────────────────────────
# Corpus walk
# ───────────────────────────────────────────────────────────────────────────
def walk_corpus(tutorials_root: Path, report: LoadReport) -> list[dict[str, Any]]:
    """Walk tutorials/LCHL_*/*.md (top level only); return list of row dicts."""
    if not tutorials_root.is_dir():
        raise FileNotFoundError(f"tutorials root not found: {tutorials_root}")

    rows: list[dict[str, Any]] = []

    for strand_dir in sorted(tutorials_root.glob("LCHL_*")):
        if not strand_dir.is_dir():
            continue
        for md in sorted(strand_dir.glob("*.md")):
            report.walked += 1
            name = md.name

            if name.startswith("_SUMMARY-"):
                report.skipped_summary += 1
                continue
            if name == "README.md":
                report.skipped_readme += 1
                continue

            try:
                text = md.read_text(encoding="utf-8")
            except OSError as e:
                report.parse_errors.append((md, f"read error: {e}"))
                continue

            try:
                parsed = split_frontmatter(text)
            except ValueError as e:
                report.parse_errors.append((md, str(e)))
                continue

            if parsed is None:
                report.parse_errors.append((md, "no YAML frontmatter delimiters"))
                continue

            fm, body = parsed
            if "slug" not in fm or not fm.get("slug"):
                # Schema variance (e.g. LCHL_Paper_*_Proofs cross-references).
                # Skip-with-warning is not a parse failure.
                report.skipped_out_of_schema.append(md)
                continue

            try:
                row = build_row(fm, body, md)
            except Exception as e:  # noqa: BLE001 — surface unexpected build failures
                report.parse_errors.append((md, f"build_row failed: {e}"))
                continue

            rows.append(row)
            report.parsed += 1

    return rows


# ───────────────────────────────────────────────────────────────────────────
# Snowflake load
# ───────────────────────────────────────────────────────────────────────────
def _row_to_params(row: dict[str, Any]) -> list[Any]:
    """Flatten a row dict into the ordered parameter list expected by the
    multi-row VALUES clause. VARIANT/ARRAY columns become JSON strings,
    `PARSE_JSON()`-ed inside SQL."""
    out: list[Any] = []
    for c in COLS_SCALAR:
        out.append(row.get(c))
    for c in COLS_VARIANT:
        out.append(json.dumps(row.get(c) or []))
    return out


def _build_merge_sql(staging_fqn: str, target_fqn: str) -> str:
    """Build the single MERGE statement used to upsert from staging."""
    update_cols = [c for c in ALL_COLS if c != "slug"]
    set_clause = ",\n                ".join(f"t.{c} = s.{c}" for c in update_cols)
    set_clause += ",\n                t.loaded_at = CURRENT_TIMESTAMP()"

    insert_cols_csv = ", ".join([*ALL_COLS, "loaded_at"])
    insert_vals = [f"s.{c}" for c in ALL_COLS]
    insert_vals.append("CURRENT_TIMESTAMP()")
    insert_vals_csv = ", ".join(insert_vals)

    return f"""
MERGE INTO {target_fqn} t
USING {staging_fqn} s
   ON t.slug = s.slug
 WHEN MATCHED THEN UPDATE SET
                {set_clause}
 WHEN NOT MATCHED THEN INSERT ({insert_cols_csv})
                VALUES ({insert_vals_csv})
"""


def _build_staging_insert_sql(staging_fqn: str, n_rows: int) -> str:
    """One INSERT SELECT … FROM VALUES (?,?,?), (?,?,?), …
    with PARSE_JSON wrapping the VARIANT cols."""
    # Column expressions in the SELECT — scalars passthrough, variants PARSE_JSON'd.
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

    ncols = len(ALL_COLS)
    row_placeholder = "(" + ",".join(["?"] * ncols) + ")"
    values_clause = ",\n    ".join([row_placeholder] * n_rows)

    return f"""
INSERT INTO {staging_fqn} ({", ".join(column_names)})
SELECT {", ".join(select_exprs)}
FROM VALUES
    {values_clause}
"""


def load_to_snowflake(rows: list[dict[str, Any]], report: LoadReport) -> None:
    """Connect to Snowflake, stage rows, MERGE into TUTORIALS, log counts."""
    if not rows:
        log.warning("Nothing to load; skipping Snowflake connection.")
        return

    try:
        import snowflake.connector  # noqa: PLC0415  (lazy import: not needed for --dry-run)
    except ImportError as e:
        raise RuntimeError(
            "snowflake-connector-python is required for live loads. "
            "Install via pip or use --dry-run."
        ) from e

    # The bulk-insert + MERGE SQL uses qmark `?` placeholders rather than the
    # connector's default pyformat `%s`. Set it process-wide before any
    # connection is opened.
    snowflake.connector.paramstyle = "qmark"

    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    if not account or not user:
        raise RuntimeError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER env vars are required for live loads. "
            "Use --dry-run if you only want to validate parsing."
        )

    conn_kwargs: dict[str, Any] = {
        "account": account,
        "user": user,
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "WH_TUTOR"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", "GKTUITION_TUTOR"),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", "RAW"),
        "client_session_keep_alive": False,
    }
    if pk_path := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        conn_kwargs["private_key_file"] = pk_path
        conn_kwargs["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT")
    elif password := os.environ.get("SNOWFLAKE_PASSWORD"):
        conn_kwargs["password"] = password
    else:
        raise RuntimeError(
            "Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH must be set."
        )

    target_fqn = "GKTUITION_TUTOR.RAW.TUTORIALS"
    staging_fqn = "TUTORIALS_STAGING"

    log.info("Connecting to Snowflake account=%s as user=%s", account, user)
    conn = snowflake.connector.connect(**conn_kwargs)
    try:
        cs = conn.cursor()
        try:
            cs.execute(f"USE WAREHOUSE {conn_kwargs['warehouse']}")
            cs.execute(f"USE DATABASE {conn_kwargs['database']}")
            cs.execute(f"USE SCHEMA {conn_kwargs['schema']}")

            log.info("Creating transient staging table %s", staging_fqn)
            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
            cs.execute(f"CREATE TRANSIENT TABLE {staging_fqn} LIKE {target_fqn}")

            log.info("Bulk-inserting %d rows into staging (single INSERT)", len(rows))
            insert_sql = _build_staging_insert_sql(staging_fqn, len(rows))
            params: list[Any] = []
            for r in rows:
                params.extend(_row_to_params(r))
            cs.execute(insert_sql, params)

            log.info("Running MERGE %s → %s", staging_fqn, target_fqn)
            merge_sql = _build_merge_sql(staging_fqn, target_fqn)
            cs.execute(merge_sql)
            merge_result = cs.fetchall()
            # Snowflake returns (rows_inserted, rows_updated) for a MERGE.
            inserted = updated = 0
            if merge_result and len(merge_result[0]) >= 2:
                inserted = int(merge_result[0][0] or 0)
                updated = int(merge_result[0][1] or 0)
            log.info("MERGE complete: %d inserted, %d updated", inserted, updated)
            report.loaded = inserted + updated

            cs.execute(f"DROP TABLE IF EXISTS {staging_fqn}")
        finally:
            cs.close()
    finally:
        conn.close()


# ───────────────────────────────────────────────────────────────────────────
# CLI
# ───────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument(
        "--tutorials-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent / "career-transition-2026" / "tutorials",
        help="Path to the tutorials/ directory containing LCHL_*/ strand folders.",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Walk + parse the corpus, print counts, do not touch Snowflake.",
    )
    args = ap.parse_args(argv)

    report = LoadReport()
    tutorials_root = args.tutorials_root.resolve()
    log.info("Walking corpus under %s", tutorials_root)

    try:
        rows = walk_corpus(tutorials_root, report)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 2

    # Print counts always.
    log.info("Walked:     %d files", report.walked)
    log.info("Parsed:     %d tutorials (ready to load)", report.parsed)
    log.info("Skipped:    %d summary file(s), %d README(s), %d out-of-schema (no slug)",
             report.skipped_summary, report.skipped_readme, len(report.skipped_out_of_schema))

    if report.skipped_out_of_schema:
        log.info("Out-of-schema files (skipped, no slug field):")
        for p in report.skipped_out_of_schema:
            log.info("    %s", p)

    if report.parse_errors:
        log.error("Parse errors (%d):", len(report.parse_errors))
        for p, msg in report.parse_errors:
            log.error("    %s -> %s", p, msg)
        log.error("Aborting — fix the YAML in the files above and re-run.")
        return 1

    if args.dry_run:
        log.info("--dry-run: would load %d tutorials into GKTUITION_TUTOR.RAW.TUTORIALS", len(rows))
        return 0

    load_to_snowflake(rows, report)
    log.info("Loaded:     %d rows merged into TUTORIALS (sum of inserts + updates)", report.loaded)
    return 0


if __name__ == "__main__":
    sys.exit(main())
