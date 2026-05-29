"""Hosted-librarian retrieval backends — Snowflake-exit Phase-0 v4 (AGENT_33).

Three backends, each isolating one lever vs the v1→v3 local stack, all over the
**same** chunk set as AGENT_29 (chunking held constant so the embedding lever is
the only thing that moves):

* ``voyage-cosine``         — Voyage ``voyage-3.5`` dense vectors, vector-only.
                              Isolates the *embedding-quality* lever vs arctic.
* ``voyage-hybrid``         — Voyage dense ⊕ BM25, fused with RRF (reused from
                              :mod:`local_retrieval.hybrid`). The hosted analogue
                              of v2.
* ``voyage-hybrid-rerank``  — + a hosted reranker (Voyage ``rerank-2.5``). Mirrors
                              Cortex's full internal pipeline; the candidate.

The dense leg reuses :func:`local_retrieval.core.retrieve` (which routes a
``voyage*`` ``model_name`` to the cached hosted embedder via
:mod:`local_retrieval.embedding`). The lexical leg and RRF fusion reuse
AGENT_31's :mod:`local_retrieval.hybrid`. The rerank stage reuses
:mod:`local_retrieval.hosted_rerank`. Nothing about the gate or the chunking
changes — only the embedder and the optional rerank stage.

Spike-only: never imported by ``api/``.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

from .core import retrieve as retrieve_dense
from .hosted_rerank import RerankCache, rerank
from .hybrid import (
    DEFAULT_N_CANDIDATES,
    DEFAULT_RRF_K,
    DEFAULT_TOP_K,
    retrieve_hybrid,
)

DEFAULT_VOYAGE_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5")

# Width of the candidate pool handed to the hosted reranker. Wide enough that a
# true positive ranked mid-pack by the hybrid still reaches the reranker; the
# rerank-2.5 32K context makes a 30-wide pool cheap.
DEFAULT_RERANK_CANDIDATE_K = 30


def _default_voyage_index_dir() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    return os.environ.get("VOYAGE_INDEX_DIR", str(repo_root / "local_index_voyage"))


@functools.lru_cache(maxsize=4)
def _slug_to_text(index_dir_str: str) -> dict[str, str]:
    """``slug -> rerank text`` (title_plus_phrasings + head of body), cached per
    index dir. Same two fields Cortex indexed, so the reranker sees a
    representative document. Reuses the index already built for the dense leg."""
    from .store import open_tutor_table  # noqa: PLC0415 (lazy: lancedb)

    table = open_tutor_table(index_dir_str)
    rows = (
        table.to_lance()
        .to_table(columns=["slug", "title_plus_phrasings", "body"])
        .to_pylist()
    )
    cap = 2000  # rerank-2.5 has a 32K context; 2k chars (~512 tok) is ample.
    out: dict[str, str] = {}
    for r in rows:
        slug = r.get("slug")
        if not slug:
            continue
        head = (r.get("title_plus_phrasings") or "").strip()
        body = (r.get("body") or "").strip()
        out[slug] = (head + "\n\n" + body)[:cap] or slug
    return out


def retrieve_voyage_cosine(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_VOYAGE_MODEL,
) -> list[tuple[str, float]]:
    """Vector-only Voyage retrieval — the embedding-quality lever in isolation."""
    idx = index_dir if index_dir is not None else _default_voyage_index_dir()
    return retrieve_dense(query, top_k, index_dir=idx, model_name=model_name)


def retrieve_voyage_hybrid(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_VOYAGE_MODEL,
    n_candidates: int = DEFAULT_N_CANDIDATES,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[tuple[str, float]]:
    """Voyage dense ⊕ BM25, RRF-fused — the hosted analogue of v2's hybrid."""
    idx = index_dir if index_dir is not None else _default_voyage_index_dir()
    return retrieve_hybrid(
        query, top_k, index_dir=idx, model_name=model_name,
        n_candidates=n_candidates, rrf_k=rrf_k,
    )


def retrieve_voyage_hybrid_rerank(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    eval_id: str,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_VOYAGE_MODEL,
    n_candidates: int = DEFAULT_N_CANDIDATES,
    rrf_k: int = DEFAULT_RRF_K,
    rerank_candidate_k: int = DEFAULT_RERANK_CANDIDATE_K,
    rerank_vendor: str = "voyage",
    rerank_model: str | None = None,
    rerank_cache: RerankCache | None = None,
    allow_api: bool = False,
) -> list[tuple[str, float]]:
    """The candidate: Voyage⊕BM25 hybrid, then a hosted rerank of the wide pool.

    Mirrors Cortex's full pipeline (dense + lexical + managed reranker). The
    rerank cache is keyed by ``eval_id`` + the candidate set, so scoring replays
    offline once the cache is populated. Empty query / ``top_k <= 0`` → ``[]``.
    """
    if not query or not query.strip() or top_k <= 0:
        return []
    idx = index_dir if index_dir is not None else _default_voyage_index_dir()

    # Wide candidate pool from the hybrid fuser.
    fused = retrieve_hybrid(
        query, rerank_candidate_k, index_dir=idx, model_name=model_name,
        n_candidates=n_candidates, rrf_k=rrf_k,
    )
    if not fused:
        return []

    text_map = _slug_to_text(str(idx))
    candidates = [(slug, text_map.get(slug, slug)) for slug, _ in fused]

    reranked = rerank(
        eval_id=eval_id, query=query, candidates=candidates,
        vendor=rerank_vendor, model=rerank_model,
        cache=rerank_cache, allow_api=allow_api,
    )
    return reranked[:top_k]
