"""Hosted reranker adapter (Voyage ``rerank-2.5``, optional Cohere
``rerank-v3.5``) with an on-disk result cache — Snowflake-exit Phase-0 v4
(AGENT_33).

This is the component most likely to fix the binding-constraint rows. Across
v1→v3 the failure localised to terse ``solution_cross_ref`` exam prompts, where
a wide candidate pool *contains* the right tutorial but the top-1 is a close
cousin. A strong reranker re-scores ``(query, candidate)`` pairs directly and is
exactly what Cortex's managed reranker does internally — so a hosted reranker on
top of the Voyage⊕BM25 hybrid is the closest offline analogue to Cortex's full
pipeline.

It mirrors AGENT_30's local reranker (``rerank.py``) but swaps the local
cross-encoder for a hosted call, and caches every result so all downstream
scoring is offline / free / reproducible.

Score calibration
-----------------
Voyage's ``relevance_score`` is already in ``[0, 1]``; Cohere's likewise. We
pass it through a defensive min-max calibration *within each query's candidate
set* (top hit → 1.0) so the emitted score is directly comparable to
``RETRIEVAL_FLOOR = 0.30`` regardless of vendor, and a degenerate all-equal set
never collapses to 0.0. Calibration is **order-preserving**, so it never changes
the reranked order — only the absolute scale (same contract as ``rerank.py``).

Cache
-----
Results are cached to disk keyed by ``sha1(model | eval_id | candidate-set)``
(candidate slugs sorted, so the key is independent of the order the candidates
arrived in). A cache miss with no API key raises — the adapter never fabricates
a reranking (dispatch rule 4d).

Spend posture
-------------
Default vendor is **Voyage** (free tier covers the corpus + golden set at ~$0).
Cohere is an OPTIONAL secondary comparison, used only if ``COHERE_API_KEY`` is
present AND the operator opted in via the runner flag.

Spike-only: never imported by ``api/``.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

# Confirmed current at build time (2026-05-29): Voyage rerank-2.5 (32K context,
# instruction-following); Cohere rerank-v3.5. Swappable via env.
DEFAULT_VOYAGE_RERANKER = os.environ.get("VOYAGE_RERANK_MODEL", "rerank-2.5")
DEFAULT_COHERE_RERANKER = os.environ.get("COHERE_RERANK_MODEL", "rerank-v3.5")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_cache_path() -> Path:
    """``<repo>/eval/cache/voyage_rerank.json`` unless ``HOSTED_RERANK_CACHE``
    overrides. One JSON file keyed by the rerank cache key."""
    env = os.environ.get("HOSTED_RERANK_CACHE")
    if env:
        return Path(env)
    return _repo_root() / "eval" / "cache" / "hosted_rerank.json"


def rerank_cache_key(model: str, eval_id: str, candidate_slugs: Sequence[str]) -> str:
    """Order-independent cache key for one rerank request.

    Keyed on the candidate *set* (sorted) so re-running with a differently
    ordered candidate list (e.g. a re-fused hybrid) still hits the cache as long
    as the same slugs were submitted.
    """
    h = hashlib.sha1()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(eval_id.encode("utf-8"))
    h.update(b"\x00")
    h.update("\x1f".join(sorted(candidate_slugs)).encode("utf-8"))
    return h.hexdigest()


class RerankCache:
    """A flat ``{key: [[slug, score], ...]}`` JSON cache on disk."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_cache_path()
        self._data: dict[str, list[list]] | None = None

    def _ensure(self) -> dict[str, list[list]]:
        if self._data is None:
            if self.path.is_file():
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            else:
                self._data = {}
        return self._data

    def get(self, key: str) -> list[tuple[str, float]] | None:
        data = self._ensure()
        hit = data.get(key)
        return None if hit is None else [(s, float(sc)) for s, sc in hit]

    def put(self, key: str, ranked: list[tuple[str, float]]) -> None:
        data = self._ensure()
        data[key] = [[s, float(sc)] for s, sc in ranked]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._ensure(), indent=0), encoding="utf-8"
        )

    def __len__(self) -> int:
        return len(self._ensure())


