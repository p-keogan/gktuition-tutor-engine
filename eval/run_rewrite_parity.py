#!/usr/bin/env python3
"""Score the ``local-hybrid-rewrite`` backend through AGENT_28's unchanged parity
harness — Snowflake-exit Phase-0 **v3** (AGENT_32).

This is the production-representative gate: AGENT_31's ``local-hybrid`` retriever
wrapped with the live query-rewrite layer (cached offline by
``eval/build_rewrite_cache.py``). It reuses AGENT_31's hybrid checkpoint as the
base and composes the rewrite on top, so scoring is offline, free, and
reproducible — and registers the backend with the harness so the gate math is
AGENT_28's, unchanged.

Phases
------
* ``score``  — (live; needs fastembed + arctic index + a populated cache)
  re-retrieve the fired rows with their cached rewritten query into
  ``local-hybrid-rewrite.jsonl``. Bounded to the ≤ few-hundred firing rows;
  resumable.
* ``report`` — compose base ⊕ rewrite checkpoints and score through the gate.
* ``recall`` — recall@1/5/20 overall + per-source on the composed hits.
* ``bound``  — perfect-rewrite UPPER BOUND on P@1 (decisive, key-independent):
  the most P@1 could possibly reach if every fired-and-currently-wrong row
  flipped to rank 1. Needs only the base checkpoint + cache firing decisions.

Compose rule (mirrors ``local_retrieval.rewrite_backend``)
----------------------------------------------------------
Per row, keyed off the cached firing decision:
* not fired / no rewrite        → base (original-query) hybrid hits;
* ``iter1`` + rewrite present   → rewritten-query hybrid hits;
* ``fallback``                  → if dense (arctic) top-1 cosine ≥ 0.30 → base;
  else the better-scoring of {base, rewritten-query hits}.

Usage::

    python eval/run_rewrite_parity.py bound   local-hybrid-rewrite
    python eval/run_rewrite_parity.py report  local-hybrid-rewrite
    python eval/run_rewrite_parity.py report  local-hybrid-rewrite --subset
    python eval/run_rewrite_parity.py recall  local-hybrid-rewrite
    python eval/run_rewrite_parity.py score   local-hybrid-rewrite   # live, operator
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for p in (str(REPO), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util  # noqa: E402

import parity_harness as ph  # noqa: E402
import run_hybrid_parity as rhp  # noqa: E402  (reuse ckpt I/O + recall math)


def _load_rewrite_backend():
    """Load ``local_retrieval/rewrite_backend.py`` by file path.

    The module is pure-stdlib, but importing it via the ``local_retrieval``
    package would trigger that package's ``__init__`` (which eagerly imports the
    lancedb/fastembed serving stack). Loading the file directly keeps the
    offline scoring path dependency-free.
    """
    path = REPO / "local_retrieval" / "rewrite_backend.py"
    spec = importlib.util.spec_from_file_location("rewrite_backend", path)
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve sys.modules[cls.__module__].
    sys.modules.setdefault("rewrite_backend", mod)
    spec.loader.exec_module(mod)
    return mod


_rb = _load_rewrite_backend()
load_rewrite_cache = _rb.load_rewrite_cache
make_rewrite_backend = _rb.make_rewrite_backend

BACKEND = "local-hybrid-rewrite"
BASE_BACKEND = "local-hybrid"
ARCTIC_BACKEND = "local-arctic-cosine"
CACHE_PATH = HERE / "rewrite_cache.csv"
STORE_K = rhp.STORE_K
BUDGET_S = rhp.BUDGET_S


def _arctic_top1() -> dict[str, float]:
    ckpt = rhp._load_ckpt(ARCTIC_BACKEND)
    return {eid: (hits[0][1] if hits else 0.0) for eid, hits in ckpt.items()}


def _composed_hits_by_eval_id(
    rows: list[ph.EvalInput],
) -> dict[str, list[tuple[str, float]]]:
    """Compose base ⊕ rewrite checkpoints per the backend's substitution rule."""
    base = rhp._load_ckpt(BASE_BACKEND)
    rw = rhp._load_ckpt(BACKEND)  # fired-row re-retrievals (operator-generated)
    arctic = _arctic_top1()
    cache = load_rewrite_cache(CACHE_PATH)
    out: dict[str, list[tuple[str, float]]] = {}
    for r in rows:
        eid = r.eval_id
        base_hits = base.get(eid, [])
        entry = cache.get(r.question_text)
        if entry is None or not entry.fired or not entry.rewritten_query:
            out[eid] = base_hits
            continue
        rw_hits = rw.get(eid, [])
        if not rw_hits:
            # Rewrite decided but not yet re-retrieved (no live score run) → base.
            out[eid] = base_hits
            continue
        if entry.mechanism == "iter1":
            out[eid] = rw_hits
            continue
        # fallback: only substitute when genuinely sub-floor on the dense signal.
        if arctic.get(eid, 0.0) >= ph.RETRIEVAL_FLOOR:
            out[eid] = base_hits
            continue
        base_top = base_hits[0][1] if base_hits else 0.0
        rw_top = rw_hits[0][1] if rw_hits else 0.0
        out[eid] = rw_hits if rw_top >= base_top else base_hits
    return out


