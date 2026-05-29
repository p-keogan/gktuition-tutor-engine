#!/usr/bin/env python3
"""Run the local-retrieval backends through AGENT_28's parity harness.

Snowflake-exit Phase-0 spike (AGENT_30). Registers two backends with
``eval/parity_harness.py`` and scores them against the golden set, fully
offline:

* ``local-cosine``   — AGENT_29's raw ``local_retrieval.retrieve`` (cosine only)
* ``local-reranked`` — ``local_retrieval.rerank.retrieve_reranked`` (cosine
  candidate pool re-ranked by a local cross-encoder)

Why a checkpointed two-phase design
-----------------------------------
Retrieval — especially the cross-encoder rerank (≈20 pairs/query over 3.2k
rows) — is far too slow to finish in a single short process. So we split:

  phase ``score``  : compute each row's top-K ``(slug, score)`` once and append
                     to a JSONL checkpoint (resumable; skips done eval_ids).
  phase ``report`` : replay the checkpoint as a harness backend and run
                     ``parity_harness.score_backend`` for the *exact* same
                     metrics, gate, per-strand and per-source breakdown the
                     Cortex baseline used — subset or full.

The replay returns the REAL recorded scores (not synthetic), so
``mean_top1_score`` / ``pct_top1_above_floor`` reflect the true local
distribution — the input the floor recalibration needs.

Usage (offline; set LOCAL_INDEX_DIR to the built index)::

    python eval/run_local_parity.py score local-cosine   --start 0 --count 400
    python eval/run_local_parity.py score local-reranked --start 0 --count 120
    python eval/run_local_parity.py report local-reranked            # full
    python eval/run_local_parity.py report local-reranked --subset   # subset
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import parity_harness as ph  # noqa: E402  (local module, sys.path set above)


def _register_live_backends() -> None:
    """Expose the two local backends through AGENT_28's ``register_backend``
    hook so they are first-class harness backends (``--backend local-cosine`` /
    ``local-reranked`` run live, end-to-end). The checkpointed ``score``/
    ``report`` phases below exist only because a *full*-set live run is too slow
    to finish in one process — they score through the identical harness math.
    """
    def _cosine_factory(args, rows):  # noqa: ANN001, ARG001
        from local_retrieval import retrieve
        return lambda q, k=ph.TOP_K: retrieve(q, k)

    def _reranked_factory(args, rows):  # noqa: ANN001, ARG001
        from local_retrieval.rerank import retrieve_reranked
        return lambda q, k=ph.TOP_K: retrieve_reranked(q, k)

    ph.register_backend("local-cosine", _cosine_factory)
    ph.register_backend("local-reranked", _reranked_factory)


_register_live_backends()

# Checkpoints live on the (writable, unlink-capable) native FS, not the repo
# fuse mount — keyed dir overridable so a CI/box with a normal FS can co-locate.
CKPT_DIR = Path(__file__).resolve().parent / "_local_parity_ckpt"
CKPT_DIR_ENV = "LOCAL_PARITY_CKPT_DIR"


def _ckpt_path(backend: str) -> Path:
    import os
    base = Path(os.environ.get(CKPT_DIR_ENV, str(CKPT_DIR)))
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{backend}.jsonl"


def _load_ckpt(backend: str) -> dict[str, list[tuple[str, float]]]:
    """eval_id -> list[(slug, score)] from the JSONL checkpoint."""
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


def _backend_fn(backend: str):
    """Return the (query, top_k) -> [(slug, score)] callable for a backend."""
    if backend == "local-cosine":
        from local_retrieval import retrieve
        return lambda q, k: retrieve(q, k)
    if backend == "local-reranked":
        from local_retrieval.rerank import retrieve_reranked
        return lambda q, k: retrieve_reranked(q, k)
    raise SystemExit(f"unknown backend {backend!r}")


def _score_reranked_batch(pending, top_k, candidate_k):
    """Rerank a batch of rows with a SINGLE cross-encoder predict() call.

    Identical math to ``rerank.retrieve_reranked`` (same candidate pool, same
    model, same sigmoid calibration) but amortises the per-call cross-encoder
    overhead across the whole slice — the only way a full 3.4k-row rerank pass
    is tractable on CPU. Returns ``[(eval_id, hits)]``.
    """
    import os

    try:
        import torch
        torch.set_num_threads(max(1, os.cpu_count() or 1))
    except Exception:  # noqa: BLE001 - torch threading is a perf knob, not required
        pass

    from local_retrieval import retrieve
    from local_retrieval.rerank import (
        _get_reranker,
        _sigmoid,
        _slug_to_text,
        DEFAULT_RERANKER_MODEL,
    )

    idx = os.environ.get("LOCAL_INDEX_DIR")
    text_map = _slug_to_text(str(idx)) if idx else _slug_to_text(
        str(__import__("local_retrieval").DEFAULT_INDEX_DIR)
    )
    reranker = _get_reranker(DEFAULT_RERANKER_MODEL)

    per_row_cands = []   # list of (eval_id, [(slug, cosine), ...])
    pairs = []           # flat list of (query, text)
    for r in pending:
        cands = retrieve(r.question_text, candidate_k)
        per_row_cands.append((r.eval_id, cands))
        for slug, _cos in cands:
            pairs.append((r.question_text, text_map.get(slug, slug)))

    logits = list(reranker.predict(pairs, batch_size=64)) if pairs else []

    out = []
    cursor = 0
    for eid, cands in per_row_cands:
        n = len(cands)
        chunk = logits[cursor:cursor + n]
        cursor += n
        scored = [
            (slug, _sigmoid(float(lg))) for (slug, _cos), lg in zip(cands, chunk)
        ]
        scored.sort(key=lambda t: t[1], reverse=True)
        out.append((eid, [[s, round(sc, 6)] for s, sc in scored[:top_k]]))
    return out


def phase_score(
    backend: str, start: int, count: int, top_k: int, candidate_k: int,
    subset: bool = False,
) -> None:
    """Compute top-K for rows[start:start+count] and append to the checkpoint.

    With ``subset=True`` the candidate population is the deterministic golden
    subset (so the headline subset numbers can be completed first), and
    ``start``/``count`` slice within it.
    """
    rows = (
        ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=True)
        if subset else ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    )
    done = set(_load_ckpt(backend))
    path = _ckpt_path(backend)
    sl = [r for r in rows[start:start + count] if r.eval_id not in done]
    written = 0
    with path.open("a", encoding="utf-8") as fh:
        if backend == "local-reranked":
            # Mini-batch + flush so partial progress survives a process kill
            # (this sandbox caps wall-time per call). Re-running the same command
            # is idempotent — already-checkpointed eval_ids are skipped.
            mini = 20
            for i in range(0, len(sl), mini):
                for eid, hits in _score_reranked_batch(sl[i:i + mini], top_k, candidate_k):
                    fh.write(json.dumps({"eval_id": eid, "hits": hits}) + "\n")
                    written += 1
                fh.flush()
        else:
            fn = _backend_fn(backend)
            for r in sl:
                hits = fn(r.question_text, top_k)
                fh.write(json.dumps({"eval_id": r.eval_id, "hits": hits}) + "\n")
                written += 1
        fh.flush()
    total = len(_load_ckpt(backend))
    print(
        f"{backend}: scored {written} new rows in [{start}:{start+count}]; "
        f"checkpoint now holds {total}/{len(rows)}"
    )


def _make_replay_backend(backend: str, golden_rows):
    """Replay the checkpoint as a harness RetrieveFn (query-keyed, real scores)."""
    ckpt = _load_ckpt(backend)
    id_to_query = {r.eval_id: r.question_text for r in golden_rows}
    q_to_hits: dict[str, list[tuple[str, float]]] = {}
    covered: set[str] = set()
    for eid, hits in ckpt.items():
        q = id_to_query.get(eid)
        if q is None:
            continue
        q_to_hits[q] = hits
        covered.add(eid)

    def retrieve(query: str, top_k: int = ph.TOP_K) -> list[tuple[str, float]]:
        return q_to_hits.get(query, [])[:top_k]

    retrieve.restrict_to_eval_ids = covered  # type: ignore[attr-defined]
    return retrieve


def phase_report(backend: str, subset: bool, baseline_strands: Path | None) -> int:
    rows = ph.load_rows(ph.DEFAULT_GOLDEN_CSV, only_golden_subset=subset)
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    fn = _make_replay_backend(backend, all_rows)
    restrict = getattr(fn, "restrict_to_eval_ids", None)
    if restrict is not None:
        missing = [r.eval_id for r in rows if r.eval_id not in restrict]
        if missing:
            print(
                f"WARNING: {len(missing)} of {len(rows)} rows not yet in the "
                f"{backend} checkpoint — run more `score` slices first.",
                file=sys.stderr,
            )
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="phase", required=True)

    sc = sub.add_parser("score", help="checkpoint top-K for a row slice")
    sc.add_argument("backend", choices=["local-cosine", "local-reranked"])
    sc.add_argument("--start", type=int, default=0)
    sc.add_argument("--count", type=int, default=10_000)
    sc.add_argument("--top-k", type=int, default=ph.TOP_K)
    sc.add_argument("--candidate-k", type=int, default=20)
    sc.add_argument("--subset", action="store_true",
                    help="score within the golden subset population")

    rp = sub.add_parser("report", help="replay checkpoint through the harness")
    rp.add_argument("backend", choices=["local-cosine", "local-reranked"])
    rp.add_argument("--subset", action="store_true")
    rp.add_argument("--baseline-strands", type=Path, default=None)

    args = ap.parse_args(argv)
    if args.phase == "score":
        phase_score(
            args.backend, args.start, args.count, args.top_k, args.candidate_k,
            subset=args.subset,
        )
        return 0
    return phase_report(args.backend, args.subset, args.baseline_strands)


if __name__ == "__main__":
    sys.exit(main())
