#!/usr/bin/env python3
"""Build a deterministic, bounded, cached query-rewrite cache — Snowflake-exit
Phase-0 **v3** (AGENT_32).

Why this exists
===============
AGENT_31's v2 gate (``local-hybrid``) fed retrieval the **raw** golden prompts
and NO-GO'd at P@1 = 0.497. But the *live* system runs a query-rewrite layer
(AGENT_21's ``maybe_rewrite`` + AGENT_24's ``maybe_rewrite_fallback``) on exactly
the awkward prompts that sink the offline gate, so v2 *understates* production.
This script closes that gap: it replicates production's rewrite-firing logic
verbatim (importing ``api/orchestrator/query_rewrite.py`` read-only) and, for the
rows that fire, generates the rewritten query with the **same Haiku model
production uses**, caching every result to disk so all downstream scoring is
offline, free, and reproducible.

Production fidelity
===================
Two firing mechanisms, mirrored exactly:

* **iter-1** (``maybe_rewrite``): fires PRE-retrieval on a conceptual framing —
  ``query_class == CONCEPT`` AND a conceptual prefix ("explain", "what is", …)
  AND ≤ 4 content tokens AND no domain-language signal (``=`` ``²`` ``√``
  "prove" "derive" …). Production rewrites these *before* retrieving.
* **fallback / iter-2** (``maybe_rewrite_fallback``): fires POST-retrieval, only
  when the first retrieve came back **sub-floor** (top score < RETRIEVAL_FLOOR =
  0.30), with a looser pre-check (no prefix gate; ≤ 6 content tokens). We use the
  **dense (arctic) top-1 cosine** from AGENT_31's checkpoint as the offline
  sub-floor signal — the hybrid RRF score is normalised so its top is always 1.0
  (v2 §5) and therefore unusable as a floor, whereas the arctic cosine is a real
  [0, 1] confidence directly comparable to RETRIEVAL_FLOOR and is the offline
  analogue of production's reranker/cosine floor.

Query class
===========
The golden set carries no ``query_class`` column and the production classifier is
not importable offline (Snowflake deps). We therefore treat **every row as
``CONCEPT``** — the *maximally generous* firing assumption. Real production would
classify the cryptic ``solution_cross_ref`` exam prompts as ``solution_lookup``
(routed to SOLUTIONS_SEARCH, never the CONCEPT-gated rewriter), so production
fires on a **subset** of what this script counts. Every fire-rate / lift number
here is thus an **upper bound** on what production rewriting can achieve.

Spend discipline (the single relaxation vs prior key-free spikes)
=================================================================
* Counts firing rows and prints an estimated cost BEFORE any paid call.
* Honours ``--max-rewrites N`` (default 1500) — caps actual LLM calls.
* Idempotent / resumable: rows already in the cache are skipped on re-run.
* If no Anthropic key / SDK is available, writes the **firing decisions only**
  (``rewritten_query`` left empty) and prints the exact operator one-liner. No
  fake rewrites are ever written.

Output: ``eval/rewrite_cache.csv`` keyed by ``eval_id`` with columns
``eval_id, source, fired, mechanism, original_query, rewritten_query``.

Usage (offline firing analysis; no key needed)::

    python eval/build_rewrite_cache.py --dry-run

Usage (operator, with key — generates the rewrites)::

    ANTHROPIC_API_KEY=sk-... python eval/build_rewrite_cache.py --max-rewrites 1500
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import parity_harness as ph  # noqa: E402

# Read-only reuse of the EXACT production rewrite logic (additive; never modified).
from api.orchestrator import query_rewrite as qr  # noqa: E402
from api.orchestrator.contract import QueryClass  # noqa: E402

CACHE_PATH = HERE / "rewrite_cache.csv"
CACHE_FIELDS = ("eval_id", "source", "fired", "mechanism", "original_query",
                "rewritten_query")

# Sub-floor signal source: AGENT_31's arctic dense checkpoint (top-1 cosine).
CKPT_DIR = Path(os.environ.get("LOCAL_PARITY_CKPT_DIR", "/tmp/hybrid_parity_ckpt"))
ARCTIC_CKPT = CKPT_DIR / "local-arctic-cosine.jsonl"
RETRIEVAL_FLOOR = ph.RETRIEVAL_FLOOR  # 0.30, mirrored from the live retriever.

# --- Cost estimate constants (Haiku 4.5). Documented list prices as of 2026-05;
# treat as an ESTIMATE and confirm against current pricing before a large run. ---
HAIKU_INPUT_USD_PER_MTOK = 1.0
HAIKU_OUTPUT_USD_PER_MTOK = 5.0
# System prompt is ~150 tokens; the query user-prompt ~25; output capped at 50.
EST_INPUT_TOKENS_PER_CALL = 175
EST_OUTPUT_TOKENS_PER_CALL = 50


def _est_cost_usd(n_calls: int) -> float:
    return (
        n_calls * EST_INPUT_TOKENS_PER_CALL / 1_000_000 * HAIKU_INPUT_USD_PER_MTOK
        + n_calls * EST_OUTPUT_TOKENS_PER_CALL / 1_000_000 * HAIKU_OUTPUT_USD_PER_MTOK
    )


def _load_arctic_top1() -> dict[str, float]:
    """eval_id -> dense (arctic) top-1 cosine, from AGENT_31's checkpoint."""
    out: dict[str, float] = {}
    if not ARCTIC_CKPT.is_file():
        return out
    for line in ARCTIC_CKPT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        hits = rec.get("hits") or []
        out[rec["eval_id"]] = float(hits[0][1]) if hits else 0.0
    return out


