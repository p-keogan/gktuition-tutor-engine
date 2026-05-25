#!/usr/bin/env python3
"""Score the EVAL_GOLDEN_SET against the live Cortex Search Services.

For each row, query the appropriate service, capture the top-K results, and
compute three retrieval-quality metrics:

* ``precision@1`` — was the expected_slug returned at rank 1?
* ``recall@5``    — does the expected_slug appear anywhere in the top 5?
* ``MRR``         — reciprocal of the rank at which the expected_slug first
                    appears (0 if it never appears in the top K).

Routing
-------
::

    source = 'phrasings'           → TUTOR_SEARCH
    source = 'solution_cross_ref'  → SOLUTIONS_SEARCH
                                     (with optional TUTOR_SEARCH fallback if
                                      the cross-ref expected_slug is not in
                                      any returned part's tutorials_referenced)

For SOLUTIONS_SEARCH the returned objects are exam-part rows, not tutorial
slugs. Each part carries a ``tutorials_referenced`` array; the expected_slug
is checked against the union of those arrays across the top-K parts. The
*rank* of the expected slug is the index of the first part whose
``tutorials_referenced`` contains it.

The ``--ambiguous-both`` flag re-issues every cross-ref query against
TUTOR_SEARCH as well (and picks the better of the two ranks for MRR /
recall@5). Off by default — the SOLUTIONS_SEARCH route is the architectural
intent for exam-question utterances.

Outputs
-------
* Markdown report at ``eval/scoring_report_{YYYYMMDD}_{HHMM}.md`` (the
  timestamp is intentional — running twice on the same day produces two
  reports rather than overwriting).
* Per-row scoring CSV at ``eval/scoring_rows_{YYYYMMDD}_{HHMM}.csv`` so
  later analysis can drill into specific failures.

Usage
-----
::

    # Score everything in RAW.EVAL_GOLDEN_SET against the live services:
    python score_against_cortex_search.py

    # Only the golden subset (Week 13 milestone signal):
    python score_against_cortex_search.py --only-golden-subset

    # Subsample for quick iteration (50 random rows per source):
    python score_against_cortex_search.py --sample-per-source 50

    # Read rows from the CSV instead of Snowflake (offline-friendly):
    python score_against_cortex_search.py --from-csv eval_golden_set.csv

Environment
-----------
Same SNOWFLAKE_* variables as build_eval_set.py. The Cortex Search queries
use ``SNOWFLAKE.CORTEX.SEARCH_PREVIEW`` via the standard connector — no
additional dependency.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ───────────────────────────────────────────────────────────────────────────
# Logging
# ───────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("score")

# ───────────────────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
TOP_K = 5

TUTOR_SEARCH = "GKTUITION_TUTOR.CORTEX.TUTOR_SEARCH"
SOLUTIONS_SEARCH = "GKTUITION_TUTOR.CORTEX.SOLUTIONS_SEARCH"

# Cortex Search Preview is rate-limited per warehouse. A small delay between
# calls keeps us well under the published per-second quota and avoids
# tripping retry logic in the connector.
INTER_QUERY_DELAY_S = 0.05


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class EvalInput:
    eval_id: str
    question_text: str
    expected_slug: str
    source: str
    difficulty: str
    is_in_golden_subset: bool
    source_metadata: dict[str, Any]


@dataclass
class RowResult:
    eval_id: str
    source: str
    difficulty: str
    expected_slug: str
    topic: str | None
    rank: int | None  # 1-indexed; None if not in top-K
    p_at_1: int
    r_at_5: int
    mrr: float
    service_used: str
    top_k_slugs: list[str]
    error: str | None = None


@dataclass
class Aggregate:
    n: int = 0
    p_at_1_sum: int = 0
    r_at_5_sum: int = 0
    mrr_sum: float = 0.0
    errors: int = 0

    def add(self, r: RowResult) -> None:
        self.n += 1
        if r.error:
            self.errors += 1
            return
        self.p_at_1_sum += r.p_at_1
        self.r_at_5_sum += r.r_at_5
        self.mrr_sum += r.mrr

    def metrics(self) -> dict[str, float]:
        scored = max(self.n - self.errors, 1)
        return {
            "precision@1": self.p_at_1_sum / scored,
            "recall@5": self.r_at_5_sum / scored,
            "mrr": self.mrr_sum / scored,
        }


# ───────────────────────────────────────────────────────────────────────────
# Snowflake helpers
# ───────────────────────────────────────────────────────────────────────────
def _build_conn_kwargs() -> dict[str, Any]:
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    user = os.environ.get("SNOWFLAKE_USER")
    if not account or not user:
        raise RuntimeError(
            "SNOWFLAKE_ACCOUNT and SNOWFLAKE_USER must be set."
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
        kw["authenticator"] = os.environ.get("SNOWFLAKE_AUTHENTICATOR",
                                             "SNOWFLAKE_JWT")
    elif password := os.environ.get("SNOWFLAKE_PASSWORD"):
        kw["password"] = password
    else:
        raise RuntimeError(
            "Either SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH must be set."
        )
    return kw


def _load_rows_from_snowflake(
    only_golden_subset: bool,
) -> list[EvalInput]:
    import snowflake.connector  # noqa: PLC0415

    conn = snowflake.connector.connect(**_build_conn_kwargs())
    try:
        cs = conn.cursor()
        try:
            where = "WHERE is_in_golden_subset" if only_golden_subset else ""
            cs.execute(f"""
                SELECT eval_id, question_text, expected_slug, source, difficulty,
                       is_in_golden_subset, source_metadata
                FROM GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET
                {where}
            """)
            rows: list[EvalInput] = []
            for (eid, q, slug, src, diff, golden, md_raw) in cs:
                md = (
                    json.loads(md_raw) if isinstance(md_raw, str) else (md_raw or {})
                )
                rows.append(
                    EvalInput(
                        eval_id=eid, question_text=q, expected_slug=slug,
                        source=src, difficulty=diff,
                        is_in_golden_subset=bool(golden),
                        source_metadata=md,
                    )
                )
            return rows
        finally:
            cs.close()
    finally:
        conn.close()


def _load_rows_from_csv(
    csv_path: Path, only_golden_subset: bool,
) -> list[EvalInput]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    rows: list[EvalInput] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            in_golden = r.get("is_in_golden_subset", "FALSE").upper() == "TRUE"
            if only_golden_subset and not in_golden:
                continue
            md_raw = r.get("source_metadata") or "{}"
            try:
                md = json.loads(md_raw)
            except json.JSONDecodeError:
                md = {}
            rows.append(
                EvalInput(
                    eval_id=r["eval_id"],
                    question_text=r["question_text"],
                    expected_slug=r["expected_slug"],
                    source=r["source"],
                    difficulty=r.get("difficulty", ""),
                    is_in_golden_subset=in_golden,
                    source_metadata=md,
                )
            )
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Cortex Search Preview wrapper
# ───────────────────────────────────────────────────────────────────────────
def _search_preview(cursor, service_fqn: str, query: str, columns: list[str],
                    limit: int = TOP_K) -> list[dict[str, Any]]:
    """Issue a SEARCH_PREVIEW against ``service_fqn`` and return the parsed
    ``results`` list. Mirrors the smoke-test query embedded in
    ``create_tutor_search_service.sql`` / ``create_solutions_search_service.sql``.
    """
    payload = {
        "query": query,
        "columns": columns,
        "limit": limit,
    }
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
    # Snowflake returns ARRAY of OBJECTs; the connector hands them back as
    # JSON-encoded strings.
    if isinstance(results, str):
        results = json.loads(results)
    return list(results)


# ───────────────────────────────────────────────────────────────────────────
# Scoring
# ───────────────────────────────────────────────────────────────────────────
def _rank_in_slugs(expected: str, slugs: list[str]) -> int | None:
    """1-indexed rank of ``expected`` in ``slugs``; None if absent."""
    for i, s in enumerate(slugs, 1):
        if s == expected:
            return i
    return None


def _best_rank_over_slugs(
    valid_slugs: set[str], ranked: list[str],
) -> int | None:
    """Best (lowest) 1-indexed rank of any slug in ``valid_slugs`` within
    ``ranked``; None if no slug in ``valid_slugs`` appears in ``ranked``.

    Used by ``_score_solutions_search`` for cross-ref rows where an exam-part
    references multiple tutorials. The eval set arbitrarily pins one as
    ``expected_slug``, but **any** of the referenced tutorials at rank 1 is a
    legitimate hit — they all describe the same exam question from the
    curriculum-judging author's viewpoint.
    """
    best: int | None = None
    for slug in valid_slugs:
        rank = _rank_in_slugs(slug, ranked)
        if rank is not None and (best is None or rank < best):
            best = rank
    return best


def _build_part_id_to_referenced_slugs(
    rows: list[EvalInput],
) -> dict[str, set[str]]:
    """For ``source='solution_cross_ref'`` rows the eval set emits one row per
    ``(part_id, expected_slug)`` pair. Group by ``part_id`` to recover the
    full ``tutorials_referenced`` set for each exam-part — that set is what
    counts as a "hit" under the recall@1-over-refs scoring rule.
    """
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.source != "solution_cross_ref":
            continue
        part_id = row.source_metadata.get("part_id")
        if not part_id:
            continue
        mapping[part_id].add(row.expected_slug)
    return mapping


def _score_tutor_search(
    cursor, row: EvalInput,
) -> RowResult:
    hits = _search_preview(
        cursor, TUTOR_SEARCH, row.question_text,
        columns=["slug", "title", "topic"],
    )
    slugs = [h.get("slug", "") for h in hits]
    topics_seen = next((h.get("topic") for h in hits if h.get("topic")), None)
    rank = _rank_in_slugs(row.expected_slug, slugs)
    return _build_row_result(row, slugs, rank, TUTOR_SEARCH, topics_seen)


def _score_solutions_search(
    cursor,
    row: EvalInput,
    also_try_tutor: bool,
    valid_slugs_for_row: set[str] | None = None,
) -> RowResult:
    """Score a cross-ref row against SOLUTIONS_SEARCH.

    ``valid_slugs_for_row`` is the full set of ``tutorials_referenced`` for
    this row's exam-part (recovered by grouping eval rows on ``part_id``).
    A hit is counted if **any** slug in that set lands at the same rank as
    the best match in the flattened result ranking. When ``valid_slugs_for_row``
    is ``None`` or empty, falls back to the legacy single-expected-slug rule
    for backward compatibility.
    """
    hits = _search_preview(
        cursor, SOLUTIONS_SEARCH, row.question_text,
        columns=["part_id", "topic", "tutorials_referenced"],
    )
    # Flatten tutorials_referenced in result order to build a slug ranking.
    ranked: list[str] = []
    topic_for_report: str | None = None
    for h in hits:
        if topic_for_report is None and h.get("topic"):
            topic_for_report = h.get("topic")
        refs = h.get("tutorials_referenced") or []
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except json.JSONDecodeError:
                refs = []
        for slug in refs:
            if slug not in ranked:
                ranked.append(slug)
            if len(ranked) >= TOP_K:
                break
        if len(ranked) >= TOP_K:
            break

    # New scoring rule: a cross-ref row whose exam-part references multiple
    # tutorials is a hit if any of those tutorials lands at rank 1 (not just
    # the arbitrarily-pinned ``expected_slug``). See eval/README.md for the
    # rationale.
    if valid_slugs_for_row:
        rank = _best_rank_over_slugs(valid_slugs_for_row, ranked)
    else:
        rank = _rank_in_slugs(row.expected_slug, ranked)

    # Optional ambiguous-both fallback: try TUTOR_SEARCH and keep the better
    # rank for MRR/recall@5 calculation.
    service = SOLUTIONS_SEARCH
    if also_try_tutor:
        tut_hits = _search_preview(
            cursor, TUTOR_SEARCH, row.question_text,
            columns=["slug", "title"],
        )
        tut_slugs = [h.get("slug", "") for h in tut_hits]
        if valid_slugs_for_row:
            tut_rank = _best_rank_over_slugs(valid_slugs_for_row, tut_slugs)
        else:
            tut_rank = _rank_in_slugs(row.expected_slug, tut_slugs)
        # Take the better of the two ranks.
        if tut_rank is not None and (rank is None or tut_rank < rank):
            rank = tut_rank
            ranked = tut_slugs
            service = f"{SOLUTIONS_SEARCH}+{TUTOR_SEARCH}"

    return _build_row_result(row, ranked, rank, service, topic_for_report)


def _build_row_result(
    row: EvalInput, top_k_slugs: list[str], rank: int | None,
    service: str, topic: str | None,
) -> RowResult:
    p_at_1 = 1 if rank == 1 else 0
    r_at_5 = 1 if (rank is not None and rank <= TOP_K) else 0
    mrr = (1.0 / rank) if rank is not None else 0.0
    return RowResult(
        eval_id=row.eval_id,
        source=row.source,
        difficulty=row.difficulty,
        expected_slug=row.expected_slug,
        topic=topic or row.source_metadata.get("topic"),
        rank=rank,
        p_at_1=p_at_1,
        r_at_5=r_at_5,
        mrr=mrr,
        service_used=service,
        top_k_slugs=top_k_slugs[:TOP_K],
    )


# ───────────────────────────────────────────────────────────────────────────
# Reporting
# ───────────────────────────────────────────────────────────────────────────
def _emit_markdown_report(
    results: list[RowResult], out_path: Path,
    overall: Aggregate, by_source: dict[str, Aggregate],
    by_topic: dict[str, Aggregate], by_difficulty: dict[str, Aggregate],
    args: argparse.Namespace,
) -> None:
    lines: list[str] = []
    lines.append("# Cortex Search scoring report")
    lines.append("")
    lines.append(f"**Run timestamp:** {datetime.now().isoformat(timespec='seconds')}")
    lines.append(f"**Rows scored:** {overall.n}  "
                 f"(errors during query: {overall.errors})")
    lines.append(f"**Source filter:** "
                 f"{'golden subset only' if args.only_golden_subset else 'full eval set'}"
                 f"  ·  top-K = {TOP_K}")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    m = overall.metrics()
    lines.append(
        f"- **precision@1**: {m['precision@1']:.3f}\n"
        f"- **recall@5**: {m['recall@5']:.3f}\n"
        f"- **MRR**: {m['mrr']:.3f}"
    )
    lines.append("")
    lines.append("## By source")
    lines.append("")
    lines.append("| source | n | precision@1 | recall@5 | MRR | errors |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for src in sorted(by_source):
        agg = by_source[src]
        sm = agg.metrics()
        lines.append(
            f"| {src} | {agg.n} | {sm['precision@1']:.3f} | "
            f"{sm['recall@5']:.3f} | {sm['mrr']:.3f} | {agg.errors} |"
        )
    lines.append("")
    lines.append("## By difficulty tier")
    lines.append("")
    lines.append("| difficulty | n | precision@1 | recall@5 | MRR |")
    lines.append("|---|---:|---:|---:|---:|")
    for tier in ("auto-easy", "auto-medium", "auto-hard"):
        agg = by_difficulty.get(tier)
        if not agg:
            continue
        sm = agg.metrics()
        lines.append(
            f"| {tier} | {agg.n} | {sm['precision@1']:.3f} | "
            f"{sm['recall@5']:.3f} | {sm['mrr']:.3f} |"
        )
    lines.append("")
    lines.append("## By topic (weakest first)")
    lines.append("")
    topics = [
        (t, a) for t, a in by_topic.items() if a.n - a.errors >= 5
    ]
    topics.sort(key=lambda kv: kv[1].metrics()["precision@1"])
    lines.append("| topic | n | precision@1 | recall@5 | MRR |")
    lines.append("|---|---:|---:|---:|---:|")
    for t, a in topics:
        sm = a.metrics()
        lines.append(
            f"| {t} | {a.n} | {sm['precision@1']:.3f} | "
            f"{sm['recall@5']:.3f} | {sm['mrr']:.3f} |"
        )
    lines.append("")
    lines.append("## Sample failures (precision@1 == 0, expected absent from top-5)")
    lines.append("")
    fails = [r for r in results if r.r_at_5 == 0 and not r.error][:30]
    if not fails:
        lines.append("_No top-5 misses recorded._")
    else:
        lines.append("| eval_id | source | expected | top-1 returned |")
        lines.append("|---|---|---|---|")
        for r in fails:
            top1 = r.top_k_slugs[0] if r.top_k_slugs else "(none)"
            lines.append(
                f"| `{r.eval_id}` | {r.source} | `{r.expected_slug}` | `{top1}` |"
            )

    lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _emit_rows_csv(results: list[RowResult], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "eval_id", "source", "difficulty", "expected_slug", "topic",
            "rank", "precision@1", "recall@5", "mrr",
            "service_used", "top_k_slugs", "error",
        ])
        for r in results:
            writer.writerow([
                r.eval_id, r.source, r.difficulty, r.expected_slug,
                r.topic or "",
                r.rank if r.rank is not None else "",
                r.p_at_1, r.r_at_5, f"{r.mrr:.4f}",
                r.service_used,
                ",".join(r.top_k_slugs),
                r.error or "",
            ])


# ───────────────────────────────────────────────────────────────────────────
# Orchestration
# ───────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    ap.add_argument(
        "--only-golden-subset", action="store_true",
        help="Score only rows with is_in_golden_subset = TRUE.",
    )
    ap.add_argument(
        "--sample-per-source", type=int, default=0,
        help="If > 0, score a random sample of N rows from each source.",
    )
    ap.add_argument(
        "--from-csv", type=Path, default=None,
        help="Read eval rows from this CSV instead of Snowflake. Note: the "
             "Cortex Search queries still need Snowflake credentials.",
    )
    ap.add_argument(
        "--ambiguous-both", action="store_true",
        help="For cross-ref rows, also issue the query against TUTOR_SEARCH "
             "and take the better rank for scoring.",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=HERE,
        help="Where to write the report + per-row CSV. Default: eval/.",
    )
    ap.add_argument(
        "--seed", type=int, default=20260521,
        help="RNG seed for --sample-per-source (deterministic by default).",
    )
    args = ap.parse_args(argv)

    if args.from_csv:
        log.info("Loading rows from CSV: %s", args.from_csv)
        rows = _load_rows_from_csv(args.from_csv.resolve(), args.only_golden_subset)
    else:
        log.info("Loading rows from RAW.EVAL_GOLDEN_SET")
        rows = _load_rows_from_snowflake(args.only_golden_subset)

    log.info("Loaded %d rows", len(rows))

    if args.sample_per_source > 0:
        random.seed(args.seed)
        by_src: dict[str, list[EvalInput]] = defaultdict(list)
        for r in rows:
            by_src[r.source].append(r)
        sampled: list[EvalInput] = []
        for src, items in by_src.items():
            k = min(args.sample_per_source, len(items))
            sampled.extend(random.sample(items, k))
            log.info("  sampled %d from source=%s", k, src)
        rows = sampled
        log.info("After sampling: %d rows", len(rows))

    # Connection for the search queries.
    try:
        import snowflake.connector  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "snowflake-connector-python is required for scoring."
        ) from exc

    # Precompute part_id -> {tutorials_referenced} so the cross-ref scorer
    # can apply the recall@1-over-refs rule documented in eval/README.md.
    part_id_to_refs = _build_part_id_to_referenced_slugs(rows)

    log.info("Opening Snowflake connection for SEARCH_PREVIEW")
    conn = snowflake.connector.connect(**_build_conn_kwargs())
    results: list[RowResult] = []
    try:
        cs = conn.cursor()
        try:
            for i, row in enumerate(rows, 1):
                try:
                    if row.source == "phrasings":
                        rr = _score_tutor_search(cs, row)
                    elif row.source == "solution_cross_ref":
                        part_id = row.source_metadata.get("part_id")
                        valid_for_row = (
                            part_id_to_refs.get(part_id) if part_id else None
                        )
                        rr = _score_solutions_search(
                            cs, row,
                            also_try_tutor=args.ambiguous_both,
                            valid_slugs_for_row=valid_for_row,
                        )
                    else:
                        # Unknown source — score against TUTOR_SEARCH as a
                        # safe default; flag in the report.
                        rr = _score_tutor_search(cs, row)
                        rr.error = f"unknown source: {row.source}"
                except Exception as exc:  # noqa: BLE001
                    rr = RowResult(
                        eval_id=row.eval_id, source=row.source,
                        difficulty=row.difficulty,
                        expected_slug=row.expected_slug, topic=None,
                        rank=None, p_at_1=0, r_at_5=0, mrr=0.0,
                        service_used="(error)", top_k_slugs=[],
                        error=str(exc),
                    )
                results.append(rr)
                if i % 100 == 0:
                    log.info("scored %d / %d", i, len(rows))
                if INTER_QUERY_DELAY_S:
                    time.sleep(INTER_QUERY_DELAY_S)
        finally:
            cs.close()
    finally:
        conn.close()

    # Aggregate.
    overall = Aggregate()
    by_source: dict[str, Aggregate] = defaultdict(Aggregate)
    by_topic: dict[str, Aggregate] = defaultdict(Aggregate)
    by_difficulty: dict[str, Aggregate] = defaultdict(Aggregate)
    for r in results:
        overall.add(r)
        by_source[r.source].add(r)
        if r.topic:
            by_topic[r.topic].add(r)
        if r.difficulty:
            by_difficulty[r.difficulty].add(r)

    # Emit.
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.out_dir / f"scoring_report_{stamp}.md"
    rows_csv_path = args.out_dir / f"scoring_rows_{stamp}.csv"
    _emit_markdown_report(
        results, report_path, overall, by_source, by_topic, by_difficulty, args,
    )
    _emit_rows_csv(results, rows_csv_path)

    log.info("Report:    %s", report_path)
    log.info("Per-row:   %s", rows_csv_path)
    om = overall.metrics()
    log.info("Overall:   precision@1=%.3f  recall@5=%.3f  MRR=%.3f  (errors=%d)",
             om["precision@1"], om["recall@5"], om["mrr"], overall.errors)
    return 0


if __name__ == "__main__":
    sys.exit(main())
