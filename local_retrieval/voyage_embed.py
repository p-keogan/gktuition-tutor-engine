"""Hosted (Voyage) embeddings with an on-disk cache — Snowflake-exit Phase-0 v4
(AGENT_33).

The v1→v3 spikes proved a *local-CPU* retrieval stack cannot match Cortex
(P@1 0.41 → 0.50 → ≤0.53 vs the locked 0.911 gate) and traced the failure to
**embedding recall on terse exam cross-reference rows** (``solution_cross_ref``
recall@20 stuck at ~0.78, needs ~0.92). This module tests the one untested
lever: a strong *hosted* embedder (Voyage ``voyage-3.5``) in place of the local
arctic-embed model, holding the chunk set and the rest of the pipeline constant.

Why a hosted librarian is now on the table
------------------------------------------
Per the operator decision (DAY_34), Cortex's own cost is negligible, so the
migration is about **simplicity + dropping the warehouse compute model**, not
saving money. The target design is a cheap always-on store (pgvector / embedded
LanceDB) + a hosted librarian (Voyage embed + rerank) — no warehouse. This
module validates only the *quality* half of that design, entirely offline once
the cache is populated.

The asymmetry that bit AGENT_31 — DO NOT repeat it
--------------------------------------------------
arctic-embed silently degraded to near-random in an earlier spike because the
query-side instruction prefix was not applied (P@1 0.18 vs 0.41). Voyage has the
**same** query/document asymmetry, surfaced through the ``input_type`` argument:

* embed **chunks** with ``input_type="document"``  (Voyage prepends
  "Represent the document for retrieval: ")
* embed **queries** with ``input_type="query"``    (Voyage prepends
  "Represent the query for retrieving supporting documents: ")

Getting this wrong produces a *false NO-GO*. :func:`embed_documents` and
:func:`embed_queries` below hard-wire the correct ``input_type`` so a caller
cannot mix them up, and ``local_retrieval/tests/test_voyage_embed.py`` asserts
the exact value reaches the client for both paths.

Caching (so all scoring afterwards is offline, free, reproducible)
------------------------------------------------------------------
Every vector is cached to disk keyed by ``sha1(input_type + "\\x00" + text)``.
A re-run hits the cache and spends $0 / makes zero API calls. The cache is a
consolidated ``(index.json, vectors.npy)`` pair per model — compact, committable,
and replayable with no Voyage key present. Cache **misses** with no API key
available raise a clear, actionable error (they never silently fabricate a
vector — rule 4(d) of the dispatch).

Spend posture
-------------
* Default model: ``voyage-3.5`` (1024-dim, L2-normalised on our side).
* The whole corpus (~3.4k chunks × 2 fields) + the 3,430-row golden set is on the
  order of a few million tokens — comfortably inside Voyage's 200M-token free
  tier, so the expected spend is **~$0**. :func:`estimate_tokens` prints the
  estimate before any call and the runner enforces ``--max-calls``.

Spike-only: never imported by ``api/``; adds no dependency to the live serving
path during the exam-week freeze. Wiring a hosted embedder into ``/query`` is
Phase 2, post-freeze, and only if v4 returns GO.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np

# Default hosted embedding model (confirmed current at build time, 2026-05-29:
# voyage-3.5 — 1024-dim default, 32K context, query/document input_type). The
# production model choice remains a Phase-2 decision; swappable via model_name
# and the runner's env.
DEFAULT_VOYAGE_MODEL = os.environ.get("VOYAGE_EMBED_MODEL", "voyage-3.5")

# Known output dims (default output_dimension) for the models the spike supports.
VOYAGE_MODEL_DIMS: dict[str, int] = {
    "voyage-3.5": 1024,
    "voyage-3.5-lite": 1024,
    "voyage-3-large": 1024,
    "voyage-3": 1024,
}

# A model_name is "hosted Voyage" iff it begins with "voyage". This is the
# routing predicate embedding.py uses to delegate here instead of fastembed.
def is_voyage_model(model_name: str) -> bool:
    """True if ``model_name`` names a Voyage hosted embedding model."""
    return model_name.lower().startswith("voyage")


def model_dim(model_name: str = DEFAULT_VOYAGE_MODEL) -> int:
    """Embedding dimension for ``model_name`` (default-dimension output)."""
    return VOYAGE_MODEL_DIMS.get(model_name, 1024)


# ── cache key ───────────────────────────────────────────────────────────────
def cache_key(text: str, input_type: str) -> str:
    """Stable cache key for one (text, input_type) pair.

    ``input_type`` is part of the key because the *same* string embedded as a
    document vs a query produces different Voyage vectors (different prepended
    prompt) — they must never collide in the cache.
    """
    h = hashlib.sha1()
    h.update(input_type.encode("utf-8"))
    h.update(b"\x00")
    h.update((text or " ").encode("utf-8"))
    return h.hexdigest()


def _l2_normalise(vecs: np.ndarray) -> np.ndarray:
    """L2-normalise rows so cosine == dot, matching the local path's calibration
    (core.py maps LanceDB ``cosine`` distance back to a ``[0,1]`` similarity)."""
    if vecs.ndim == 1:
        vecs = vecs[None, :]
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return (vecs / norms).astype(np.float32)


# ── on-disk vector cache ──────────────────────────────────────────────────────
def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def default_cache_dir() -> Path:
    """``<repo>/eval/cache/voyage_embed`` unless ``VOYAGE_EMBED_CACHE`` overrides."""
    env = os.environ.get("VOYAGE_EMBED_CACHE")
    if env:
        return Path(env)
    return _repo_root() / "eval" / "cache" / "voyage_embed"


def _model_slug(model_name: str) -> str:
    return model_name.replace("/", "_")


class VoyageEmbedCache:
    """Consolidated, committable vector cache for one model.

    Layout (per model)::

        <cache_dir>/<model_slug>/index.json   # {cache_key: row_int}
        <cache_dir>/<model_slug>/vectors.npy   # (N, dim) float32, L2-normalised

    Designed so ``report``/``recall`` scoring replays from disk with **no** API
    key. Appends are batched and flushed via :meth:`save`.
    """

    def __init__(self, model_name: str, cache_dir: Path | str | None = None) -> None:
        self.model_name = model_name
        base = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self.dir = base / _model_slug(model_name)
        self._index: dict[str, int] = {}
        self._vectors: list[np.ndarray] = []  # row-aligned with _index values
        self._loaded = False

    # -- persistence -----------------------------------------------------------
    def load(self) -> VoyageEmbedCache:
        idx_path = self.dir / "index.json"
        vec_path = self.dir / "vectors.npy"
        if idx_path.is_file() and vec_path.is_file():
            self._index = json.loads(idx_path.read_text(encoding="utf-8"))
            arr = np.load(vec_path)
            self._vectors = [arr[i] for i in range(arr.shape[0])]
        else:
            self._index, self._vectors = {}, []
        self._loaded = True
        return self

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        arr = (
            np.vstack(self._vectors).astype(np.float32)
            if self._vectors
            else np.zeros((0, model_dim(self.model_name)), dtype=np.float32)
        )
        # Write vectors first, then the index, so a crash can never leave an
        # index pointing past the end of the vector array.
        np.save(self.dir / "vectors.npy", arr)
        (self.dir / "index.json").write_text(
            json.dumps(self._index), encoding="utf-8"
        )

    # -- access ----------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def get(self, key: str) -> np.ndarray | None:
        self._ensure_loaded()
        row = self._index.get(key)
        return None if row is None else self._vectors[row]

    def put(self, key: str, vec: np.ndarray) -> None:
        self._ensure_loaded()
        if key in self._index:
            return
        self._index[key] = len(self._vectors)
        self._vectors.append(np.asarray(vec, dtype=np.float32))

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._index)


# ── Voyage client (lazy; only constructed when a cache miss must be filled) ──
def _get_client():
    """Construct a ``voyageai.Client``. Raises a clear error if the package or
    the API key is missing — never silently degrades."""
    try:
        import voyageai  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(
            "voyageai is not installed. `pip install -r requirements-local.txt` "
            "(adds voyageai). Embeddings can be replayed from cache with no key, "
            "but filling a cache MISS needs the package + VOYAGE_API_KEY."
        ) from exc
    if not (os.environ.get("VOYAGE_API_KEY") or os.environ.get("VOYAGEAI_API_KEY")):
        raise RuntimeError(
            "No VOYAGE_API_KEY in the environment. This spike never fabricates "
            "embeddings (dispatch rule 4d): populate the cache once with the "
            "bounded operator one-liner, after which all scoring is offline + free."
        )
    return voyageai.Client()


def _api_embed(
    texts: Sequence[str], *, model_name: str, input_type: str,
) -> np.ndarray:
    """Call the Voyage embeddings API for ``texts`` (no caching here)."""
    client = _get_client()
    # Voyage batches up to 128 inputs / request; keep batches modest.
    out: list[list[float]] = []
    batch = 128
    for i in range(0, len(texts), batch):
        chunk = [t if (t and t.strip()) else " " for t in texts[i : i + batch]]
        resp = client.embed(chunk, model=model_name, input_type=input_type)
        out.extend(resp.embeddings)
    return _l2_normalise(np.asarray(out, dtype=np.float32))


def _embed_with_cache(
    texts: Sequence[str],
    *,
    model_name: str,
    input_type: str,
    cache: VoyageEmbedCache | None,
    allow_api: bool,
) -> np.ndarray:
    """Return ``(n, dim)`` vectors for ``texts``, hitting ``cache`` first.

    Cache misses are embedded via the API **only if** ``allow_api`` (the runner
    sets this during a bounded ``build-cache`` pass). Otherwise a miss raises —
    scoring must be fully cache-served. Newly fetched vectors are written back
    into ``cache`` (the caller is responsible for :meth:`VoyageEmbedCache.save`).
    """
    cache = cache if cache is not None else VoyageEmbedCache(model_name)
    keys = [cache_key(t, input_type) for t in texts]
    out: list[np.ndarray | None] = [cache.get(k) for k in keys]

    missing = [i for i, v in enumerate(out) if v is None]
    if missing:
        if not allow_api:
            raise KeyError(
                f"{len(missing)} cache MISS for model={model_name!r} "
                f"input_type={input_type!r} and API calls are disabled. "
                "Run the bounded `build-cache` pass first."
            )
        fetched = _api_embed(
            [texts[i] for i in missing], model_name=model_name, input_type=input_type
        )
        for slot, vec in zip(missing, fetched):
            out[slot] = vec
            cache.put(keys[slot], vec)
    return np.vstack([v for v in out]).astype(np.float32)  # type: ignore[misc]


# ── public API (mirrors embedding.py's document/query split) ─────────────────
def embed_documents(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_VOYAGE_MODEL,
    cache: VoyageEmbedCache | None = None,
    allow_api: bool = False,
) -> np.ndarray:
    """Embed **documents** (chunks) → ``(n, dim)`` float32, L2-normalised.

    Hard-wires ``input_type="document"`` — the correct half of Voyage's
    retrieval asymmetry for chunk text.
    """
    return _embed_with_cache(
        texts, model_name=model_name, input_type="document",
        cache=cache, allow_api=allow_api,
    )


def embed_queries(
    texts: Sequence[str],
    *,
    model_name: str = DEFAULT_VOYAGE_MODEL,
    cache: VoyageEmbedCache | None = None,
    allow_api: bool = False,
) -> np.ndarray:
    """Embed **queries** → ``(n, dim)`` float32, L2-normalised.

    Hard-wires ``input_type="query"`` — the correct half of Voyage's retrieval
    asymmetry for student-prompt text. Mixing this up with the document path is
    exactly the failure that produced a false NO-GO for arctic in AGENT_31.
    """
    return _embed_with_cache(
        texts, model_name=model_name, input_type="query",
        cache=cache, allow_api=allow_api,
    )


def embed_query(
    query: str,
    *,
    model_name: str = DEFAULT_VOYAGE_MODEL,
    cache: VoyageEmbedCache | None = None,
    allow_api: bool = False,
) -> np.ndarray:
    """Single-query convenience wrapper → ``(dim,)`` float32, L2-normalised."""
    return embed_queries(
        [query], model_name=model_name, cache=cache, allow_api=allow_api
    )[0]


# ── token / cost estimation (printed BEFORE any spend) ───────────────────────
# Voyage bills per token; the free tier is 200M tokens. We don't ship the
# Voyage tokenizer offline, so we use a conservative chars/4 proxy (English text
# averages ~4 chars/token; symbol-dense maths prompts run a little under, so
# chars/4 over-estimates slightly — the safe direction for a budget check).
def estimate_tokens(texts: Sequence[str]) -> int:
    """Conservative token estimate (chars / 4) for a batch of texts."""
    return sum(max(1, len(t or "") // 4) for t in texts)


def estimate_cost_usd(n_tokens: int, usd_per_million: float = 0.06) -> float:
    """Rough USD estimate. voyage-3.5 list price is ~$0.06 / 1M tokens; the
    first 200M tokens are free, so on this corpus the realistic spend is $0.
    This figure is the *list* cost ignoring the free tier — an upper bound."""
    return round(n_tokens / 1_000_000 * usd_per_million, 4)
