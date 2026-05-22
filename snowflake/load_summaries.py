#!/usr/bin/env python3
"""Load LCHL strand cram-summary sheets into GKTUITION_TUTOR.RAW.SUMMARIES.

One row per strand. Sourced from `tutorials/LCHL_<Strand>/_SUMMARY-exam-cram.md`
(the leading underscore is the canonical convention; the walker also accepts
`SUMMARY-exam-cram.md` without the underscore in case the convention drifts).

Usage
-----
    # Live run against Snowflake (env-var credentials):
    python load_summaries.py --tutorials-root ../../career-transition-2026/tutorials

    # Walk + parse only; no Snowflake write.
    python load_summaries.py --dry-run

Environment variables (live mode only)
--------------------------------------
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or PRIVATE_KEY_PATH),
    SNOWFLAKE_AUTHENTICATOR, SNOWFLAKE_ROLE (default ACCOUNTADMIN),
    SNOWFLAKE_WAREHOUSE (default WH_TUTOR), SNOWFLAKE_DATABASE (default
    GKTUITION_TUTOR), SNOWFLAKE_SCHEMA (default RAW). Identical surface to
    load_exam_parts.py and load_tutorials.py.

Design notes
------------
* The corpus currently has 20 strand summaries — Agent 01's delivery note
  corroborates this count. The prompt's "17" figure predates the Trig 1–4
  expansion and the addition of AVM 1 + Induction summaries.
* Parsing extracts three structured payloads from every summary:
    - `body`                  — full markdown below the H1 line.
    - `top_tutorials_by_frequency` — slug list from the
      "📊 Top X tutorials by exam frequency" table, rank-ordered.
    - `exam_frequency_data`  — same table, structured (rank, tutorial,
      citations, what_it_tests).
    - `recommended_time_split` — the "⏱ Suggested time split (90 min)" table
      (activity, time_text, minutes, why).
* Strand name comes from the H1 line ("# Algebra — 90-Minute Exam Cram Summary").
  Strand folder comes from the file's parent directory name.
* Load strategy mirrors load_exam_parts.py / load_tutorials.py: single bulk
  INSERT into a transient staging table, single MERGE on `summary_id`.
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

import yaml  # noqa: F401 — keeps the deps surface aligned with load_exam_parts.py

# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_summaries")

# ───────────────────────────────────────────────────────────────────────────
# Constants / regexes
# ───────────────────────────────────────────────────────────────────────────
SUMMARY_PATTERNS = ("_SUMMARY-exam-cram.md", "SUMMARY-exam-cram.md")

H1_RE = re.compile(r"^#\s+(?P<strand>.+?)\s+—\s+90-Minute Exam Cram Summary\s*$")
TIME_SPLIT_HEADER_RE = re.compile(r"^##\s+(?:[^\w\s]\s+)?Suggested time split", re.IGNORECASE)
TOP_TUTORIALS_HEADER_RE = re.compile(r"^##\s+(?:[^\w\s]\s+)?Top\s+", re.IGNORECASE)

# Markdown table row: pipes + cells. Used after stripping a leading/trailing pipe.
TABLE_ROW_RE = re.compile(r"^\s*\|")
TABLE_SEP_RE = re.compile(r"^\s*\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|\s*$")

# Slug extraction from a top-tutorials row: backticked token, e.g. `the-line-1`,
# `differentiation-15`, `the-line-7/8/9` (composite — we split on '/').
BACKTICK_TOKEN_RE = re.compile(r"`([^`]+)`")

# Minutes-from-time-cell extractor: "20 min", "5 min", "10–15 min".
MINUTES_RE = re.compile(r"(\d+)\s*(?:min|m\b)", re.IGNORECASE)

# Column order — kept aligned with bootstrap_summaries_table.sql.
COLS_SCALAR = [
    "summary_id",
    "strand_name",
    "strand_folder",
    "body",
    "source_path",
]
COLS_VARIANT = [
    "top_tutorials_by_frequency",
    "exam_frequency_data",
    "recommended_time_split",
]
ALL_COLS = COLS_SCALAR + COLS_VARIANT


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class LoadReport:
    files_walked: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    rows_built: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    snowflake_inserted: int = 0
    snowflake_updated: int = 0


@dataclass
class Summary:
    summary_id: str
    strand_name: str
    strand_folder: str
    body: str
    top_tutorials_by_frequency: list[str] = field(default_factory=list)
    exam_frequency_data: list[dict[str, Any]] = field(default_factory=list)
    recommended_time_split: list[dict[str, Any]] = field(default_factory=list)
    source_path: str = ""


# ───────────────────────────────────────────────────────────────────────────
# Folder → summary_id slug
# ───────────────────────────────────────────────────────────────────────────
def folder_to_summary_id(folder: str) -> str:
    """LCHL_The_Line → 'summary-the-line';
       LCHL_Trigonometry_2 → 'summary-trigonometry-2'."""
    base = folder.lower()
    if base.startswith("lchl_"):
        base = base[len("lchl_"):]
    base = base.replace("_", "-")
    return f"summary-{base}"


# ───────────────────────────────────────────────────────────────────────────
# Markdown table parsing
# ───────────────────────────────────────────────────────────────────────────
def _split_cells(row: str) -> list[str]:
    """Split a markdown table row into trimmed cells. Strips the outer pipes."""
    inner = row.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _extract_table_after(lines: list[str], start_idx: int) -> list[list[str]]:
    """Parse the markdown table whose H2 header lives on `lines[start_idx]`.
    Returns a list of cell-lists (excluding the header row and the `|---|---|`
    separator). Empty list if no table found before the next H2."""
    # Skip the H2 line itself + blank lines until the first table row.
    i = start_idx + 1
    while i < len(lines) and not TABLE_ROW_RE.match(lines[i]):
        if lines[i].startswith("## "):
            return []
        i += 1
    if i >= len(lines):
        return []
    # The first table row is the header; skip it + the separator below it.
    i += 1
    if i < len(lines) and TABLE_SEP_RE.match(lines[i]):
        i += 1
    # Collect data rows until the table ends.
    rows: list[list[str]] = []
    while i < len(lines) and TABLE_ROW_RE.match(lines[i]):
        rows.append(_split_cells(lines[i]))
        i += 1
    return rows


def parse_top_tutorials_table(rows: list[list[str]]) -> tuple[list[str], list[dict[str, Any]]]:
    """From rows of `[rank, tutorial, citations, what_it_tests]`, return
    (slug_list, structured_records). The slug list preserves rank order and
    deduplicates while it walks."""
    slug_list: list[str] = []
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    for cells in rows:
        if len(cells) < 2:
            continue
        rank_cell = cells[0]
        tutorial_cell = cells[1] if len(cells) > 1 else ""
        citations_cell = cells[2] if len(cells) > 2 else ""
        what_cell = cells[3] if len(cells) > 3 else ""

        # Rank — drop non-digits if any (rare). Tolerate "~" or em-dash.
        rank_match = re.search(r"\d+", rank_cell)
        rank = int(rank_match.group()) if rank_match else None

        # Slugs — every backticked token in the tutorial cell. Some authors
        # write composite ranges like `the-line-7/8/9`; expand on '/'.
        slugs: list[str] = []
        for tok in BACKTICK_TOKEN_RE.findall(tutorial_cell):
            for s in tok.split("/"):
                s = s.strip()
                if not s:
                    continue
                slugs.append(s)

        citations_match = re.search(r"\d+", citations_cell)
        citations = int(citations_match.group()) if citations_match else None

        records.append({
            "rank": rank,
            "tutorial": slugs[0] if slugs else None,
            "tutorials": slugs,
            "citations": citations,
            "what_it_tests": what_cell or None,
        })

        for s in slugs:
            if s not in seen:
                seen.add(s)
                slug_list.append(s)

    return slug_list, records


def parse_time_split_table(rows: list[list[str]]) -> list[dict[str, Any]]:
    """From rows of `[activity, time_text, why]`, return structured entries
    with parsed integer minutes alongside the original time text."""
    out: list[dict[str, Any]] = []
    for cells in rows:
        if len(cells) < 2:
            continue
        activity = cells[0] or None
        time_text = cells[1] or None
        why = cells[2] if len(cells) > 2 else None
        minutes: int | None = None
        if time_text:
            m = MINUTES_RE.search(time_text)
            if m:
                minutes = int(m.group(1))
        out.append({
            "activity": activity,
            "time_text": time_text,
            "minutes": minutes,
            "why": why,
        })
    return out


# ───────────────────────────────────────────────────────────────────────────
# Per-file parse
# ───────────────────────────────────────────────────────────────────────────
def parse_summary_file(path: Path) -> Summary | None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    strand_name: str | None = None
    body_start = 0
    for i, line in enumerate(lines):
        m = H1_RE.match(line)
        if m:
            strand_name = m.group("strand").strip()
            body_start = i + 1
            break
    if strand_name is None:
        # Fall back to the folder name if the H1 doesn't match the convention.
        # The summary is still loadable — just with a less-friendly name.
        strand_name = path.parent.name.replace("LCHL_", "").replace("_", " ")

    body = "\n".join(lines[body_start:]).lstrip("\n")
    strand_folder = path.parent.name
    summary_id = folder_to_summary_id(strand_folder)

    # Locate the two structured tables.
    top_tutorials_rows: list[list[str]] = []
    time_split_rows: list[list[str]] = []
    for i, line in enumerate(lines):
        if not top_tutorials_rows and TOP_TUTORIALS_HEADER_RE.match(line):
            top_tutorials_rows = _extract_table_after(lines, i)
        elif not time_split_rows and TIME_SPLIT_HEADER_RE.match(line):
            time_split_rows = _extract_table_after(lines, i)

    top_tutorials_by_frequency, exam_frequency_data = parse_top_tutorials_table(top_tutorials_rows)
    recommended_time_split = parse_time_split_table(time_split_rows)

    return Summary(
        summary_id=summary_id,
        strand_name=strand_name,
        strand_folder=strand_folder,
        body=body,
        top_tutorials_by_frequency=top_tutorials_by_frequency,
        exam_frequency_data=exam_frequency_data,
        recommended_time_split=recommended_time_split,
        source_path=str(path),
    )


# ───────────────────────────────────────────────────────────────────────────
# Corpus walk
# ───────────────────────────────────────────────────────────────────────────
def walk_corpus(tutorials_root: Path, report: LoadReport) -> list[Summary]:
    if not tutorials_root.is_dir():
        raise FileNotFoundError(f"tutorials root not found: {tutorials_root}")

    files: list[Path] = []
    for strand_dir in sorted(tutorials_root.glob("LCHL_*")):
        if not strand_dir.is_dir():
            continue
        for pattern in SUMMARY_PATTERNS:
            files.extend(strand_dir.glob(pattern))
    files = sorted(set(files))

    summaries: list[Summary] = []
    for path in files:
        report.files_walked += 1
        try:
            summary = parse_summary_file(path)
        except Exception as exc:  # noqa: BLE001
            report.parse_errors.append((path.name, repr(exc)))
            continue
        if summary is None:
            report.files_skipped += 1
            continue
        report.files_parsed += 1
        summaries.append(summary)
    return summaries


# ───────────────────────────────────────────────────────────────────────────
# Row build + Snowflake load
# ───────────────────────────────────────────────────────────────────────────
def build_row(s: Summary) -> dict[str, Any]:
    return {
        "summary_id": s.summary_id,
        "strand_name": s.strand_name,
        "strand_folder": s.strand_folder,
        "body": s.body,
        "source_path": s.source_path,
        "top_tutorials_by_frequency": list(s.top_tutorials_by_frequency),
        "exam_frequency_data": list(s.exam_frequency_data),
        "recommended_time_split": list(s.recommended_time_split),
    }


def _row_to_params(row: dict[str, Any]) -> list[Any]:
    out: list[Any] = []
    for c in COLS_SCALAR:
        out.append(row.get(c))
    for c in COLS_VARIANT:
        val = row.get(c)
        if val is None:
            val = []
        out.append(json.dumps(val))
    return out


def _build_staging_insert_sql(staging_fqn: str, n_rows: int) -> str:
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


def _build_merge_sql(staging_fqn: str, target_fqn: str) -> str:
    update_cols = [c for c in ALL_COLS if c != "summary_id"]
    set_clause = ",\n                ".join(f"t.{c} = s.{c}" for c in update_cols)
    set_clause += ",\n                t.loaded_at = CURRENT_TIMESTAMP()"

    insert_cols_csv = ", ".join([*ALL_COLS, "loaded_at"])
    insert_vals = [f"s.{c}" for c in ALL_COLS] + ["CURRENT_TIMESTAMP()"]
    insert_vals_csv = ", ".join(insert_vals)

    return f"""
