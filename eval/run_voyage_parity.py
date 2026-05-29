#!/usr/bin/env python3
"""Run the v4 hosted-librarian backends (Voyage embeddings + BM25 hybrid +
hosted reranker) through AGENT_28's parity harness — Snowflake-exit Phase-0 v4
(AGENT_33), the decider.

v1→v3 proved a local-CPU stack can't match Cortex (P@1 0.41 → 0.50 → ≤0.53 vs
the locked 0.911 gate) and traced the failure to embedding recall on terse
``solution_cross_ref`` exam rows (recall@20 stuck ~0.78, needs ~0.92). This
runner tests the one untested lever — a strong *hosted* embedder + hosted
reranker — and produces the final Phase-0 verdict.

Backends (each isolates a lever, all over the SAME chunks as v1–v3):

* ``voyage-cosine``               — Voyage dense, vector-only (embedding lever)
* ``voyage-hybrid``               — Voyage dense ⊕ BM25, RRF (hosted analogue of v2)
* ``voyage-hybrid-rerank``        — + Voyage rerank-2.5 (the candidate; mirrors Cortex)
* ``voyage-hybrid-rerank-cohere`` — optional, Cohere rerank-v3.5 (secondary, opt-in)

Bounded, cached, key-gated spend (dispatch rule 4)
--------------------------------------------------
Voyage is the default for BOTH embeddings and reranking; its 200M-token free
tier covers this corpus + golden set at ~$0. Every embedding and rerank result
is cached to disk (``eval/cache/``), so after a single bounded ``build-cache``
pass ALL scoring is offline / free / reproducible. ``estimate`` prints a
token/cost estimate and respects ``--max-calls`` BEFORE any spend. With no
``VOYAGE_API_KEY`` present, ``build-cache`` refuses to run and prints the bounded
operator one-liner; nothing is ever fabricated.

Phases (offline unless noted)::

    python eval/run_voyage_parity.py estimate                         # cost preview, no spend
    python eval/run_voyage_parity.py build-cache --max-calls 8000     # SPENDS (needs key); fills caches
    python eval/run_voyage_parity.py score  voyage-hybrid-rerank      # cache-served, resumable
    python eval/run_voyage_parity.py report voyage-hybrid-rerank      # parity gate
    python eval/run_voyage_parity.py recall voyage-hybrid-rerank      # recall@K ablation

Index location: ``VOYAGE_INDEX_DIR`` (Voyage 1024-dim + BM25); built by
``scripts/build_local_index.py --model voyage-3.5 --with-bm25 --out local_index_voyage``
(the build embeds via the cached hosted backend).
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

VOYAGE_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5")
VOYAGE_INDEX = os.environ.get("VOYAGE_INDEX_DIR", str(REPO / "local_index_voyage"))

STORE_K = 20          # candidates checkpointed per row (for recall@20)
BUDGET_S = 36.0       # per-call wall budget (sandbox kills ~45s)

BACKENDS = (
    "voyage-cosine",
    "voyage-hybrid",
    "voyage-hybrid-rerank",
    "voyage-hybrid-rerank-cohere",
)

# Committed, offline-replayable result checkpoints (NOT /tmp — these are part of
# the reproducible deliverable, unlike the v2 runner's scratch checkpoints).
def _ckpt_dir() -> Path:
    base = Path(os.environ.get("VOYAGE_CKPT_DIR", str(HERE / "cache" / "results")))
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


# ── backend callables (eval_id-aware for the rerank cache key) ───────────────
def _vendor_for(backend: str) -> str:
    return "cohere" if backend.endswith("-cohere") else "voyage"


def _backend_fn(backend: str, *, allow_api: bool):
    """Return ``(eval_id, query, top_k) -> [(slug, score)]`` for ``backend``."""
    from local_retrieval import voyage_hybrid as vh

    if backend == "voyage-cosine":
        return lambda eid, q, k: vh.retrieve_voyage_cosine(
            q, k, index_dir=VOYAGE_INDEX, model_name=VOYAGE_MODEL
        )
    if backend == "voyage-hybrid":
        return lambda eid, q, k: vh.retrieve_voyage_hybrid(
            q, k, index_dir=VOYAGE_INDEX, model_name=VOYAGE_MODEL
        )
    if backend in ("voyage-hybrid-rerank", "voyage-hybrid-rerank-cohere"):
        vendor = _vendor_for(backend)
        return lambda eid, q, k: vh.retrieve_voyage_hybrid_rerank(
            q, k, eval_id=eid, index_dir=VOYAGE_INDEX, model_name=VOYAGE_MODEL,
            rerank_vendor=vendor, allow_api=allow_api,
        )
    raise SystemExit(f"unknown backend {backend!r}")


# ── estimate (no spend) ──────────────────────────────────────────────────────
def phase_estimate(max_calls: int | None) -> int:
    from local_retrieval.voyage_embed import estimate_cost_usd, estimate_tokens

    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=False)
    queries = [r.question_text for r in rows]
    q_tokens = estimate_tokens(queries)

    # Corpus side: estimate from the index if built, else from the corpus walk.
    corpus_tokens = 0
    n_chunks = 0
    try:
        from local_retrieval.store import open_tutor_table  # noqa: PLC0415

        tbl = open_tutor_table(VOYAGE_INDEX)
        recs = tbl.to_lance().to_table(
            columns=["title_plus_phrasings", "body"]
        ).to_pylist()
        texts = [(r.get("title_plus_phrasings") or "") for r in recs] + \
                [(r.get("body") or "")[:2000] for r in recs]
        corpus_tokens = estimate_tokens(texts)
        n_chunks = len(recs)
    except Exception as exc:  # noqa: BLE001
        print(f"(corpus token estimate unavailable — index not built yet: {exc})")

    total = q_tokens + corpus_tokens
    print("=" * 64)
    print("VOYAGE SPEND ESTIMATE (pre-flight, no API calls made)")
    print("=" * 64)
    print(f"  embedding model      : {VOYAGE_MODEL}")
    print(f"  golden queries       : {len(queries)}  (~{q_tokens:,} tok)")
    print(f"  corpus chunks x2 flds: {n_chunks}  (~{corpus_tokens:,} tok)")
    print(f"  TOTAL embed tokens   : ~{total:,}")
    print(f"  list cost @ $0.06/1M : ${estimate_cost_usd(total):.4f}  "
          f"(Voyage free tier = 200M tok → realistic spend $0)")
    print(f"  rerank calls (1/query, build-cache): up to {len(queries)}")
    if max_calls is not None:
        print(f"  --max-calls cap      : {max_calls}")
    print("=" * 64)
    return 0


# ── build-cache (SPENDS; needs key) ──────────────────────────────────────────
def phase_build_cache(backend: str, subset: bool, max_calls: int | None) -> int:
    if not (os.environ.get("VOYAGE_API_KEY") or os.environ.get("VOYAGEAI_API_KEY")):
        print(
            "No VOYAGE_API_KEY present — refusing to fabricate (dispatch 4d).\n"
            "Operator one-liner to populate caches (bounded), then scoring is "
            "offline + free:\n\n"
            "  export VOYAGE_API_KEY=...\n"
            "  python scripts/build_local_index.py --model voyage-3.5 --with-bm25 "
            "--out local_index_voyage\n"
            "  VOYAGE_INDEX_DIR=local_index_voyage python eval/run_voyage_parity.py "
            f"build-cache {backend} --max-calls 8000\n",
            file=sys.stderr,
        )
        return 2
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    fn = _backend_fn(backend, allow_api=True)
    done = set(_load_ckpt(backend))
    pending = [r for r in rows if r.eval_id not in done]
    path = _ckpt_path(backend)
    t0 = time.perf_counter()
    written = 0
    calls = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in pending:
            if (time.perf_counter() - t0) > BUDGET_S:
                break
            if max_calls is not None and calls >= max_calls:
                break
            hits = fn(r.eval_id, r.question_text, STORE_K)
            fh.write(json.dumps({"eval_id": r.eval_id,
                                 "hits": [[s, sc] for s, sc in hits]}) + "\n")
            written += 1
            calls += 1
        fh.flush()
    # Persist the embedding + rerank caches accumulated this pass.
    _save_caches(backend)
    total = len(_load_ckpt(backend))
    print(f"{backend}: +{written} rows ({calls} call-batches); "
          f"checkpoint {total}/{len(rows)}"
          f"{' (DONE)' if total >= len(rows) else ''}")
    return 0


def _save_caches(backend: str) -> None:
    """Flush the on-disk Voyage embed + hosted rerank caches to disk."""
    try:
        from local_retrieval.voyage_embed import VoyageEmbedCache
        VoyageEmbedCache(VOYAGE_MODEL).load().save()
    except Exception:  # noqa: BLE001 - best effort flush
        pass
    try:
        from local_retrieval.hosted_rerank import RerankCache
        RerankCache().save()
    except Exception:  # noqa: BLE001
        pass


# ── score (cache-served, offline, resumable) ─────────────────────────────────
def phase_score(backend: str, subset: bool) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    fn = _backend_fn(backend, allow_api=False)
    done = set(_load_ckpt(backend))
    pending = [r for r in rows if r.eval_id not in done]
    path = _ckpt_path(backend)
    t0 = time.perf_counter()
    written = 0
    misses = 0
    with path.open("a", encoding="utf-8") as fh:
        for r in pending:
            if (time.perf_counter() - t0) > BUDGET_S:
                break
            try:
                hits = fn(r.eval_id, r.question_text, STORE_K)
            except KeyError:
                misses += 1
                continue
            fh.write(json.dumps({"eval_id": r.eval_id,
                                 "hits": [[s, sc] for s, sc in hits]}) + "\n")
            written += 1
        fh.flush()
    total = len(_load_ckpt(backend))
    scope = "subset" if subset else "full"
    print(f"{backend} [{scope}]: +{written} rows; checkpoint {total}/{len(rows)}"
          f"{' (DONE)' if total >= len(rows) else ''}")
    if misses:
        print(f"  {misses} rows skipped (cache MISS) — run `build-cache` with a "
              "VOYAGE_API_KEY to populate, then re-run `score`.", file=sys.stderr)
    return 0


def _make_replay(backend: str, golden_rows):
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

    def retrieve(query: str, k: int = ph.TOP_K) -> list[tuple[str, float]]:
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
                  f"run more `score {backend}` slices (after build-cache).",
                  file=sys.stderr)
        rows = [r for r in rows if r.eval_id in restrict]
    if not rows:
        print(f"No scored rows for {backend}. Populate caches first:\n"
              "  python eval/run_voyage_parity.py build-cache "
              f"{backend} --max-calls 8000   (needs VOYAGE_API_KEY)",
              file=sys.stderr)
        return 2
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


# ── recall@K ablation (mirrors run_hybrid_parity) ────────────────────────────
def _rank_for_row(row, ranked: list[str], part_id_to_refs) -> int | None:
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
    id_to_hits = _load_ckpt(backend)
    rows = [r for r in rows if r.eval_id in id_to_hits]
    if not rows:
        print(f"No checkpoint rows for {backend}; run `build-cache`+`score` first.",
              file=sys.stderr)
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

    p_est = sub.add_parser("estimate")
    p_est.add_argument("--max-calls", type=int, default=None)

    p_bc = sub.add_parser("build-cache")
    p_bc.add_argument("backend", choices=BACKENDS)
    p_bc.add_argument("--subset", action="store_true")
    p_bc.add_argument("--max-calls", type=int, default=None)

    for name in ("score", "report", "recall"):
        p = sub.add_parser(name)
        p.add_argument("backend", choices=BACKENDS)
        p.add_argument("--subset", action="store_true")
        if name == "report":
            p.add_argument("--baseline-strands", type=Path, default=None)

    args = ap.parse_args(argv)
    if args.phase == "estimate":
        return phase_estimate(args.max_calls)
    if args.phase == "build-cache":
        return phase_build_cache(args.backend, args.subset, args.max_calls)
    if args.phase == "score":
        return phase_score(args.backend, args.subset)
    if args.phase == "recall":
        return phase_recall(args.backend, args.subset)
    return phase_report(args.backend, args.subset, args.baseline_strands)


# Register the backends with AGENT_28's harness so they are first-class
# (`parity_harness.py --backend voyage-hybrid-rerank` runs live, end-to-end,
# once caches are populated). The factory closes over a query→eval_id map (built
# from the golden rows) so the rerank cache key can be derived from the harness's
# query-only contract. Cache-served (allow_api=False): the harness path never
# spends.
def _register() -> None:
    for name in BACKENDS:
        def factory(args, rows, _n=name):  # noqa: ANN001, ARG001
            q_to_eid = {r.question_text: r.eval_id for r in rows}
            fn = _backend_fn(_n, allow_api=False)

            def retrieve(q: str, k: int = ph.TOP_K):
                return fn(q_to_eid.get(q, q), q, k)

            return retrieve
        ph.register_backend(name, factory)


_register()

if __name__ == "__main__":
    sys.exit(main())
