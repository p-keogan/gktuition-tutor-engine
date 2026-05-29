"""Hybrid (dense + lexical) retrieval with Reciprocal Rank Fusion — Snowflake-exit
Phase-0 v2 (AGENT_31).

This is the *candidate* architecture: it reproduces what Cortex Search actually
does. The live ``api/orchestrator/retriever.py`` consumes BOTH a lexical signal
(``text_match``) and vector signals (``cosine_similarity``, ``reranker_score``)
from each Cortex hit — i.e. Cortex is itself a hybrid retriever. AGENT_30's v1
spike used the weakest possible stand-in (vector-only, ``bge-small``) and
NO-GO'd at recall@20 ≈ 0.78–0.83, with the collapse concentrated in cryptic
``solution_cross_ref`` rows (0.752). This module tests the two missing levers
together:

* a stronger, query/document-asymmetric dense model (arctic-embed-m), via
  :func:`local_retrieval.retrieve` pointed at the arctic index;
* a lexical BM25 index (:mod:`local_retrieval.bm25_index`), which should recover
  the literal-token cross-ref rows the dense path misses.

Fusion: Reciprocal Rank Fusion (RRF). For each retriever we take its top-N
ranked list and credit every returned doc ``1 / (rrf_k + rank)`` (rank 1-indexed,
``rrf_k = 60`` — the Cormack et al. default, robust and tuning-free). A doc's
fused score is the sum over retrievers, so a doc both retrievers rank highly
beats one only a single retriever likes. RRF deliberately uses *rank*, not raw
score, so the wildly different scales of cosine ``[0,1]`` and unbounded BM25
never need reconciling — the chief reason RRF is the standard hybrid fuser.

Score calibration
-----------------
The emitted ``[0, 1]`` score is the fused RRF score divided by the max fused
score in the candidate set (top hit → 1.0). This is **analysis-only** (so the
parity harness's floor / mean-top-1 metrics render); a real
``RETRIEVAL_FLOOR`` recalibration against this distribution is a Phase-2 task and
is flagged as such in the report. The *ranking* the gate scores on depends only
on the fused RRF order, not on this normalisation.

Spike-only: never imported by ``api/``; adds no dependency to the live serving
path during the exam-week freeze. Wiring hybrid into ``/query`` is Phase 2,
post-freeze.
"""
from __future__ import annotations

import os
from pathlib import Path

from .bm25_index import retrieve_bm25_raw
from .core import retrieve as retrieve_dense

# The v2 dense model: the arctic-embed family Cortex's managed embeddings come
# from. Swappable, but this is the spike default for the hybrid candidate.
DEFAULT_HYBRID_MODEL = os.environ.get(
    "LOCAL_HYBRID_MODEL", "snowflake/snowflake-arctic-embed-m"
)

DEFAULT_TOP_K = 5
# Candidates pulled from EACH retriever before fusion. Wide enough that a doc
# ranked mid-pack by one retriever still reaches the fuser; cheap on a few-
# hundred-row corpus.
DEFAULT_N_CANDIDATES = 50
# RRF constant (Cormack et al. 2009). Damps the contribution of deep ranks.
DEFAULT_RRF_K = 60


def _default_index_dir() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    return os.environ.get("LOCAL_INDEX_DIR", str(repo_root / "local_index_arctic"))


def rrf_fuse(
    ranked_lists: list[list[str]],
    rrf_k: int = DEFAULT_RRF_K,
) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion over several ranked slug lists.

    Each list is best-first. Returns ``(slug, fused_score)`` sorted best-first,
    where ``fused_score = sum_lists 1 / (rrf_k + rank)`` (rank 1-indexed).
    A doc present in multiple lists accumulates across them.
    """
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, slug in enumerate(ranked, start=1):
            if not slug:
                continue
            fused[slug] = fused.get(slug, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(fused.items(), key=lambda kv: kv[1], reverse=True)


def retrieve_hybrid(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_HYBRID_MODEL,
    n_candidates: int = DEFAULT_N_CANDIDATES,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[tuple[str, float]]:
    """Return up to ``top_k`` ``(slug, score)`` pairs, hybrid-fused best-first.

    Pulls ``n_candidates`` from the arctic dense index and from BM25, fuses with
    RRF, normalises the fused score into ``[0, 1]`` (analysis-only; see module
    docstring), and returns the top ``top_k``. Empty/whitespace query or
    ``top_k <= 0`` → ``[]``. Matches the shared backend contract.
    """
    if not query or not query.strip() or top_k <= 0:
        return []
    idx = index_dir if index_dir is not None else _default_index_dir()

    dense_hits = retrieve_dense(
        query, n_candidates, index_dir=idx, model_name=model_name
    )
    bm25_hits = retrieve_bm25_raw(query, n_candidates, index_dir=idx)

    dense_slugs = [slug for slug, _ in dense_hits]
    bm25_slugs = [slug for slug, _ in bm25_hits]

    fused = rrf_fuse([dense_slugs, bm25_slugs], rrf_k=rrf_k)
    if not fused:
        return []

    top_fused = fused[0][1] or 1.0
    out: list[tuple[str, float]] = []
    for slug, score in fused[:top_k]:
        norm = score / top_fused if top_fused > 0 else 0.0
        norm = 0.0 if norm < 0.0 else 1.0 if norm > 1.0 else norm
        out.append((slug, round(norm, 6)))
    return out
