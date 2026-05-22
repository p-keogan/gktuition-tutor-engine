#!/usr/bin/env python3
"""Mark ~200 rows in EVAL_GOLDEN_SET as ``is_in_golden_subset = TRUE``.

The full auto-generated eval set (≥ 3,000 rows) is for breadth analysis.
The Week 13 milestone ("≥ 80% precision@1") is measured against a much
smaller hand-pickable subset — but we don't need to hand-pick from scratch.
This script does a stratified random selection so the human curator can
either:

* accept the auto-selected ~200 wholesale and proceed to scoring, or
* run this once, eyeball the picks, and only override the rows they
  disagree with (still cheaper than picking 200 from 3,000+).

Stratified selection
--------------------
::

    ~50  rows from the easiest tier ("auto-easy")     — short phrasings;
                                                        the trivial wins
    ~100 rows from the medium tier ("auto-medium")    — recent main-sitting
                                                        cross-refs; longer
                                                        phrasings with edge-
                                                        case framing
    ~50  rows from the hardest tier ("auto-hard")     — deferred sittings;
                                                        multi-tutorial parts
                                                        (>2 refs); phrasings
                                                        from low-frequency
                                                        strands

Within each tier the sampling balances ``source`` (so the golden subset
contains both phrasings and solution_cross_ref rows in roughly the same
ratio as the underlying eval set within that tier) and ``topic`` (so no
single strand dominates).

The script never picks more than one row per (source × expected_slug)
combination — variety beats redundancy at this size.

Usage
-----
::

    # Live (read from + write back to RAW.EVAL_GOLDEN_SET):
    python select_golden_subset.py

    # Offline (read + write the CSV in place):
    python select_golden_subset.py --from-csv eval_golden_set.csv \\
                                   --write-csv eval_golden_set.csv

    # Dry-run (compute + print, don't write anywhere):
    python select_golden_subset.py --dry-run --from-csv eval_golden_set.csv

The selection is deterministic given ``--seed`` (default 20260521 — the
DAY_26 ordinal date), so repeated runs produce the same golden subset.

Reset
-----
``--reset`` clears the flag on every row before re-selecting. Useful when
the eval set has grown since the last run and the previous subset is
stale.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
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
log = logging.getLogger("golden_subset")

# ───────────────────────────────────────────────────────────────────────────
# Constants
# ───────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent

# Per-tier target counts. The ~200 headline is the sum of these three.
TARGET_EASY = 50
TARGET_MEDIUM = 100
TARGET_HARD = 50
TARGETS = {
    "auto-easy": TARGET_EASY,
    "auto-medium": TARGET_MEDIUM,
    "auto-hard": TARGET_HARD,
}


# ───────────────────────────────────────────────────────────────────────────
# Data classes
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class EvalRowMin:
    eval_id: str
    expected_slug: str
    source: str
    difficulty: str
    source_metadata: dict[str, Any]
    is_in_golden_subset: bool


# ───────────────────────────────────────────────────────────────────────────
# Loaders
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


def _load_from_snowflake() -> list[EvalRowMin]:
    import snowflake.connector  # noqa: PLC0415

    conn = snowflake.connector.connect(**_build_conn_kwargs())
    try:
        cs = conn.cursor()
        try:
            cs.execute("""
                SELECT eval_id, expected_slug, source, difficulty,
                       source_metadata, is_in_golden_subset
                FROM GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET
            """)
            rows: list[EvalRowMin] = []
            for (eid, slug, src, diff, md_raw, golden) in cs:
                md = (
                    json.loads(md_raw) if isinstance(md_raw, str) else (md_raw or {})
                )
                rows.append(
                    EvalRowMin(
                        eval_id=eid, expected_slug=slug, source=src,
                        difficulty=diff,
                        source_metadata=md or {},
                        is_in_golden_subset=bool(golden),
                    )
                )
            return rows
        finally:
            cs.close()
    finally:
        conn.close()


def _load_from_csv(path: Path) -> list[EvalRowMin]:
    rows: list[EvalRowMin] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            try:
                md = json.loads(r.get("source_metadata") or "{}")
            except json.JSONDecodeError:
                md = {}
            rows.append(
                EvalRowMin(
                    eval_id=r["eval_id"],
                    expected_slug=r["expected_slug"],
                    source=r["source"],
                    difficulty=r.get("difficulty", ""),
                    source_metadata=md,
                    is_in_golden_subset=(
                        (r.get("is_in_golden_subset") or "FALSE").upper() == "TRUE"
                    ),
                )
            )
    return rows


# ───────────────────────────────────────────────────────────────────────────
# Selection
# ───────────────────────────────────────────────────────────────────────────
def _key_for_dedup(row: EvalRowMin) -> tuple[str, str]:
    """Variety beats redundancy: at most one row per (source × expected_slug)
    inside the golden subset."""
    return (row.source, row.expected_slug)


def _strand_of(row: EvalRowMin) -> str:
    """Coarse strand label inferred from expected_slug (e.g. ``the-line-4-…``
    → ``the-line``). This is what we diversify across — cross-ref topics
    are free-text English so they explode the topic count and would
    swamp the round-robin. Strand prefix is the stable common denominator."""
    slug = row.expected_slug
    # Two cases:
    #   the-line-4-...           → 'the-line'         (multi-word strand)
    #   algebra-15-...           → 'algebra'
    #   complex-numbers-10-...   → 'complex-numbers'
    # Strand always ends one segment before the first numeric segment.
    parts = slug.split("-")
    strand_parts: list[str] = []
    for p in parts:
        if p.isdigit():
            break
        strand_parts.append(p)
    return "-".join(strand_parts) or slug


def _balanced_sample(
    pool: list[EvalRowMin], target: int, rng: random.Random,
) -> list[EvalRowMin]:
    """Pull ``target`` rows from ``pool``, balancing across source and strand.

    Two-stage strategy:

    1. Split the pool by source and aim for roughly equal representation —
       cap each source at half the tier target (rounded), then top up from
       whichever source has more rows left if the other ran out.
    2. Within each source, round-robin across strand prefixes (derived from
       ``expected_slug``) so no single strand dominates.
    """
    if not pool:
        return []

    by_source: dict[str, list[EvalRowMin]] = defaultdict(list)
    for r in pool:
        by_source[r.source].append(r)

    sources = list(by_source.keys())
    if not sources:
        return []
    if len(sources) == 1:
        per_source = {sources[0]: target}
    else:
        # 50/50 split. Allocate any remainder deterministically.
        base = target // len(sources)
        per_source = {s: base for s in sources}
        for i in range(target - base * len(sources)):
            per_source[sources[i % len(sources)]] += 1

    chosen: list[EvalRowMin] = []
    seen_keys: set[tuple[str, str]] = set()
    leftover_pools: list[list[EvalRowMin]] = []

    for src, quota in per_source.items():
        sub_pool = list(by_source[src])
        rng.shuffle(sub_pool)
        by_strand: dict[str, list[EvalRowMin]] = defaultdict(list)
        for r in sub_pool:
            by_strand[_strand_of(r)].append(r)
        strands = list(by_strand.keys())
        rng.shuffle(strands)

        picked_this_source = 0
        wave = 1
        while picked_this_source < quota:
            added_this_wave = 0
            for strand in strands:
                if picked_this_source >= quota:
                    break
                quota_this_strand = sum(
                    1 for r in chosen
                    if r.source == src and _strand_of(r) == strand
                )
                if quota_this_strand >= wave:
                    continue
                for r in by_strand[strand]:
                    key = _key_for_dedup(r)
                    if key in seen_keys:
                        continue
                    chosen.append(r)
                    seen_keys.add(key)
                    picked_this_source += 1
                    added_this_wave += 1
                    break
            if added_this_wave == 0:
                break
            wave += 1

        # Whatever's left in this source's pool becomes top-up material if
        # another source ran short.
        leftover_pools.append([
            r for r in sub_pool if _key_for_dedup(r) not in seen_keys
        ])

    # Top up if any source ran short of its quota.
    if len(chosen) < target:
        leftover = [r for sub in leftover_pools for r in sub]
        rng.shuffle(leftover)
        for r in leftover:
            if len(chosen) >= target:
                break
            key = _key_for_dedup(r)
            if key in seen_keys:
                continue
            chosen.append(r)
            seen_keys.add(key)

    return chosen


def select_subset(
    rows: list[EvalRowMin], seed: int,
) -> list[EvalRowMin]:
    """Return the rows that should be flagged. Deterministic given seed."""
    rng = random.Random(seed)

    by_tier: dict[str, list[EvalRowMin]] = defaultdict(list)
    for r in rows:
        by_tier[r.difficulty].append(r)

    chosen: list[EvalRowMin] = []
    for tier, target in TARGETS.items():
        pool = list(by_tier.get(tier, []))
        picks = _balanced_sample(pool, target, rng)
        log.info("tier=%s target=%d picked=%d available=%d",
                 tier, target, len(picks), len(pool))
        chosen.extend(picks)

    return chosen


# ───────────────────────────────────────────────────────────────────────────
# Writers
# ───────────────────────────────────────────────────────────────────────────
def _write_to_snowflake(
    chosen_ids: set[str], reset_first: bool,
) -> tuple[int, int]:
    """UPDATE is_in_golden_subset. Returns (cleared, set_true)."""
    import snowflake.connector  # noqa: PLC0415

    conn = snowflake.connector.connect(**_build_conn_kwargs())
    cleared = updated = 0
    try:
        cs = conn.cursor()
        try:
            if reset_first:
                cs.execute("""
                    UPDATE GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET
                    SET is_in_golden_subset = FALSE
                    WHERE is_in_golden_subset
                """)
                cleared = cs.rowcount or 0
            # Chunked UPDATE — Snowflake accepts large IN lists but we cap at
            # 10k to stay friendly.
            ids = sorted(chosen_ids)
            CHUNK = 5_000
            for i in range(0, len(ids), CHUNK):
                batch = ids[i:i + CHUNK]
                placeholders = ", ".join(["%s"] * len(batch))
                cs.execute(
                    f"""
                    UPDATE GKTUITION_TUTOR.RAW.EVAL_GOLDEN_SET
                    SET is_in_golden_subset = TRUE
                    WHERE eval_id IN ({placeholders})
                    """,
                    batch,
                )
                updated += cs.rowcount or 0
        finally:
            cs.close()
    finally:
        conn.close()
    return cleared, updated


def _rewrite_csv(
    csv_in: Path, csv_out: Path, chosen_ids: set[str], reset_first: bool,
) -> int:
    """Stream csv_in to csv_out, flipping is_in_golden_subset to TRUE for
    every eval_id in ``chosen_ids``. Returns the count flipped to TRUE."""
    n_set = 0
    with csv_in.open(newline="", encoding="utf-8") as fr:
        reader = csv.DictReader(fr)
        fieldnames = reader.fieldnames or []
        rows = list(reader)
    for r in rows:
        if reset_first:
            r["is_in_golden_subset"] = "FALSE"
        if r["eval_id"] in chosen_ids:
            r["is_in_golden_subset"] = "TRUE"
            n_set += 1
    csv_out.parent.mkdir(parents=True, exist_ok=True)
    with csv_out.open("w", newline="", encoding="utf-8") as fw:
        writer = csv.DictWriter(fw, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return n_set


# ───────────────────────────────────────────────────────────────────────────
# Orchestration
# ───────────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__.splitlines()[0] if __doc__ else None,
    )
    ap.add_argument(
        "--from-csv", type=Path, default=None,
        help="Read rows from CSV instead of Snowflake.",
    )
    ap.add_argument(
        "--write-csv", type=Path, default=None,
        help="Write the updated CSV here. Default: same path as --from-csv.",
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Compute and print the selection; don't write anywhere.",
    )
    ap.add_argument(
        "--reset", action="store_true",
        help="Clear is_in_golden_subset on every row before re-selecting.",
    )
    ap.add_argument(
        "--seed", type=int, default=20260521,
        help="RNG seed (deterministic by default).",
    )
    args = ap.parse_args(argv)

    if args.from_csv:
        log.info("Loading rows from CSV: %s", args.from_csv)
        rows = _load_from_csv(args.from_csv.resolve())
    else:
        log.info("Loading rows from RAW.EVAL_GOLDEN_SET")
        rows = _load_from_snowflake()
    log.info("Loaded %d rows", len(rows))

    chosen = select_subset(rows, seed=args.seed)
    chosen_ids = {r.eval_id for r in chosen}
    log.info("Selected %d rows total (target: %d)",
             len(chosen), sum(TARGETS.values()))

    # Print distribution summary.
    by_tier_n = defaultdict(int)
    by_src_n = defaultdict(int)
    for r in chosen:
        by_tier_n[r.difficulty] += 1
        by_src_n[r.source] += 1
    log.info("By tier: %s", dict(by_tier_n))
    log.info("By source: %s", dict(by_src_n))

    if args.dry_run:
        log.info("--dry-run: skipping writes.")
        return 0

    if args.from_csv:
        out_csv = args.write_csv.resolve() if args.write_csv else args.from_csv.resolve()
        n = _rewrite_csv(
            args.from_csv.resolve(), out_csv, chosen_ids, reset_first=args.reset,
        )
        log.info("CSV rewritten: %s  (rows set to TRUE: %d)", out_csv, n)
    else:
        cleared, updated = _write_to_snowflake(chosen_ids, reset_first=args.reset)
        log.info("Snowflake: cleared=%d  set_true=%d", cleared, updated)

    return 0


if __name__ == "__main__":
    sys.exit(main())
