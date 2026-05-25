#!/usr/bin/env python3
"""Per-row failure inspector for the Cortex Search eval set.

Complement to ``score_against_cortex_search.py`` — that script reports
aggregate metrics; this one dumps the raw top-K with full per-hit scores
(reranker, cosine, text-match) for every row where the expected slug
landed at rank > 1 (or wasn't in top-K at all).

Output is a Markdown table so the dump is browsable as a file.

Use cases
---------
* DAY_31 Algebra precision@1 tuning — feed the dump for ``--strand algebra``
  into a blended-score weight-tuning loop (see AGENT_16 brief).
* General "why did this row fail" debugging when the eval scorer's brief
  fail-list isn't enough.

Routing mirrors ``score_against_cortex_search.py``:

* ``source = 'phrasings'``           → TUTOR_SEARCH
* ``source = 'solution_cross_ref'``  → SOLUTIONS_SEARCH

Usage
-----
::

    # Inspect every Algebra failure in the golden subset:
    python inspect_failures.py --only-golden-subset --strand algebra \
        --out eval/algebra_failures_DAY_31.md

    # Full corpus, every strand:
    python inspect_failures.py --out eval/all_failures.md

    # Read from a CSV instead of Snowflake (rows only; scores still need
    # live SEARCH_PREVIEW calls):
    python inspect_failures.py --from-csv eval/eval_golden_set.csv \
        --strand algebra --out eval/algebra_failures_DAY_31.md
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Reuse the loaders + Snowflake helpers from the sibling scorer so the two
# tools share a single source of truth on connection handling and the
# EvalInput shape.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# noqa: E402 — sys.path mutation must precede the import.
from score_against_cortex_search import (  # noqa: E402
    EvalInput,
    SOLUTIONS_SEARCH,
    TOP_K,
    TUTOR_SEARCH,
    _build_conn_kwargs,
    _load_rows_from_csv,
    _load_rows_from_snowflake,
    _rank_in_slugs,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("inspect")

INTER_QUERY_DELAY_S = 0.05


def _strand_of(slug: str) -> str:
    """Best-effort strand inference from a slug prefix.

    Mirrors the prefix list used by the corpus (`tutorials/LCHL_*` folders).
    Returns ``"unknown"`` for slugs that don't match any known prefix.
    """
    prefixes = [
        ("algebra-", "algebra"),
        ("the-circle-", "the-circle"),
        ("the-line-", "the-line"),
        ("statistics-", "statistics"),
        ("trigonometry-", "trigonometry"),
        ("differentiation-", "differentiation"),
        ("integration-", "integration"),
        ("complex-numbers-", "complex-numbers"),
        ("financial-maths-", "financial-maths"),
        ("functions-graphs-", "functions-graphs"),
        ("indices-logs-", "indices-logs"),
        ("induction-", "induction"),
        ("number-theory-", "number-theory"),
        ("probability-", "probability"),
        ("sequences-series-", "sequences-series"),
        ("avm-", "avm"),
    ]
    for pfx, strand in prefixes:
        if slug.startswith(pfx):
            return strand
    return "unknown"


def _search_preview_full(
    cursor: Any, service_fqn: str, query: str, columns: list[str],
    limit: int = TOP_K,
) -> list[dict[str, Any]]:
    """SEARCH_PREVIEW that asks the connector to return every hit verbatim.

    Unlike the scorer's ``_search_preview`` (which strips down to slug +
    metadata), we keep the full hit dict — including ``@scores`` — so the
    per-row dump can show reranker / cosine / text-match for every hit.
    """
    payload = {"query": query, "columns": columns, "limit": limit}
    cursor.execute(
        """
        SELECT PARSE_JSON(
            SNOWFLAKE.CORTEX.SEARCH_PREVIEW(%s, %s)
        ):results::ARRAY AS top_hits
        """,
        (service_fqn, json.dumps(payload)),
    )
    raw = cursor.fetchone()
    if not raw or raw[0] is None:
        return []
    results = raw[0]
    if isinstance(results, str):
        results = json.loads(results)
    return list(results)


def _scores_for(hit: dict[str, Any]) -> tuple[float | None, float | None, float | None]:
    """Pull (reranker, cosine, text_match) out of a hit's ``@scores`` block.

    Returns ``(None, None, None)`` if the block is missing — keeps the dump
    readable when the response shape changes.
    """
    sc = hit.get("@scores") or {}
    if not isinstance(sc, dict):
        return (None, None, None)

    def _f(k: str) -> float | None:
        v = sc.get(k)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return _f("reranker_score"), _f("cosine_similarity"), _f("text_match")


# ───────────────────────────────────────────────────────────────────────────
# Per-row inspection
# ───────────────────────────────────────────────────────────────────────────


def _inspect_phrasings_row(
    cursor: Any, row: EvalInput,
) -> tuple[int | None, list[dict[str, Any]]]:
    hits = _search_preview_full(
        cursor, TUTOR_SEARCH, row.question_text,
        columns=["slug", "title", "topic"],
    )
    slugs = [str(h.get("slug") or "") for h in hits]
    rank = _rank_in_slugs(row.expected_slug, slugs)
    return rank, hits


def _inspect_xref_row(
    cursor: Any, row: EvalInput,
) -> tuple[int | None, list[dict[str, Any]]]:
    """Cross-ref rows hit SOLUTIONS_SEARCH; the rank is computed against the
    flattened ``tutorials_referenced`` lists (matches the scorer)."""
    hits = _search_preview_full(
        cursor, SOLUTIONS_SEARCH, row.question_text,
        columns=["part_id", "topic", "tutorials_referenced"],
    )
    flat: list[str] = []
    for h in hits:
        refs = h.get("tutorials_referenced") or []
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                refs = []
        for slug in refs:
            if slug not in flat:
                flat.append(slug)
            if len(flat) >= TOP_K:
                break
        if len(flat) >= TOP_K:
            break
    rank = _rank_in_slugs(row.expected_slug, flat)
    return rank, hits


# ───────────────────────────────────────────────────────────────────────────
# Markdown emission
# ───────────────────────────────────────────────────────────────────────────


def _format_score(v: float | None) -> str:
    return f"{v:+.3f}" if v is not None else "  -   "


def _emit_markdown(
    out_path: Path,
    strand_filter: str | None,
    total_rows: int,
    fail_rows: list[tuple[EvalInput, int | None, list[dict[str, Any]]]],
) -> None:
    lines: list[str] = []
    title_suffix = f" — strand={strand_filter}" if strand_filter else ""
    lines.append(f"# Per-row failure dump{title_suffix}")
    lines.append("")
    lines.append(f"**Rows scanned:** {total_rows}")
    lines.append(f"**Failures shown (rank > 1 or not in top-{TOP_K}):** {len(fail_rows)}")
    lines.append("")
    lines.append(
        "For each failure: the query, the expected slug + its strand, and the "
        "live top-K hits with their `reranker_score` / `cosine_similarity` / "
        "`text_match` from Cortex Search."
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Strand-grouped table-of-contents at the top so reviewers can jump.
    by_strand: dict[str, list[tuple[EvalInput, int | None]]] = defaultdict(list)
    for row, rank, _ in fail_rows:
        by_strand[_strand_of(row.expected_slug)].append((row, rank))
    if by_strand:
        lines.append("## Index")
        lines.append("")
        for strand in sorted(by_strand):
            lines.append(f"- **{strand}** ({len(by_strand[strand])})")
            for row, rank in by_strand[strand]:
                anchor = row.eval_id.replace("_", "-").lower()
                rank_s = str(rank) if rank is not None else "—"
                lines.append(f"  - [`{row.eval_id}`](#{anchor}) (rank {rank_s})")
        lines.append("")
        lines.append("---")
        lines.append("")

    for row, rank, hits in fail_rows:
        anchor = row.eval_id.replace("_", "-").lower()
        strand = _strand_of(row.expected_slug)
        rank_s = str(rank) if rank is not None else f"not in top-{TOP_K}"
        lines.append(f"### `{row.eval_id}`")
        lines.append("")
        lines.append(f"- **strand:** `{strand}`")
        lines.append(f"- **source:** `{row.source}`  ·  **difficulty:** `{row.difficulty}`")
        lines.append(f"- **expected slug:** `{row.expected_slug}`")
        lines.append(f"- **rank of expected slug:** {rank_s}")
        lines.append("")
        lines.append(f"**Query.** {row.question_text}")
        lines.append("")
        if not hits:
            lines.append("_No hits returned._")
            lines.append("")
            lines.append("---")
            lines.append("")
            continue

        lines.append("| rank | slug / part_id | reranker | cosine | text_match |")
        lines.append("|---:|---|---:|---:|---:|")
        for i, h in enumerate(hits, 1):
            slug = str(h.get("slug") or h.get("part_id") or "(?)")
            r, c, tm = _scores_for(h)
            lines.append(
                f"| {i} | `{slug}` | {_format_score(r)} | "
                f"{_format_score(c)} | {_format_score(tm)} |"
            )

        if row.source == "solution_cross_ref":
            lines.append("")
            lines.append(
                "_(cross-ref row: the expected slug is matched against the "
                "union of each part's `tutorials_referenced`, walked in result "
                "order — see `_score_solutions_search`.)_"
            )
            # Also dump the flattened tutorial slugs in the order the scorer
            # walks them, so the rank-vs-expected mismatch is obvious.
            flat: list[str] = []
            for h in hits:
                refs = h.get("tutorials_referenced") or []
                if isinstance(refs, str):
                    try:
                        refs = json.loads(refs)
                    except json.JSONDecodeError:
                        refs = []
                for s in refs:
                    if s not in flat:
                        flat.append(s)
                    if len(flat) >= TOP_K:
                        break
                if len(flat) >= TOP_K:
                    break
            if flat:
                lines.append("")
                lines.append("Flattened `tutorials_referenced` (rank order):")
                for i, s in enumerate(flat, 1):
                    marker = " ← expected" if s == row.expected_slug else ""
                    lines.append(f"{i}. `{s}`{marker}")

        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("Wrote %s (%d failure rows)", out_path, len(fail_rows))


# ───────────────────────────────────────────────────────────────────────────
# Orchestration
# ───────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument(
        "--only-golden-subset", action="store_true",
        help="Inspect only rows with is_in_golden_subset = TRUE.",
    )
    ap.add_argument(
        "--strand", type=str, default=None,
        help="Restrict to rows whose expected_slug belongs to this strand "
             "(e.g. 'algebra').",
    )
    ap.add_argument(
        "--from-csv", type=Path, default=None,
        help="Read eval rows from this CSV instead of Snowflake.",
    )
    ap.add_argument(
        "--out", type=Path,
        default=HERE / "algebra_failures_DAY_31.md",
        help="Where to write the Markdown dump.",
    )
    args = ap.parse_args(argv)

    if args.from_csv:
        log.info("Loading rows from CSV: %s", args.from_csv)
        rows = _load_rows_from_csv(args.from_csv.resolve(), args.only_golden_subset)
    else:
        log.info("Loading rows from RAW.EVAL_GOLDEN_SET")
        rows = _load_rows_from_snowflake(args.only_golden_subset)

    if args.strand:
        rows = [r for r in rows if _strand_of(r.expected_slug) == args.strand]
        log.info("After --strand=%s filter: %d rows", args.strand, len(rows))

    log.info("Inspecting %d rows", len(rows))

    try:
        import snowflake.connector  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "snowflake-connector-python is required for inspection."
        ) from exc

    conn = snowflake.connector.connect(**_build_conn_kwargs())
    fail_rows: list[tuple[EvalInput, int | None, list[dict[str, Any]]]] = []
    try:
        cs = conn.cursor()
        try:
            for i, row in enumerate(rows, 1):
                try:
                    if row.source == "phrasings":
                        rank, hits = _inspect_phrasings_row(cs, row)
                    elif row.source == "solution_cross_ref":
                        rank, hits = _inspect_xref_row(cs, row)
                    else:
                        rank, hits = _inspect_phrasings_row(cs, row)
                except Exception as exc:  # noqa: BLE001
                    log.warning("row %s raised: %s", row.eval_id, exc)
                    continue
                # Treat rank=None (not in top-K) or rank>1 as a failure.
                if rank is None or rank > 1:
                    fail_rows.append((row, rank, hits))
                if i % 50 == 0:
                    log.info("inspected %d / %d", i, len(rows))
                if INTER_QUERY_DELAY_S:
                    time.sleep(INTER_QUERY_DELAY_S)
        finally:
            cs.close()
    finally:
        conn.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    _emit_markdown(args.out, args.strand, len(rows), fail_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
