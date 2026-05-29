"""``retrieve(query, top_k) -> list[(slug, score)]`` — the shared contract.

This is the local backend the Snowflake-exit parity spike measures (AGENT_30
wraps a reranker on top; this layer is deliberately rerank-free). It mirrors
the live ``api/orchestrator/retriever.py`` score semantics so the numbers are
directly comparable to the locked Cortex baseline.

Score calibration
-----------------
The spike embeddings (bge-small-en-v1.5) are L2-normalised, so cosine
similarity equals the dot product and lands in ``[-1, 1]`` — and in practice
``[0, 1]`` for topically-related English text. LanceDB's ``cosine`` metric
returns ``_distance = 1 - cosine_similarity``; we map back with::

    score = clamp(1 - _distance, 0.0, 1.0)

This puts ``score`` on the SAME ``[0, 1]`` scale as the live retriever's
``@scores.cosine_similarity`` field and directly comparable to
``RETRIEVAL_FLOOR = 0.30``. We clamp (rather than rescale ``(x+1)/2``) precisely
so the floor keeps its meaning: a 0.30 cosine here means the same "weak match"
it means in the Cortex path.

Multi-field merge
-----------------
Cortex's ``TUTOR_SEARCH`` embedded ``title_plus_phrasings`` and ``body``
independently. We store both vectors and, per query, search each column then
keep the **max** similarity per slug — so a near-verbatim phrasing hit and a
paragraph-grounded body hit each get represented. Best-first, deduped by slug,
truncated to ``top_k``.
"""
from __future__ import annotations

import os
from pathlib import Path

from .embedding import DEFAULT_MODEL, embed_query
from .store import open_tutor_table

# Default index location: <repo-root>/local_index (the LanceDB database dir;
# the tutor table lives at local_index/tutor.lance). Overridable via env for
# the harness / tests without changing the call sites.
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX_DIR = Path(os.environ.get("LOCAL_INDEX_DIR", _REPO_ROOT / "local_index"))

# Match the live serving path so spike numbers are apples-to-apples.
DEFAULT_TOP_K = 5

# Per-column candidate pool before the cross-column max-merge. A small
# multiple of top_k is plenty for a few-hundred-row corpus and keeps the merge
# cheap while ensuring a slug that ranks mid-pack on one field but top on the
# other still surfaces.
_CANDIDATE_FACTOR = 6
_MIN_CANDIDATES = 25


def _clamp01(x: float) -> float:
    if x != x:  # NaN guard
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    *,
    index_dir: Path | str | None = None,
    model_name: str = DEFAULT_MODEL,
) -> list[tuple[str, float]]:
    """Return up to ``top_k`` ``(slug, score)`` pairs, ranked best-first.

    ``score`` is calibrated to ``[0, 1]`` and directly comparable to
    ``RETRIEVAL_FLOOR = 0.30`` (see module docstring). An empty / whitespace
    query returns ``[]``. ``top_k <= 0`` returns ``[]``.
    """
    if not query or not query.strip() or top_k <= 0:
        return []

    table = open_tutor_table(index_dir if index_dir is not None else DEFAULT_INDEX_DIR)
    qvec = embed_query(query, model_name=model_name)

    n_candidates = max(top_k * _CANDIDATE_FACTOR, _MIN_CANDIDATES)
    best: dict[str, float] = {}

    for column in ("vec_phrasings", "vec_body"):
        hits = (
            table.search(qvec, vector_column_name=column)
            .metric("cosine")
            .limit(n_candidates)
            .select(["slug"])
            .to_list()
        )
        for h in hits:
            slug = h.get("slug")
            if not slug:
                continue
            sim = _clamp01(1.0 - float(h.get("_distance", 1.0)))
            if sim > best.get(slug, -1.0):
                best[slug] = sim

    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    return [(slug, round(score, 6)) for slug, score in ranked[:top_k]]