def _make_replay(rows: list[ph.EvalInput], composed):
    id_to_q = {r.eval_id: r.question_text for r in rows}
    q_to_hits: dict[str, list[tuple[str, float]]] = {}
    covered: set[str] = set()
    for eid, hits in composed.items():
        q = id_to_q.get(eid)
        if q is None:
            continue
        q_to_hits[q] = hits
        covered.add(eid)

    def retrieve(query: str, k: int = ph.TOP_K) -> list[tuple[str, float]]:
        return q_to_hits.get(query, [])[:k]

    retrieve.restrict_to_eval_ids = covered  # type: ignore[attr-defined]
    return retrieve


def phase_report(subset: bool, baseline_strands: Path | None) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    composed = _composed_hits_by_eval_id(all_rows)
    fn = _make_replay(all_rows, composed)
    restrict = fn.restrict_to_eval_ids
    missing = [r.eval_id for r in rows if r.eval_id not in restrict]
    if missing:
        print(f"WARNING: {len(missing)}/{len(rows)} rows have no base checkpoint — "
              f"run `python eval/run_hybrid_parity.py score local-hybrid`.",
              file=sys.stderr)
    rows = [r for r in rows if r.eval_id in restrict]
    bs = ph.load_baseline_strands(baseline_strands) if baseline_strands else None
    report = ph.score_backend(fn, rows, backend_name=BACKEND, baseline_strands=bs)
    print(ph.render_console(report, subset=subset, n_rows=len(rows)))
    stamp = ph.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "subset" if subset else "full"
    out = HERE / f"parity_report_{BACKEND}_{suffix}_{stamp}.json"
    payload = ph.build_json_report(report, subset=subset)
    payload["scope"] = suffix
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nJSON report: {out}")
    return 0 if report.gate_pass else 1


def phase_recall(subset: bool) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    part_refs = ph._build_part_id_to_referenced_slugs(all_rows)
    composed = _composed_hits_by_eval_id(all_rows)
    rows = [r for r in rows if r.eval_id in composed]
    if not rows:
        print("No base checkpoint; run `score local-hybrid` first.", file=sys.stderr)
        return 2
    ks = (1, 5, 20)
    overall = {k: 0 for k in ks}
    by_source: dict[str, dict[int, int]] = {}
    n_by_source: dict[str, int] = {}
    for r in rows:
        ranked = [s for s, _ in composed[r.eval_id]][:STORE_K]
        rank = rhp._rank_for_row(r, ranked, part_refs)
        by_source.setdefault(r.source, {k: 0 for k in ks})
        n_by_source[r.source] = n_by_source.get(r.source, 0) + 1
        for k in ks:
            hit = 1 if (rank is not None and rank <= k) else 0
            overall[k] += hit
            by_source[r.source][k] += hit
    n = len(rows)
    scope = "subset" if subset else "full"
    print("=" * 64)
    print(f"RECALL@K — backend: {BACKEND}  ·  {scope}  ·  n={n}")
    print("=" * 64)
    print("OVERALL   " + "  ".join(f"recall@{k}={overall[k] / n:.3f}" for k in ks))
    print("\nBY SOURCE")
    src_payload = {}
    for src in sorted(by_source):
        ns = n_by_source[src]
        vals = {k: by_source[src][k] / ns for k in ks}
        src_payload[src] = {**{f"recall@{k}": vals[k] for k in ks}, "n": ns}
        print(f"  {src:<22} n={ns:>4}  " + "  ".join(
            f"r@{k}={vals[k]:.3f}" for k in ks))
    payload = {
        "backend": BACKEND, "scope": scope, "n": n,
        "overall": {f"recall@{k}": overall[k] / n for k in ks},
        "by_source": src_payload,
        "timestamp": ph.datetime.now().isoformat(timespec="seconds"),
    }
    stamp = ph.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HERE / f"recall_report_{BACKEND}_{scope}_{stamp}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nJSON report: {out}")
    return 0


