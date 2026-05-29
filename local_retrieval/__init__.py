"""local_retrieval — offline LanceDB-backed retrieval for the Snowflake-exit spike.

Exposes the shared retrieval contract:

    from local_retrieval import retrieve
    retrieve(query: str, top_k: int = 5) -> list[tuple[str, float]]

`score` is calibrated to [0, 1] and directly comparable to the live
RETRIEVAL_FLOOR (0.30). Phase 1 / spike only — NOT imported by the live app
(`api/`). Rerank-free by design; AGENT_30 wraps a reranker on top.
"""
from __future__ import annotations

from .core import DEFAULT_INDEX_DIR, DEFAULT_TOP_K, retrieve

__all__ = ["retrieve", "DEFAULT_INDEX_DIR", "DEFAULT_TOP_K"]
