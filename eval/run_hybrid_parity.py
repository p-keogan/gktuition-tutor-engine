#!/usr/bin/env python3
"""Run the v2 (hybrid BM25 + arctic-embed) backends through AGENT_28's parity
harness, as an ablation — Snowflake-exit Phase-0 v2 (AGENT_31).

v1 (AGENT_30) NO-GO'd: vector-only ``bge-small`` ceilinged at recall@20 ≈
0.78–0.83, the collapse concentrated in cryptic ``solution_cross_ref`` rows
(0.752). This runner measures the levers v1 was missing, each isolable:

* ``local-bge-cosine``    — v1's model, vector-only (the baseline anchor)
* ``local-arctic-cosine`` — the bigger/asymmetric dense model alone
* ``local-bm25``          — the lexical lever alone
* ``local-hybrid``        — arctic ⊕ BM25 fused with RRF (the candidate)

It registers all four with ``parity_harness.register_backend`` (so the gate
math is AGENT_28's, unchanged) and adds a ``recall`` phase computing
recall@1/5/20 overall and per-source (phrasings vs cross_ref) — the exact
breakdown v1's §4 ceiling analysis used, so the v1→v2 delta is direct.

Why checkpointed: a full-set arctic / hybrid pass embeds thousands of queries
on CPU — too slow for one process / sandbox wall-cap. ``score`` computes top-20
per row and appends to a resumable JSONL checkpoint (time-bounded, skips done
rows); ``report`` / ``recall`` replay the checkpoint. The replay returns the
REAL recorded scores, so floor / mean-top-1 reflect the true distribution.

Index locations are taken from env (defaults match the AGENT_31 build):
``ARCTIC_INDEX_DIR`` (arctic 768-dim + BM25), ``BGE_INDEX_DIR`` (bge 384-dim).

Usage (offline)::

    python eval/run_hybrid_parity.py score local-hybrid          # full, resumable
    python eval/run_hybrid_parity.py score local-arctic-cosine --subset
    python eval/run_hybrid_parity.py report local-hybrid         # parity gate
    python eval/run_hybrid_parity.py recall local-hybrid         # recall@K ablation
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import parity_harness as ph  # noqa: E402

ARCTIC_MODEL = "snowflake/snowflake-arctic-embed-m"
BGE_MODEL = "BAAI/bge-small-en-v1.5"
ARCTIC_INDEX = os.environ.get("ARCTIC_INDEX_DIR", str(REPO / "local_index_arctic"))
BGE_INDEX = os.environ.get("BGE_INDEX_DIR", str(REPO / "local_index"))

# How many candidates we checkpoint per row — wide enough for recall@20.
STORE_K = 20
# Per-call wall budget (the sandbox kills at ~45s; leave headroom to flush).
BUDGET_S = 36.0

BACKENDS = ("local-bge-cosine", "local-arctic-cosine", "local-bm25", "local-hybrid")


def _backend_fn(backend: str):
    """Return a ``(query, top_k) -> [(slug, score)]`` callable for ``backend``."""
    if backend == "local-bge-cosine":
        from local_retrieval.core import retrieve
        return lambda q, k: retrieve(q, k, index_dir=BGE_INDEX, model_name=BGE_MODEL)
    if backend == "local-arctic-cosine":
        from local_retrieval.core import retrieve
        return lambda q, k: retrieve(q, k, index_dir=ARCTIC_INDEX, model_name=ARCTIC_MODEL)
    if backend == "local-bm25":
        from local_retrieval.bm25_index import retrieve_bm25
        return lambda q, k: retrieve_bm25(q, k, index_dir=ARCTIC_INDEX)
    if backend == "local-hybrid":
        from local_retrieval.hybrid import retrieve_hybrid
        return lambda q, k: retrieve_hybrid(
            q, k, index_dir=ARCTIC_INDEX, model_name=ARCTIC_MODEL
        )
    raise SystemExit(f"unknown backend {backend!r}")


# ── checkpoint I/O (native FS; the repo mount can't unlink lance manifests) ──
def _ckpt_dir() -> Path:
    base = Path(os.environ.get("LOCAL_PARITY_CKPT_DIR", "/tmp/hybrid_parity_ckpt"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _ckpt_path(backend: str) -> Path:
    return _ckpt_dir() / f"{backend}.jsonl"


def _load_ckpt(backend: str) -> dict[str, list[tuple[str, float]]]:
    path = _ckpt_path(backend)
    out: dict[str, list[tuple[str, float]]] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        out[rec["eval_id"]] = [(s, float(sc)) for s, sc in rec["hits"]]
    return out


def phase_score(backend: str, subset: bool) -> None:
    """Compute top-STORE_K for not-yet-done rows, time-bounded + resumable."""
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    done = set(_load_ckpt(backend))
    pending = [r for r in rows if r.eval_id not in done]
    fn = _backend_fn(backend)
    path = _ckpt_path(backend)
    t0 = time.perf_counter()
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in pending:
            if (time.perf_counter() - t0) > BUDGET_S:
                break
            hits = fn(r.question_text, STORE_K)
            fh.write(json.dumps({"eval_id": r.eval_id,
                                 "hits": [[s, sc] for s, sc in hits]}) + "\n")
            written += 1
        fh.flush()
    total = len(_load_ckpt(backend))
    scope = "subset" if subset else "full"
    print(f"{backend} [{scope}]: +{written} rows; checkpoint {total}/{len(rows)}"
          f"{' (DONE)' if total >= len(rows) else ''}")


def _make_replay(backend: str, golden_rows, top_k: int = ph.TOP_K):
    ckpt = _load_ckpt(backend)
    id_to_q = {r.eval_id: r.question_text for r in golden_rows}
    q_to_hits: dict[str, list[tuple[str, float]]] = {}
    covered: set[str] = set()
    for eid, hits in ckpt.items():
        q = id_to_q.get(eid)
        if q is None:
            continue
        q_to_hits[q] = hits
        covered.add(eid)

    def retrieve(query: str, k: int = top_k) -> list[tuple[str, float]]:
        return q_to_hits.get(query, [])[:k]

    retrieve.restrict_to_eval_ids = covered  # type: ignore[attr-defined]
    return retrieve


def phase_report(backend: str, subset: bool, baseline_strands: Path | None) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    fn = _make_replay(backend, all_rows)
    restrict = getattr(fn, "restrict_to_eval_ids", None)
    if restrict is not None:
        missing = [r.eval_id for r in rows if r.eval_id not in restrict]
        if missing:
            print(f"WARNING: {len(missing)}/{len(rows)} rows not yet scored — "
                  f"run more `score {backend}` slices.", file=sys.stderr)
        rows = [r for r in rows if r.eval_id in restrict]
    bs = ph.load_baseline_strands(baseline_strands) if baseline_strands else None
    report = ph.score_backend(fn, rows, backend_name=backend, baseline_strands=bs)
    print(ph.render_console(report, subset=subset, n_rows=len(rows)))
    stamp = ph.datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "subset" if subset else "full"
    out = HERE / f"parity_report_{backend}_{suffix}_{stamp}.json"
    payload = ph.build_json_report(report, subset=subset)
    payload["scope"] = suffix
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nJSON report: {out}")
    return 0 if report.gate_pass else 1


# ── recall@K ablation (the v2 headline; mirrors v1 §4 ceiling math) ──────────
def _rank_for_row(row, ranked: list[str], part_id_to_refs) -> int | None:
    """1-indexed rank of the correct answer in ``ranked`` (top-STORE_K).

    Cross-ref rows: best rank over the exam-part's full referenced-tutorial set
    (identical rule to the harness's ``score_row``); everything else: the single
    expected_slug.
    """
    valid: set[str] | None = None
    if row.source == "solution_cross_ref":
        pid = row.source_metadata.get("part_id")
        if pid:
            valid = part_id_to_refs.get(pid)
    if valid:
        return ph._best_rank_over_slugs(valid, ranked)
    return ph._rank_in_slugs(row.expected_slug, ranked)


def phase_recall(backend: str, subset: bool) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    part_id_to_refs = ph._build_part_id_to_referenced_slugs(all_rows)
    ckpt = _load_ckpt(backend)
    id_to_hits = ckpt
    rows = [r for r in rows if r.eval_id in id_to_hits]
    if not rows:
        print(f"No checkpoint rows for {backend}; run `score` first.", file=sys.stderr)
        return 2

    ks = (1, 5, 20)

    def _acc():
        return {k: 0 for k in ks}

    overall = _acc()
    by_source: dict[str, dict[int, int]] = {}
    n_by_source: dict[str, int] = {}
    for r in rows:
        ranked = [s for s, _ in id_to_hits[r.eval_id]][:STORE_K]
        rank = _rank_for_row(r, ranked, part_id_to_refs)
        by_source.setdefault(r.source, _acc())
        n_by_source[r.source] = n_by_source.get(r.source, 0) + 1
        for k in ks:
            hit = 1 if (rank is not None and rank <= k) else 0
            overall[k] += hit
            by_source[r.source][k] += hit

    n = len(rows)
    scope = "subset" if subset else "full"
    print("=" * 64)
    print(f"RECALL@K — backend: {backend}  ·  {scope}  ·  n={n}")
    print("=" * 64)
    print("OVERALL   " + "  ".join(f"recall@{k}={overall[k]/n:.3f}" for k in ks))
    print("\nBY SOURCE")
    src_payload = {}
    for src in sorted(by_source):
        ns = n_by_source[src]
        vals = {k: by_source[src][k] / ns for k in ks}
        src_payload[src] = {**{f"recall@{k}": vals[k] for k in ks}, "n": ns}
        print(f"  {src:<22} n={ns:>4}  " + "  ".join(
            f"r@{k}={vals[k]:.3f}" for k in ks))
    payload = {
        "backend": backend, "scope": scope, "n": n,
        "overall": {f"recall@{k}": overall[k] / n for k in ks},
        "by_source": src_payload,
        "timestamp": ph.datetime.now().isoformat(timespec="seconds"),
    }
    stamp = ph.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = HERE / f"recall_report_{backend}_{scope}_{stamp}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nJSON report: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="phase", required=True)
    for name in ("score", "report", "recall"):
        p = sub.add_parser(name)
        p.add_argument("backend", choices=BACKENDS)
        p.add_argument("--subset", action="store_true")
        if name == "report":
            p.add_argument("--baseline-strands", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.phase == "score":
        phase_score(args.backend, args.subset)
        return 0
    if args.phase == "recall":
        return phase_recall(args.backend, args.subset)
    return phase_report(args.backend, args.subset, args.baseline_strands)


# Register the four backends with AGENT_28's harness so they are first-class
# (`--backend local-hybrid` runs live end-to-end). The checkpointed score/report
# phases above exist only because a full-set arctic/hybrid pass is too slow for
# one process; they score through the identical harness math.
def _register() -> None:
    for name in BACKENDS:
        def factory(args, rows, _n=name):  # noqa: ANN001, ARG001
            fn = _backend_fn(_n)
            return lambda q, k=ph.TOP_K: fn(q, k)
        ph.register_backend(name, factory)


_register()

if __name__ == "__main__":
    sys.exit(main())