def phase_bound(subset: bool) -> int:
    """Perfect-rewrite UPPER BOUND on P@1 — decisive and key-independent.

    The most P@1 could reach if EVERY fired-and-currently-wrong row flipped to
    rank 1. Uses only the base hybrid checkpoint + cache firing decisions, so it
    needs no LLM call and bounds the production-representative number from above.
    """
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    subset_ids = set(ph._derive_subset_ids(all_rows))
    rows = [r for r in all_rows if r.eval_id in subset_ids] if subset else all_rows
    part_refs = ph._build_part_id_to_referenced_slugs(all_rows)
    base = rhp._load_ckpt(BASE_BACKEND)
    cache = load_rewrite_cache(CACHE_PATH)
    rows = [r for r in rows if r.eval_id in base]
    n = len(rows)
    correct = fired_n = fired_wrong = fired_wrong_cross = 0
    for r in rows:
        ranked = [s for s, _ in base[r.eval_id]][:ph.TOP_K]
        rank = rhp._rank_for_row(r, ranked, part_refs)
        ok = rank == 1
        correct += 1 if ok else 0
        e = cache.get(r.question_text)
        if e and e.fired:
            fired_n += 1
            if not ok:
                fired_wrong += 1
                if r.source == "solution_cross_ref":
                    fired_wrong_cross += 1
    cur = correct / n if n else 0.0
    ub = (correct + fired_wrong) / n if n else 0.0
    scope = "subset" if subset else "full"
    print("=" * 64)
    print(f"PERFECT-REWRITE UPPER BOUND — {scope}  ·  n={n}")
    print("=" * 64)
    print(f"  current hybrid P@1            : {cur:.3f} ({correct}/{n})")
    print(f"  rows firing a rewrite         : {fired_n}")
    print(f"  ... currently wrong (fixable) : {fired_wrong}  "
          f"(of which cross_ref: {fired_wrong_cross})")
    print(f"  PERFECT-rewrite UPPER BOUND   : {ub:.3f}")
    print(f"  locked gate                   : {ph.LOCKED_BASELINE_P_AT_1:.3f}")
    verdict = ("CLEARS" if ub >= ph.LOCKED_BASELINE_P_AT_1
               else f"FAILS by {ph.LOCKED_BASELINE_P_AT_1 - ub:.3f}")
    print(f"  upper bound vs gate           : {verdict}")
    return 0


def phase_score(subset: bool) -> int:
    """Live: re-retrieve fired rows with their cached rewritten query.

    Only the firing rows are (re)retrieved, so this is cheap; resumable via the
    checkpoint. Requires fastembed + the arctic index + a populated cache.
    """
    from local_retrieval.hybrid import retrieve_hybrid
    arctic_idx = os.environ.get("ARCTIC_INDEX_DIR", str(REPO / "local_index_arctic"))
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    cache = load_rewrite_cache(CACHE_PATH)
    done = set(rhp._load_ckpt(BACKEND))
    pending = [
        r for r in rows
        if r.eval_id not in done
        and (e := cache.get(r.question_text)) is not None
        and e.fired and e.rewritten_query
    ]
    path = rhp._ckpt_path(BACKEND)
    t0 = time.perf_counter()
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in pending:
            if (time.perf_counter() - t0) > BUDGET_S:
                break
            rq = cache[r.question_text].rewritten_query
            hits = retrieve_hybrid(rq, STORE_K, index_dir=arctic_idx)
            fh.write(json.dumps({"eval_id": r.eval_id,
                                 "hits": [[s, sc] for s, sc in hits]}) + "\n")
            written += 1
        fh.flush()
    total = len(rhp._load_ckpt(BACKEND))
    n_fire = sum(1 for r in rows
                 if (e := cache.get(r.question_text)) and e.fired and e.rewritten_query)
    print(f"{BACKEND}: +{written} fired-row re-retrievals; checkpoint {total}/{n_fire}"
          f"{' (DONE)' if total >= n_fire else ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="phase", required=True)
    for name in ("score", "report", "recall", "bound"):
        p = sub.add_parser(name)
        p.add_argument("backend", choices=[BACKEND])
        p.add_argument("--subset", action="store_true")
        if name == "report":
            p.add_argument("--baseline-strands", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.phase == "score":
        return phase_score(args.subset)
    if args.phase == "recall":
        return phase_recall(args.subset)
    if args.phase == "bound":
        return phase_bound(args.subset)
    return phase_report(args.subset, args.baseline_strands)


# Register with AGENT_28's harness so `--backend local-hybrid-rewrite` is
# first-class (live end-to-end). The checkpoint-compose phases above exist
# because a full live hybrid pass is too slow for one sandbox process.
def _register() -> None:
    def factory(args, rows, _n=BACKEND):  # noqa: ANN001, ARG001
        from local_retrieval.core import retrieve as retrieve_dense
        from local_retrieval.hybrid import retrieve_hybrid
        arctic_idx = os.environ.get("ARCTIC_INDEX_DIR", str(REPO / "local_index_arctic"))
        cache = load_rewrite_cache(CACHE_PATH)

        def hybrid_fn(q, k):
            return retrieve_hybrid(q, k, index_dir=arctic_idx)

        def dense_top1_fn(q):
            hits = retrieve_dense(q, 1, index_dir=arctic_idx,
                                  model_name=rhp.ARCTIC_MODEL)
            return hits[0][1] if hits else 0.0

        return make_rewrite_backend(cache, hybrid_fn=hybrid_fn,
                                    dense_top1_fn=dense_top1_fn)
    ph.register_backend(BACKEND, factory)


_register()

if __name__ == "__main__":
    sys.exit(main())
