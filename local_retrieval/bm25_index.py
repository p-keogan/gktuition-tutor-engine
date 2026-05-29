"""BM25 lexical index over the tutorial corpus — Snowflake-exit Phase-0 v2
(AGENT_31).

AGENT_30's NO-GO diagnosis was that the bottleneck is *embedding recall*, and
that the collapse is concentrated in cryptic exam cross-reference rows
(``solution_cross_ref`` recall@20 = 0.752) where a terse prompt like
``"Show that d = 0"`` or ``"ωⁿ = 1, ω ≠ 1 …"`` must align to a tutorial. Dense
embeddings are weak on exactly this surface form; **lexical** retrieval, which
matches literal tokens (variable names, function names, "show that"), is the
lever most likely to recover those rows. This module is that lever, kept cleanly
separable so the ablation can measure BM25 alone vs the hybrid combination.

Implementation: ``bm25s`` (pure-python/numpy BM25, no API key, no network) over
the **same** searchable text the vector index uses (``title_plus_phrasings`` +
``body``) and the **same** chunk set (the canonical ``load_tutorials`` walk), so
this is a fair single-variable ablation against the dense path.

Score calibration
-----------------
Raw BM25 scores are unbounded and corpus-dependent. The shared backend contract
(``SNOWFLAKE_EXIT_DISPATCH.md``) wants a ``[0, 1]`` score comparable to
``RETRIEVAL_FLOOR``. We min-max normalise within each query's returned candidate
set (top hit → 1.0, a floor at 0.0). This is **analysis-only** calibration: the
hybrid fuser ranks on *rank position* (RRF), not on this absolute score, so the
normalisation never feeds the fusion — it only lets the floor / mean-top-1
metrics render for the standalone ``bm25`` backend. Real floor recalibration is
a Phase-2 task and is flagged as such in the report.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# BM25 index lives in a subdirectory of the (model-specific) index dir. BM25 is
# embedding-model-independent, but co-locating keeps one index_dir self-contained.
BM25_SUBDIR = "bm25"
_SLUGS_FILE = "slugs.json"
_STOPWORDS = "en"


def _stemmer():
    """An English Snowball stemmer (PyStemmer). Imported lazily so importing
    this module doesn't force the native extension in tests that stub it."""
    import Stemmer  # noqa: PLC0415

    return Stemmer.Stemmer("english")


def doc_text(row: dict) -> str:
    """The searchable text for one chunk: title_plus_phrasings + body.

    Mirrors the two fields Cortex's TUTOR_SEARCH (and the dense index) use, so
    the lexical and dense paths see the same content — a fair ablation.
    """
    head = str(row.get("title_plus_phrasings") or row.get("title") or "")
    body = str(row.get("body") or "")
    return (head + "\n" + body).strip()


def build_bm25_index(index_dir: Path | str, rows: list[dict]) -> dict:
    """Tokenise + index ``rows`` and save the BM25 index under
    ``index_dir/bm25``. Returns a small summary dict for the delivery note.

    Idempotent: overwrites any existing BM25 index for a clean, deterministic
    rebuild from the same corpus.
    """
    import bm25s  # noqa: PLC0415

    out_dir = Path(index_dir) / BM25_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    slugs = [str(r.get("slug") or "") for r in rows]
    texts = [doc_text(r) for r in rows]

    stemmer = _stemmer()
    corpus_tokens = bm25s.tokenize(
        texts, stopwords=_STOPWORDS, stemmer=stemmer, show_progress=False
    )
    retriever = bm25s.BM25()
    retriever.index(corpus_tokens, show_progress=False)
    retriever.save(str(out_dir))
    (out_dir / _SLUGS_FILE).write_text(json.dumps(slugs), encoding="utf-8")

    return {"bm25_docs": len(slugs), "bm25_dir": str(out_dir)}


# Cache the loaded retriever + slugs per index dir so repeated queries (the
# parity harness runs thousands) don't reload from disk every call.
_CACHE: dict[str, tuple] = {}


def _load(index_dir_str: str):
    if index_dir_str in _CACHE:
        return _CACHE[index_dir_str]
    import bm25s  # noqa: PLC0415

    out_dir = Path(index_dir_str) / BM25_SUBDIR
    if not (out_dir / _SLUGS_FILE).is_file():
        raise FileNotFoundError(
            f"No BM25 index under {out_dir}. Build it first: "
            "python scripts/build_local_index.py --with-bm25"
        )
    retriever = bm25s.BM25.load(str(out_dir), load_corpus=False)
    slugs = json.loads((out_dir / _SLUGS_FILE).read_text(encoding="utf-8"))
    stemmer = _stemmer()
    val = (retriever, slugs, stemmer)
    _CACHE[index_dir_str] = val
    return val


def _default_index_dir() -> str:
    # Mirror core.DEFAULT_INDEX_DIR resolution without importing it (avoid a
    # cycle): repo-root/local_index unless LOCAL_INDEX_DIR overrides.
    repo_root = Path(__file__).resolve().parent.parent
    return os.environ.get("LOCAL_INDEX_DIR", str(repo_root / "local_index"))


def retrieve_bm25_raw(
    query: str,
    top_k: int = 5,
    *,
    index_dir: Path | str | None = None,
) -> list[tuple[str, float]]:
    """Return up to ``top_k`` ``(slug, raw_bm25_score)`` pairs, best-first.

    Raw (un-normalised) scores — used by the hybrid fuser, which only needs the
    *ranking*. Empty / all-stopword query or ``top_k <= 0`` → ``[]``.
    """
    if not query or not query.strip() or top_k <= 0:
        return []
    import bm25s  # noqa: PLC0415

    idx = str(index_dir) if index_dir is not None else _default_index_dir()
    retriever, slugs, stemmer = _load(idx)

    query_tokens = bm25s.tokenize(
        query, stopwords=_STOPWORDS, stemmer=stemmer, show_progress=False
    )
    k = min(top_k, len(slugs))
    if k <= 0:
        return []
    try:
        results, scores = retriever.retrieve(
            query_tokens, k=k, show_progress=False
        )
    except ValueError:
        # All query tokens fell out of the vocabulary (e.g. a pure-symbol
        # prompt) — bm25s can raise on an empty token set. No lexical signal.
        return []

    out: list[tuple[str, float]] = []
    for doc_idx, score in zip(results[0], scores[0]):
        out.append((slugs[int(doc_idx)], float(score)))
    return out


def _clamp01(x: float) -> float:
    if x != x:  # NaN guard
        return 0.0
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def retrieve_bm25(
    query: str,
    top_k: int = 5,
    *,
    index_dir: Path | str | None = None,
) -> list[tuple[str, float]]:
    """Shared-contract BM25 backend: ``(slug, score)`` with ``score`` in
    ``[0, 1]`` (min-max normalised within the returned set; top hit → 1.0).

    The normalisation is analysis-only (lets the floor metric render); the
    hybrid fuser uses :func:`retrieve_bm25_raw` and ranks on position, not on
    this absolute score.
    """
    raw = retrieve_bm25_raw(query, top_k, index_dir=index_dir)
    if not raw:
        return []
    scores = [s for _, s in raw]
    hi, lo = max(scores), min(scores)
    span = hi - lo
    out: list[tuple[str, float]] = []
    for slug, s in raw:
        norm = 1.0 if span <= 0 else _clamp01((s - lo) / span)
        # Keep the top hit at 1.0 and avoid collapsing a single result to 0.0.
        out.append((slug, round(norm if span > 0 else 1.0, 6)))
    return out
