"""LanceDB store for the local tutorial index.

Schema mirrors the searchable shape of the Cortex ``TUTOR_SEARCH`` service,
which indexed ``ON title_plus_phrasings, body ATTRIBUTES slug`` — i.e. it
embeds the two text columns *independently* (precision route vs recall route,
per ``create_tutor_search_service.sql``). We mirror that faithfully:

  * ``vec_phrasings`` — embedding of ``title_plus_phrasings`` (precision)
  * ``vec_body``      — embedding of ``body``                  (recall)

At query time (see ``local_retrieval.retrieve``) we search both columns with
the same query vector and merge per-slug by **max** cosine similarity, so a
near-verbatim student-phrasing hit and a paragraph-grounded body hit both get
their fair shot — exactly the behaviour Cortex's multi-field index gives.

``slug`` is the id/attribute carried through retrieval. Raw text is stored so
a future reranker (AGENT_30) can wrap ``retrieve`` without re-reading the
corpus.

LanceDB uses the ``cosine`` distance metric; for L2-normalised vectors the
returned ``_distance`` is ``1 - cosine_similarity``, so
``similarity = 1 - _distance`` lands in ``[0, 1]`` for related text.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from .embedding import EMBED_DIM

TUTOR_TABLE = "tutor"


def _infer_dim(records: list[dict[str, Any]], fallback: int = EMBED_DIM) -> int:
    """Infer the vector dimension from the first record's ``vec_phrasings``.

    Lets the same writer build a 384-dim (bge) or 768-dim (arctic) table from
    the same code path — the schema follows the embedding model, not a constant.
    """
    for r in records:
        vp = r.get("vec_phrasings")
        if vp is not None:
            return len(vp)
    return fallback


def _arrow_schema(dim: int = EMBED_DIM) -> pa.Schema:
    return pa.schema(
        [
            pa.field("slug", pa.string()),
            pa.field("title", pa.string()),
            pa.field("topic", pa.string()),
            pa.field("subtopic", pa.string()),
            pa.field("title_plus_phrasings", pa.string()),
            pa.field("body", pa.string()),
            pa.field("vec_phrasings", pa.list_(pa.float32(), dim)),
            pa.field("vec_body", pa.list_(pa.float32(), dim)),
        ]
    )


def connect(index_dir: Path | str):
    """Open (creating if needed) the LanceDB database at ``index_dir``."""
    p = Path(index_dir)
    p.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(p))


def write_tutor_table(index_dir: Path | str, records: list[dict[str, Any]]):
    """Create / overwrite the tutor table from ``records``.

    Idempotent: ``mode="overwrite"`` drops any existing table so a rebuild
    from the same corpus + model is deterministic and clean. Each record must
    carry the schema keys above (``vec_*`` as float32 lists of length
    ``EMBED_DIM``).
    """
    db = connect(index_dir)
    tbl = db.create_table(
        TUTOR_TABLE,
        data=records,
        schema=_arrow_schema(_infer_dim(records)),
        mode="overwrite",
    )
    return tbl


@functools.lru_cache(maxsize=4)
def _open_cached(index_dir_str: str):
    db = connect(index_dir_str)
    if TUTOR_TABLE not in db.table_names():
        raise FileNotFoundError(
            f"No '{TUTOR_TABLE}' table under {index_dir_str}. "
            "Build it first: python scripts/build_local_index.py"
        )
    return db.open_table(TUTOR_TABLE)


def open_tutor_table(index_dir: Path | str):
    """Open the tutor table for reading. Raises if the index hasn't been built.

    Cached per index dir: the parity harness issues thousands of queries, and
    re-opening the LanceDB connection per call dominates query latency. The
    cache is read-only and process-local — a rebuild starts a fresh process.
    """
    return _open_cached(str(index_dir))
