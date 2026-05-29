"""Local, offline embedding for the Snowflake-exit parity spike.

Wraps ``fastembed`` (ONNX, CPU) around a swappable local sentence-embedding
model that needs **no API key** and runs with zero network egress after a
one-time model download.

Two models are exercised by the parity work:

* ``BAAI/bge-small-en-v1.5`` — 384-dim, the AGENT_29/30 v1 *spike* model.
* ``snowflake/snowflake-arctic-embed-m`` — 768-dim, the AGENT_31 v2 model. This
  is the *family* Cortex's managed embeddings come from, so it is the more
  faithful local stand-in. arctic-embed is an asymmetric (query/document) model:
  queries are embedded with a retrieval instruction prefix, documents without.
  We honour that via ``fastembed``'s ``query_embed`` for queries.

The *production* embedding choice (hosted vs local) remains a separate Phase-3
decision per ``docs/SNOWFLAKE_EXIT_PLAN.md`` §3; both models here are local
spike models, swappable via ``model_name`` (and the indexer's ``--model`` flag).

All models here are L2-normalised on output, so cosine similarity equals the
dot product and similarity for topically-related text lands in ``[0, 1]`` — the
scale the live ``retriever.RETRIEVAL_FLOOR = 0.30`` gate expects. See
``local_retrieval.retrieve`` for the score-calibration detail.
"""
from __future__ import annotations

import functools
from collections.abc import Sequence

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

# Known output dimensions for the models the spike supports. Used by the
# indexer/store to size the Arrow vector columns. Anything not listed falls
# back to a one-shot probe embed (see ``model_dim``).
MODEL_DIMS: dict[str, int] = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-small-en": 384,
    "snowflake/snowflake-arctic-embed-m": 768,
    "snowflake/snowflake-arctic-embed-m-long": 768,
    "snowflake/snowflake-arctic-embed-l": 1024,
    "snowflake/snowflake-arctic-embed-s": 384,
    "snowflake/snowflake-arctic-embed-xs": 384,
}

# Back-compat: modules that imported the old module-level constant still work.
# This is the *default* model's dim; per-model code should call ``model_dim``.
EMBED_DIM = MODEL_DIMS[DEFAULT_MODEL]

# arctic-embed is an *asymmetric* retrieval model: documents are embedded
# verbatim, but queries MUST be prefixed with a retrieval instruction so they
# land in the same region of the space as the documents they should match.
# fastembed 0.3.6 does NOT apply this prefix in ``query_embed`` (it is identical
# to ``embed``), so we apply it ourselves. Skipping the prefix is catastrophic
# for arctic — query/document spaces drift apart and ranking degrades to near
# random (observed: arctic P@1 0.18 without the prefix vs bge's 0.41). The
# string is arctic-embed's documented query prefix.
_ARCTIC_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


def _query_prefix(model_name: str) -> str:
    """The query-side instruction prefix for ``model_name`` (``""`` if none)."""
    return _ARCTIC_QUERY_PREFIX if "arctic-embed" in model_name else ""


def model_dim(model_name: str = DEFAULT_MODEL) -> int:
    """Return the embedding dimension for ``model_name``.

    Uses the static table when known; otherwise probes the model once with a
    trivial document embed (cached, so the cost is paid at most once).
    """
    if model_name in MODEL_DIMS:
        return MODEL_DIMS[model_name]
    return int(embed_texts([" "], model_name=model_name).shape[1])


@functools.lru_cache(maxsize=4)
def _get_model(model_name: str):
    """Load (and cache) a fastembed TextEmbedding model.

    Cached per-process so the indexer and ``retrieve()`` don't reload the
    ONNX graph on every call. Imported lazily so importing this module
    (e.g. in a test that injects a stub embedder) doesn't force fastembed.
    """
    import os  # noqa: PLC0415

    from fastembed import TextEmbedding  # noqa: PLC0415 (lazy: heavy import)

    # Use all available cores for ONNX inference. arctic-embed-m on a single
    # thread is ~50x slower than on 4 cores; the default leaves cores idle.
    return TextEmbedding(model_name=model_name, threads=os.cpu_count() or 1)


# Bounded embedding batch. fastembed defaults to 256, which on a small-RAM box
# spikes memory (and gets OOM-killed) when the inputs are long 512-token bodies.
# A modest batch keeps peak memory flat at a negligible throughput cost.
_EMBED_BATCH = 16


def embed_texts(texts: Sequence[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a batch of **documents** → ``(n, dim)`` float32, L2-normalised.

    Empty / whitespace-only strings are embedded as a single space so the
    model never sees an empty input (fastembed tolerates it, but a space keeps
    the output deterministic across versions).
    """
    cleaned = [t if (t and t.strip()) else " " for t in texts]
    model = _get_model(model_name)
    vecs = np.asarray(
        list(model.embed(cleaned, batch_size=_EMBED_BATCH)), dtype=np.float32
    )
    return _l2_normalise(vecs)


def embed_queries(texts: Sequence[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a batch of **queries** → ``(n, dim)`` float32, L2-normalised.

    For asymmetric models (arctic-embed) we prepend the model's retrieval
    instruction prefix (see ``_ARCTIC_QUERY_PREFIX``) — fastembed 0.3.6's
    ``query_embed`` does *not* do this, so we apply it explicitly via the normal
    document encoder. For symmetric models (bge-small) the prefix is empty, so
    this is equivalent to embedding the raw query — safe across the board.
    """
    prefix = _query_prefix(model_name)
    cleaned = [
        prefix + (t if (t and t.strip()) else " ") for t in texts
    ]
    model = _get_model(model_name)
    vecs = np.asarray(
        list(model.embed(cleaned, batch_size=_EMBED_BATCH)), dtype=np.float32
    )
    return _l2_normalise(vecs)


def embed_query(query: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a single query string → ``(dim,)`` float32, L2-normalised."""
    return embed_queries([query], model_name=model_name)[0]


def _l2_normalise(vecs: np.ndarray) -> np.ndarray:
    """Defensive re-normalisation. Most model outputs are already unit-norm, but
    a second pass guarantees ``dot == cosine`` regardless of model swap."""
    if vecs.ndim == 1:
        vecs = vecs[None, :]
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return (vecs / norms).astype(np.float32)
