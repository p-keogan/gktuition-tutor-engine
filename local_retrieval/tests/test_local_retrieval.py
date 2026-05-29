"""Offline tests for local_retrieval.retrieve.

No network. Embeddings are produced by a deterministic STUB embedder (a tiny
hashing bag-of-words vectoriser) injected in place of fastembed, so the test
neither downloads a model nor hits an API. The stub is L2-normalised, so the
cosine-similarity → [0, 1] calibration path is exercised exactly as in
production.

We build a tiny ~6-chunk LanceDB index from a synthetic fixture corpus, then
assert the contract:
  * an obvious query returns the planted slug at rank 1
  * all scores are in [0, 1]
  * top_k is respected (length + ordering)
  * an empty / whitespace query returns []
"""
from __future__ import annotations

import re

import numpy as np
import pytest

import local_retrieval.core as retrieve_mod
from local_retrieval import store

# ---------------------------------------------------------------------------
# Deterministic, offline stub embedder
# ---------------------------------------------------------------------------

_STUB_DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stub_vector(text: str) -> np.ndarray:
    """Hashing bag-of-words → unit vector. Shared vocabulary ⇒ high cosine."""
    v = np.zeros(_STUB_DIM, dtype=np.float32)
    for tok in _TOKEN_RE.findall((text or "").lower()):
        v[hash(tok) % _STUB_DIM] += 1.0
    n = np.linalg.norm(v)
    if n == 0.0:
        v[0] = 1.0
        n = 1.0
    return (v / n).astype(np.float32)


def _stub_embed_texts(texts, model_name="stub"):
    return np.asarray([_stub_vector(t) for t in texts], dtype=np.float32)


def _stub_embed_query(query, model_name="stub"):
    return _stub_vector(query)


# ---------------------------------------------------------------------------
# Fixture corpus + built index
# ---------------------------------------------------------------------------

_FIXTURE_ROWS = [
    {
        "slug": "circumcentre-of-a-triangle",
        "title": "Circumcentre of a triangle",
        "topic": "coordinate-geometry",
        "subtopic": "circumcentre",
        "title_plus_phrasings": "circumcentre circumcenter perpendicular bisector equidistant vertices",
        "body": "The circumcentre is the point equidistant from the three vertices, found by intersecting perpendicular bisectors.",
    },
    {
        "slug": "bernoulli-trials-binomial",
        "title": "Bernoulli trials and the binomial distribution",
        "topic": "probability",
        "subtopic": "bernoulli",
        "title_plus_phrasings": "bernoulli trials binomial distribution success probability repeated independent",
        "body": "A Bernoulli trial has two outcomes. Repeated independent trials give the binomial distribution.",
    },
    {
        "slug": "present-value-annuity",
        "title": "Present value of an annuity",
        "topic": "financial-maths",
        "subtopic": "annuity",
        "title_plus_phrasings": "present value annuity discount rate payments financial maths",
        "body": "The present value of an annuity discounts a stream of equal future payments to today.",
    },
    {
        "slug": "differentiation-from-first-principles",
        "title": "Differentiation from first principles",
        "topic": "calculus",
        "subtopic": "first-principles",
        "title_plus_phrasings": "differentiation first principles limit derivative slope tangent",
        "body": "Differentiation from first principles uses the limit of a difference quotient.",
    },
    {
        "slug": "complex-numbers-modulus",
        "title": "Modulus of a complex number",
        "topic": "complex-numbers",
        "subtopic": "modulus",
        "title_plus_phrasings": "complex number modulus argand distance origin",
        "body": "The modulus of a complex number is its distance from the origin on the Argand diagram.",
    },
    {
        "slug": "integration-by-parts",
        "title": "Integration by parts",
        "topic": "calculus",
        "subtopic": "integration",
        "title_plus_phrasings": "integration by parts product rule reverse antiderivative",
        "body": "Integration by parts reverses the product rule for differentiation.",
    },
]


@pytest.fixture()
def built_index(tmp_path, monkeypatch):
    """Build a tiny LanceDB index from the fixture rows using the stub embedder."""
    # Patch the embedder everywhere it's used (build path + query path).
    monkeypatch.setattr(retrieve_mod, "embed_query", _stub_embed_query)
    # Build records directly with stub vectors (avoids importing the script).
    phr = _stub_embed_texts([r["title_plus_phrasings"] for r in _FIXTURE_ROWS])
    bod = _stub_embed_texts([r["body"] for r in _FIXTURE_ROWS])
    records = []
    for r, vp, vb in zip(_FIXTURE_ROWS, phr, bod):
        records.append(
            {
                "slug": r["slug"],
                "title": r["title"],
                "topic": r["topic"],
                "subtopic": r["subtopic"],
                "title_plus_phrasings": r["title_plus_phrasings"],
                "body": r["body"],
                "vec_phrasings": vp.tolist(),
                "vec_body": vb.tolist(),
            }
        )
    # Stub schema dim differs from production EMBED_DIM, so build the table
    # with an explicit stub-dim schema rather than store.write_tutor_table.
    import pyarrow as pa

    schema = pa.schema(
        [
            pa.field("slug", pa.string()),
            pa.field("title", pa.string()),
            pa.field("topic", pa.string()),
            pa.field("subtopic", pa.string()),
            pa.field("title_plus_phrasings", pa.string()),
            pa.field("body", pa.string()),
            pa.field("vec_phrasings", pa.list_(pa.float32(), _STUB_DIM)),
            pa.field("vec_body", pa.list_(pa.float32(), _STUB_DIM)),
        ]
    )
    db = store.connect(tmp_path)
    db.create_table(store.TUTOR_TABLE, data=records, schema=schema, mode="overwrite")
    return tmp_path


def test_planted_slug_rank_one(built_index):
    results = retrieve_mod.retrieve(
        "explain the circumcentre perpendicular bisector", top_k=5, index_dir=built_index
    )
    assert results, "expected non-empty results"
    assert results[0][0] == "circumcentre-of-a-triangle"


def test_scores_in_unit_interval_and_sorted(built_index):
    results = retrieve_mod.retrieve(
        "bernoulli trials binomial distribution", top_k=5, index_dir=built_index
    )
    assert results[0][0] == "bernoulli-trials-binomial"
    scores = [s for _, s in results]
    assert all(0.0 <= s <= 1.0 for s in scores), scores
    assert scores == sorted(scores, reverse=True), "results must be best-first"


def test_top_k_respected(built_index):
    for k in (1, 2, 3):
        results = retrieve_mod.retrieve("present value of an annuity", top_k=k, index_dir=built_index)
        assert len(results) == k
    # top_k larger than corpus returns at most corpus size.
    results = retrieve_mod.retrieve("present value of an annuity", top_k=50, index_dir=built_index)
    assert len(results) == len(_FIXTURE_ROWS)


def test_no_duplicate_slugs(built_index):
    results = retrieve_mod.retrieve("integration calculus derivative", top_k=6, index_dir=built_index)
    slugs = [s for s, _ in results]
    assert len(slugs) == len(set(slugs))


@pytest.mark.parametrize("q", ["", "   ", "\n\t"])
def test_empty_query_returns_empty(built_index, q):
    assert retrieve_mod.retrieve(q, top_k=5, index_dir=built_index) == []


def test_nonpositive_top_k_returns_empty(built_index):
    assert retrieve_mod.retrieve("circumcentre", top_k=0, index_dir=built_index) == []
