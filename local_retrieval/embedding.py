"""Local, offline embedding for the Snowflake-exit Phase 1 spike.

Wraps ``fastembed`` (ONNX, CPU) around ``BAAI/bge-small-en-v1.5`` — a 384-dim,
L2-normalised sentence embedding model that needs **no API key** and runs with
zero network egress after a one-time model download.

The *production* embedding choice (hosted vs local) is a separate Phase-3
decision per ``docs/SNOWFLAKE_EXIT_PLAN.md`` §3; this module is the spike model
and is swappable via the ``model_name`` argument (and the indexer's ``--model``
flag).

Because bge embeddings are already L2-normalised, cosine similarity equals the
dot product, and similarity for topically-related text lands in ``[0, 1]`` —
which is exactly the scale the live ``retriever.RETRIEVAL_FLOOR = 0.30`` gate
expects. See ``local_retrieval.retrieve`` for the score-calibration detail.
"""
from __future__ import annotations

import functools
from collections.abc import Sequence

import numpy as np

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384  # bge-small-en-v1.5


@functools.lru_cache(maxsize=4)
def _get_model(model_name: str):
    """Load (and cache) a fastembed TextEmbedding model.

    Cached per-process so the indexer and ``retrieve()`` don't reload the
    ~130MB ONNX graph on every call. Imported lazily so importing this module
    (e.g. in a test that injects a stub embedder) doesn't force fastembed.
    """
    from fastembed import TextEmbedding  # noqa: PLC0415 (lazy: heavy import)

    return TextEmbedding(model_name=model_name)


def embed_texts(texts: Sequence[str], model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a batch of documents → ``(n, EMBED_DIM)`` float32, L2-normalised.

    Empty / whitespace-only strings are embedded as a single space so the
    model never sees an empty input (fastembed tolerates it, but a space keeps
    the output deterministic across versions).
    """
    cleaned = [t if (t and t.strip()) else " " for t in texts]
    model = _get_model(model_name)
    vecs = np.asarray(list(model.embed(cleaned)), dtype=np.float32)
    return _l2_normalise(vecs)


def embed_query(query: str, model_name: str = DEFAULT_MODEL) -> np.ndarray:
    """Embed a single query string → ``(EMBED_DIM,)`` float32, L2-normalised."""
    return embed_texts([query], model_name=model_name)[0]


def _l2_normalise(vecs: np.ndarray) -> np.ndarray:
    """Defensive re-normalisation. bge output is already unit-norm, but a
    second pass guarantees ``dot == cosine`` regardless of model swap."""
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms = np.where(norms == 0.0, 1.0, norms)
    return (vecs / norms).astype(np.float32)