MERGE INTO {target_fqn} t
USING {staging_fqn} s
   ON t.summary_id = s.summary_id
 WHEN MATCHED THEN UPDATE SET
                {set_clause}
 WHEN NOT MATCHED THEN INSERT ({insert_cols_csv})
                VALUES ({insert_vals_csv})
"""


def load_to_snowflake(rows: list[dict[str, Any]], report: LoadReport) -> None:
    if not rows:
        log.warning("Nothing to load; skipping Snowflake connection.")
        return

    try:
        import snowflake.connector  # noqa: PLC0415
    except ImportError:
        log.warning(
            "snowflake-connector-python not installed — skipping MERGE. "
            "`pip install snowflake-connector-python` for a live load."
        )
        return

    snowflake.connector.paramstyle = "qmark"

    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    if not account or not user:
        log.warning(
            "SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER unset — skipping MERGE. "
            "Set both env vars and re-run for a live load."
        )
        return

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

    target_fqn = "GKTUITION_TUTOR.RAW.SUMMARIES"
    staging_fqn = "SUMMARIES_STAGING"

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

            log.info("Bulk-inserting %d rows into staging", len(rows))
            insert_sql = _build_staging_insert_sql(staging_fqn, len(rows))
            params: list[Any] = []
            for r in rows:
                params.extend(_row_to_params(r))
            cs.execute(insert_sql, params)

            log.info("Running MERGE %s → %s", staging_fqn, target_fqn)
            merge_sql = _build_merge_sql(staging_fqn, target_fqn)
            cs.execute(merge_sql)
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
# CLI
# ───────────────────────────────────────────────────────────────────────────
def _default_tutorials_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / (
        "career-transition-2026/tutorials"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument(
        "--tutorials-root",
        type=Path,
        default=_default_tutorials_root(),
        help="Path to the tutorials/ directory containing LCHL_*/ strand folders.",
    )
    ap.add_argument("--dry-run", action="store_true",
                    help="Walk + parse, print counts; no Snowflake write.")
    args = ap.parse_args(argv)

    report = LoadReport()
    tutorials_root = args.tutorials_root.resolve()
    log.info("Walking corpus under %s", tutorials_root)

    try:
        summaries = walk_corpus(tutorials_root, report)
    except FileNotFoundError as e:
        log.error("%s", e)
        return 2

    report.rows_built = len(summaries)

    log.info("Files walked:    %d", report.files_walked)
    log.info("Files parsed:    %d", report.files_parsed)
    log.info("Rows built:      %d", report.rows_built)
    log.info("Strands present in build:")
    for s in summaries:
        log.info("    • %-35s  %2d top-tutorials, %2d time-split entries",
                 s.strand_name,
                 len(s.top_tutorials_by_frequency),
                 len(s.recommended_time_split))

    if report.parse_errors:
        log.error("Parse errors (%d):", len(report.parse_errors))
        for name, msg in report.parse_errors:
            log.error("    %s -> %s", name, msg)

    if args.dry_run:
        log.info("--dry-run: would MERGE %d rows into GKTUITION_TUTOR.RAW.SUMMARIES",
                 report.rows_built)
        return 0

    rows = [build_row(s) for s in summaries]
    load_to_snowflake(rows, report)
    log.info("Loaded: %d rows merged into SUMMARIES (%d inserted, %d updated)",
             report.snowflake_inserted + report.snowflake_updated,
             report.snowflake_inserted, report.snowflake_updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
