"""Offline tests for the v2 hybrid retriever — Snowflake-exit Phase-0 v2 (AGENT_31).

All tests are offline and key-free. The BM25 path uses a tiny on-the-fly index
(``bm25s`` is pure-python/numpy, no model download). The dense path is stubbed
via monkeypatch so the hybrid tests never load an embedding model — they
exercise the fusion + calibration logic, which is what AGENT_31 added.

Covers the three properties the dispatch calls out:
  1. BM25 returns the planted slug for an exact-token query.
  2. RRF ranks a doc both retrievers return above one only one returns.
  3. The hybrid score is in [0, 1] (top hit normalised to 1.0).
"""
from __future__ import annotations

import pytest

from local_retrieval import bm25_index, hybrid
from local_retrieval.hybrid import retrieve_hybrid, rrf_fuse


def _tiny_rows() -> list[dict]:
    return [
        {"slug": "alpha", "title_plus_phrasings": "factorising quadratics",
         "body": "split the middle term into two factors"},
        {"slug": "beta", "title_plus_phrasings": "the discriminant",
         "body": "b squared minus four a c tells the nature of roots"},
        {"slug": "gamma", "title_plus_phrasings": "de moivre theorem",
         "body": "complex numbers raised to a power using polar form"},
    ]


@pytest.fixture()
def bm25_dir(tmp_path):
    """Build a tiny BM25 index in a temp dir and return its parent index dir."""
    idx = tmp_path / "idx"
    idx.mkdir()
    bm25_index.build_bm25_index(idx, _tiny_rows())
    # The per-process load cache is keyed by dir string; tmp dirs are unique
    # per test, so no cross-test contamination.
    return idx


# ── 1. BM25 exact-token recall ───────────────────────────────────────────────
def test_bm25_returns_planted_slug_for_exact_token(bm25_dir):
    hits = bm25_index.retrieve_bm25("discriminant", 3, index_dir=bm25_dir)
    assert hits, "BM25 returned no hits for an in-vocabulary token"
    assert hits[0][0] == "beta", f"expected 'beta' at rank 1, got {hits}"


def test_bm25_score_calibrated_to_unit_interval(bm25_dir):
    hits = bm25_index.retrieve_bm25("factorising quadratics", 3, index_dir=bm25_dir)
    assert hits[0][0] == "alpha"
    assert all(0.0 <= s <= 1.0 for _, s in hits)
    assert hits[0][1] == pytest.approx(1.0)  # top hit normalised to 1.0


def test_bm25_empty_or_symbol_query_returns_empty(bm25_dir):
    assert bm25_index.retrieve_bm25("   ", 3, index_dir=bm25_dir) == []


# ── 2. RRF fusion ranking property ───────────────────────────────────────────
def test_rrf_ranks_agreed_doc_above_single_list_doc():
    # 'b' appears in both lists; 'a' is rank 1 in only one. RRF should put the
    # doc both retrievers like first, even though 'a' tops a single list.
    fused = rrf_fuse([["a", "b"], ["b", "c"]])
    order = [slug for slug, _ in fused]
    assert order[0] == "b", f"expected agreed doc 'b' first, got {order}"
    assert order.index("b") < order.index("a")


def test_rrf_respects_rank_within_a_list():
    fused = dict(rrf_fuse([["x", "y", "z"]]))
    assert fused["x"] > fused["y"] > fused["z"]


# ── 3. Hybrid end-to-end (dense stubbed) ─────────────────────────────────────
def _stub_dense(monkeypatch, ranked):
    """Stub the dense retriever the hybrid module calls, returning ``ranked``
    slugs with descending cosine-like scores (the hybrid fuser ignores the
    scores and uses rank, but we supply plausible values)."""
    def fake(query, k, *, index_dir=None, model_name=None):  # noqa: ARG001
        return [(s, 0.9 - 0.05 * i) for i, s in enumerate(ranked[:k])]
    monkeypatch.setattr(hybrid, "retrieve_dense", fake)


def test_hybrid_score_in_unit_interval(monkeypatch, bm25_dir):
    _stub_dense(monkeypatch, ["beta", "alpha", "gamma"])
    hits = retrieve_hybrid("discriminant of a quadratic", 3, index_dir=bm25_dir)
    assert hits, "hybrid returned no hits"
    assert all(0.0 <= s <= 1.0 for _, s in hits), hits
    assert hits[0][1] == pytest.approx(1.0)  # top fused hit normalised to 1.0


def test_hybrid_fuses_both_signals(monkeypatch, bm25_dir):
    # Dense ranks alpha #1 and beta #2; BM25 (real, tiny) ranks beta #1 for the
    # token 'discriminant'. The doc both retrievers like (beta, #2+#1) should
    # outrank the doc only dense likes (alpha, #1 only) — RRF rewards
    # cross-retriever agreement over a single list's top rank.
    _stub_dense(monkeypatch, ["alpha", "beta"])
    hits = retrieve_hybrid("discriminant", 3, index_dir=bm25_dir)
    order = [slug for slug, _ in hits]
    assert order[0] == "beta", f"expected agreed doc 'beta' first, got {order}"
    assert order.index("beta") < order.index("alpha")


def test_hybrid_empty_query_returns_empty(monkeypatch, bm25_dir):
    _stub_dense(monkeypatch, ["beta"])
    assert retrieve_hybrid("", 3, index_dir=bm25_dir) == []
    assert retrieve_hybrid("x", 0, index_dir=bm25_dir) == []
