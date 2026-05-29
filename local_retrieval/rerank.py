"""Local cross-encoder reranker over ``local_retrieval.retrieve`` — Snowflake-exit
Phase-0 spike (AGENT_30).

The cosine-only local retriever (AGENT_29) recalls the right tutorial well but,
per ``docs/SNOWFLAKE_EXIT_PLAN.md`` §5, is expected to *misrank* close cousins at
rank 1 — exactly the failure mode Cortex's reranker fixes. This module is the
load-bearing component that tries to recover that parity offline and for free:

1. pull a **wide** candidate set from ``retrieve`` (default top-20),
2. re-score each ``(query, tutorial-text)`` pair with a LOCAL cross-encoder
   (``cross-encoder/ms-marco-MiniLM-L-6-v2`` — ONNX-free, no API key, runs on
   CPU after a one-time model download), and
3. return the top-``k`` reranked ``(slug, score)`` pairs.

Score calibration
-----------------
The cross-encoder emits an **unbounded** relevance logit (observed roughly
-11 .. +9 on this corpus). We map it to ``[0, 1]`` with the logistic, mirroring
the live retriever's ``_sigmoid_normalize`` (``api/orchestrator/retriever.py``)
so the emitted score is directly comparable to ``RETRIEVAL_FLOOR = 0.30`` and to
the Cortex reranker's calibrated score. The mapping is order-preserving, so it
never changes the reranked order — only the absolute scale.

This module is **spike-only**: it is never imported by ``api/`` and adds no
dependency to the live serving path during the exam-week freeze. Wiring a
reranker into ``/query`` is Phase 2, post-freeze.
"""
from __future__ import annotations

import functools
import math
import os
from pathlib import Path

from .core import DEFAULT_INDEX_DIR, DEFAULT_TOP_K, retrieve
from .store import open_tutor_table

# The spike reranker. A small (~80MB) MS-MARCO-tuned cross-encoder; no API key,
# CPU-only, one-time download. The PRODUCTION reranker (hosted vs local) is a
# Phase-3 decision (docs/SNOWFLAKE_EXIT_PLAN.md §3) — swappable via model_name.
DEFAULT_RERANKER_MODEL = os.environ.get(
    "LOCAL_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)

# Width of the candidate pool pulled from cosine retrieve() before reranking.
# Wide enough that a true positive the cosine stage ranks mid-pack still reaches
# the cross-encoder, small enough to keep CPU reranking cheap on this corpus.
DEFAULT_CANDIDATE_K = 20

# Char cap on the tutorial text handed to the cross-encoder. We lead with
# ``title_plus_phrasings`` — the highest-signal field for matching a student's
# phrasing, since it literally contains the canonical title + paraphrases — then
# the head of ``body`` for topical grounding. ~256 chars (~64 tokens) is enough
# to capture the title + phrasings while keeping CPU rerank throughput high
# (~150 cross-encoder pairs/s vs ~50 at 700 chars), which is what makes a full
# 3.4k-row offline pass tractable. Text length is a quality/latency knob for
# Phase 2: a hosted reranker removes the latency constraint and can rerank the
# full body — see the report's hosted-vs-local note.
_RERANK_TEXT_CAP = 256


@functools.lru_cache(maxsize=2)
def _get_reranker(model_name: str):
    """Load (and process-cache) a sentence-transformers CrossEncoder.

    Imported lazily so importing this module (e.g. in a test that injects a
    stub scorer) does not force torch / sentence-transformers.
    """
    from sentence_transformers import CrossEncoder  # noqa: PLC0415 (heavy, lazy)

    return CrossEncoder(model_name, max_length=512)


@functools.lru_cache(maxsize=4)
def _slug_to_text(index_dir_str: str) -> dict[str, str]:
    """Build a ``slug -> rerank text`` map from the index, cached per index dir.

    The rerank text is ``title_plus_phrasings`` + the head of ``body`` — the
    same two fields Cortex's TUTOR_SEARCH indexed — so the cross-encoder sees a
    representative document, not just a slug.
    """
    table = open_tutor_table(index_dir_str)
    rows = table.to_lance().to_table(
        columns=["slug", "title_plus_phrasings", "body"]
    ).to_pylist()
    out: dict[str, str] = {}
    for r in rows:
        slug = r.get("slug")
        if not slug:
            continue
        head = (r.get("title_plus_phrasings") or "").strip()
        body = (r.get("body") or "").strip()
        text = (head + "\n\n" + body)[:_RERANK_TEXT_CAP]
        out[slug] = text or slug
    return out


def _sigmoid(raw: float) -> float:
    """Logistic map of an unbounded logit onto ``[0, 1]``.

    Mirrors ``retriever._sigmoid_normalize`` (including the overflow clamps) so
    the reranked score is on the same calibrated scale as the live path and
    directly comparable to ``RETRIEVAL_FLOOR``.
    """
    if raw != raw:  # NaN guard
        return 0.0
    if raw >= 700:
        return 1.0
    if raw <= -700:
        return 0.0
    return 1.0 / (1.0 + math.exp(-raw))


def rerank_detailed(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_RERANKER_MODEL,
) -> list[dict[str, float | str]]:
    """Rerank and return per-candidate detail for analysis/recalibration.

    Each dict carries ``slug``, ``cosine`` (the AGENT_29 cosine similarity),
    ``logit`` (raw cross-encoder score) and ``score`` (sigmoid(logit)). Sorted
    best-first by the reranked score, truncated to ``top_k``.
    """
    if not query or not query.strip() or top_k <= 0:
        return []
    idx = index_dir if index_dir is not None else DEFAULT_INDEX_DIR
    candidates = retrieve(query, candidate_k, index_dir=idx)
    if not candidates:
        return []

    text_map = _slug_to_text(str(idx))
    pairs = [(query, text_map.get(slug, slug)) for slug, _ in candidates]
    reranker = _get_reranker(model_name)
    logits = reranker.predict(pairs)

    scored = [
        {
            "slug": slug,
            "cosine": float(cos),
            "logit": float(logit),
            "score": _sigmoid(float(logit)),
        }
        for (slug, cos), logit in zip(candidates, logits)
    ]
    scored.sort(key=lambda d: d["score"], reverse=True)  # type: ignore[arg-type,return-value]
    return scored[:top_k]


def retrieve_reranked(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    candidate_k: int = DEFAULT_CANDIDATE_K,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_RERANKER_MODEL,
) -> list[tuple[str, float]]:
    """Return up to ``top_k`` ``(slug, score)`` pairs, reranked best-first.

    Matches the shared backend contract (``SNOWFLAKE_EXIT_DISPATCH.md``):
    ``score`` is calibrated to ``[0, 1]`` and directly comparable to
    ``RETRIEVAL_FLOOR = 0.30``. Empty/whitespace query or ``top_k <= 0`` → ``[]``.
    """
    detail = rerank_detailed(
        query, top_k, candidate_k=candidate_k,
        index_dir=index_dir, model_name=model_name,
    )
    return [(str(d["slug"]), round(float(d["score"]), 6)) for d in detail]