def classify_firing(
    row: ph.EvalInput, arctic_top1: dict[str, float],
) -> str | None:
    """Replicate production's firing decision. Returns 'iter1' | 'fallback' | None.

    query_class is treated as CONCEPT for every row (see module docstring — the
    maximally-generous assumption that makes the result an upper bound).
    """
    q = row.question_text
    # iter-1: pre-retrieval conceptual rewrite.
    if qr._should_rewrite(q, QueryClass.CONCEPT):
        return "iter1"
    # fallback: only when the first (dense) retrieve came back sub-floor AND the
    # looser pre-check accepts the query.
    top1 = arctic_top1.get(row.eval_id, 0.0)
    if top1 < RETRIEVAL_FLOOR and qr._should_rewrite_fallback(q, QueryClass.CONCEPT):
        return "fallback"
    return None


def _have_anthropic() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _load_existing_cache() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    if not CACHE_PATH.is_file():
        return out
    with CACHE_PATH.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out[r["eval_id"]] = r
    return out


def _write_cache(records: list[dict[str, str]]) -> None:
    records = sorted(records, key=lambda r: r["eval_id"])
    with CACHE_PATH.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CACHE_FIELDS)
        w.writeheader()
        for rec in records:
            w.writerow(rec)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-rewrites", type=int, default=1500,
                    help="Cap on actual LLM rewrite calls (default 1500).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute + print the firing analysis and cost, write "
                         "firing decisions with empty rewrites, make NO LLM calls.")
    ap.add_argument("--subset", action="store_true",
                    help="Restrict to the ~200-row golden subset.")
    args = ap.parse_args(argv)

    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=args.subset)
    arctic_top1 = _load_arctic_top1()
    if not arctic_top1:
        print(f"WARNING: arctic checkpoint not found at {ARCTIC_CKPT}; the "
              f"sub-floor (fallback) trigger cannot be evaluated. Build it with "
              f"`python eval/run_hybrid_parity.py score local-arctic-cosine` first.",
              file=sys.stderr)

    # 1) Firing analysis (deterministic, free).
    firing: dict[str, str] = {}
    by_mech_src: dict[tuple[str, str], int] = {}
    for r in rows:
        mech = classify_firing(r, arctic_top1)
        if mech:
            firing[r.eval_id] = mech
            by_mech_src[(mech, r.source)] = by_mech_src.get((mech, r.source), 0) + 1

    n_fire = len(firing)
    print("=" * 68)
    print(f"REWRITE FIRING ANALYSIS  ·  rows={len(rows)}  "
          f"({'subset' if args.subset else 'full'})")
    print("=" * 68)
    n_iter1 = sum(1 for m in firing.values() if m == "iter1")
    n_fb = sum(1 for m in firing.values() if m == "fallback")
    print(f"  iter-1 (pre-retrieval conceptual) : {n_iter1}")
    print(f"  fallback (sub-floor, post-retrieve): {n_fb}")
    print(f"  TOTAL firing rows                  : {n_fire}  "
          f"({100 * n_fire / max(len(rows), 1):.1f}% of set)")
    print("  by mechanism × source:")
    for (mech, src), c in sorted(by_mech_src.items()):
        print(f"    {mech:<9} {src:<22} {c}")

    # 2) Cost pre-acknowledgement (BEFORE any spend).
    n_to_call = min(n_fire, args.max_rewrites)
    est = _est_cost_usd(n_to_call)
    print("-" * 68)
    print(f"  Haiku model              : {qr._REWRITE_MODEL}")
    print(f"  --max-rewrites cap       : {args.max_rewrites}")
    print(f"  rewrite calls to make    : {n_to_call}")
    print(f"  est tokens/call          : ~{EST_INPUT_TOKENS_PER_CALL} in / "
          f"{EST_OUTPUT_TOKENS_PER_CALL} out")
    print(f"  ESTIMATED COST           : ~${est:.4f} USD "
          f"(@ ${HAIKU_INPUT_USD_PER_MTOK}/{HAIKU_OUTPUT_USD_PER_MTOK} per MTok; "
          f"confirm current pricing)")
    print("=" * 68)

    # 3) Existing cache (resumable).
    existing = _load_existing_cache()
    id_to_row = {r.eval_id: r for r in rows}

    # Compose the full record set: every row gets a row in the cache (fired or
    # not), so the backend can look up any query. Preserve any already-generated
    # rewritten_query from a previous run.
    records: list[dict[str, str]] = []
    pending_ids: list[str] = []
    for r in rows:
        mech = firing.get(r.eval_id, "")
        prev = existing.get(r.eval_id, {})
        rewritten = prev.get("rewritten_query", "") if prev else ""
        records.append({
            "eval_id": r.eval_id,
            "source": r.source,
            "fired": "true" if mech else "false",
            "mechanism": mech,
            "original_query": r.question_text,
            "rewritten_query": rewritten,
        })
        if mech and not rewritten:
            pending_ids.append(r.eval_id)

    have_key = _have_anthropic()
    if args.dry_run or not have_key:
        _write_cache(records)
        if not have_key and not args.dry_run:
            print("\nNo ANTHROPIC_API_KEY / anthropic SDK in this environment.")
            print("Wrote FIRING DECISIONS ONLY (rewritten_query empty) to:")
        else:
            print("\n[dry-run] Wrote firing decisions only (no LLM calls) to:")
        print(f"  {CACHE_PATH}")
        print(f"\n  Rows still pending an LLM rewrite: {len(pending_ids)}")
        print("\n  OPERATOR ONE-LINER to populate the cache (bounded + cost-printed):")
        print("  ----------------------------------------------------------------")
        print(f"  cd {REPO} && \\")
        print("    ANTHROPIC_API_KEY=sk-... \\")
        print(f"    python eval/build_rewrite_cache.py --max-rewrites {args.max_rewrites}")
        print("  ----------------------------------------------------------------")
        print("  Then score the production-representative backend:")
        print("    python eval/run_rewrite_parity.py score  local-hybrid-rewrite")
        print("    python eval/run_rewrite_parity.py report local-hybrid-rewrite")
        print("    python eval/run_rewrite_parity.py report local-hybrid-rewrite --subset")
        return 0

    # 4) Generate rewrites for pending fired rows (bounded by --max-rewrites),
    #    reusing the EXACT production path (gate + Haiku caller + output cleaner).
    os.environ["QUERY_REWRITE_ENABLED"] = "1"
    os.environ["QUERY_REWRITE_FALLBACK_ENABLED"] = "1"
    qr.set_rewrite_llm_caller(qr._default_rewrite_llm_caller)

    id_to_rec = {rec["eval_id"]: rec for rec in records}
    made = 0
    for eid in pending_ids:
        if made >= args.max_rewrites:
            print(f"  --max-rewrites cap reached ({args.max_rewrites}); stopping.")
            break
        row = id_to_row[eid]
        mech = firing[eid]
        if mech == "iter1":
            rewritten = qr.maybe_rewrite(row.question_text, QueryClass.CONCEPT)
        else:
            rewritten = qr.maybe_rewrite_fallback(row.question_text, QueryClass.CONCEPT)
        id_to_rec[eid]["rewritten_query"] = (
            rewritten if rewritten != row.question_text else ""
        )
        made += 1
        if made % 25 == 0:
            print(f"  ... {made}/{min(len(pending_ids), args.max_rewrites)} rewrites")
            _write_cache(list(id_to_rec.values()))  # periodic flush (resumable)

    _write_cache(list(id_to_rec.values()))
    actual_cost = _est_cost_usd(made)
    print(f"\nGenerated {made} rewrites (est actual spend ~${actual_cost:.4f}).")
    print(f"Cache written: {CACHE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