def _clamp01(x: float) -> float:
    if x != x:  # NaN guard
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _minmax_calibrate(
    scored: list[tuple[str, float]],
) -> list[tuple[str, float]]:
    """Min-max calibrate raw relevance scores into ``[0, 1]`` within the set,
    top hit → 1.0. Order-preserving (already sorted best-first by the caller)."""
    if not scored:
        return []
    vals = [s for _, s in scored]
    hi, lo = max(vals), min(vals)
    span = hi - lo
    out: list[tuple[str, float]] = []
    for slug, s in scored:
        norm = 1.0 if span <= 0 else _clamp01((s - lo) / span)
        out.append((slug, round(norm, 6)))
    return out


# ── hosted vendor calls (lazy; only on a cache miss) ─────────────────────────
def _voyage_rerank_raw(
    query: str, documents: list[str], slugs: list[str], *, model: str,
) -> list[tuple[str, float]]:
    try:
        import voyageai  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "voyageai not installed; `pip install -r requirements-local.txt`."
        ) from exc
    if not (os.environ.get("VOYAGE_API_KEY") or os.environ.get("VOYAGEAI_API_KEY")):
        raise RuntimeError(
            "No VOYAGE_API_KEY; rerank results must be cache-served (dispatch 4d)."
        )
    client = voyageai.Client()
    resp = client.rerank(query, documents, model=model, top_k=len(documents))
    # resp.results: objects with .index (into documents) and .relevance_score
    ranked = [
        (slugs[r.index], float(r.relevance_score)) for r in resp.results
    ]
    return ranked


def _cohere_rerank_raw(
    query: str, documents: list[str], slugs: list[str], *, model: str,
) -> list[tuple[str, float]]:
    try:
        import cohere  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError("cohere not installed (optional secondary vendor).") from exc
    if not os.environ.get("COHERE_API_KEY"):
        raise RuntimeError("No COHERE_API_KEY; Cohere is opt-in secondary only.")
    client = cohere.Client(os.environ["COHERE_API_KEY"])
    resp = client.rerank(
        query=query, documents=documents, model=model, top_n=len(documents)
    )
    ranked = [
        (slugs[r.index], float(r.relevance_score)) for r in resp.results
    ]
    return ranked


def _vendor_rerank(
    vendor: str, query: str, documents: list[str], slugs: list[str], *, model: str,
) -> list[tuple[str, float]]:
    if vendor == "voyage":
        return _voyage_rerank_raw(query, documents, slugs, model=model)
    if vendor == "cohere":
        return _cohere_rerank_raw(query, documents, slugs, model=model)
    raise ValueError(f"unknown rerank vendor {vendor!r}")


def rerank(
    *,
    eval_id: str,
    query: str,
    candidates: Sequence[tuple[str, str]],
    vendor: str = "voyage",
    model: str | None = None,
    cache: RerankCache | None = None,
    allow_api: bool = False,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Rerank ``candidates`` (each ``(slug, document_text)``) for ``query``.

    Returns ``[(slug, calibrated_score)]`` best-first, calibrated to ``[0, 1]``.
    Cache-served by default; a miss raises unless ``allow_api`` (the bounded
    ``build-cache`` pass). Newly fetched results are written into ``cache`` (the
    caller calls :meth:`RerankCache.save`). ``eval_id`` keys the cache so scoring
    replays deterministically without re-submitting query text.
    """
    model = model or (DEFAULT_VOYAGE_RERANKER if vendor == "voyage" else DEFAULT_COHERE_RERANKER)
    cache = cache if cache is not None else RerankCache()
    slugs = [s for s, _ in candidates]
    key = rerank_cache_key(model, eval_id, slugs)

    hit = cache.get(key)
    if hit is None:
        if not allow_api:
            raise KeyError(
                f"rerank cache MISS for eval_id={eval_id!r} ({len(slugs)} cands, "
                f"{vendor}/{model}); API disabled. Run the bounded build-cache pass."
            )
        documents = [doc for _, doc in candidates]
        raw = _vendor_rerank(vendor, query, documents, slugs, model=model)
        hit = raw
        cache.put(key, raw)

    calibrated = _minmax_calibrate(hit)
    return calibrated[:top_k] if top_k is not None else calibrated
