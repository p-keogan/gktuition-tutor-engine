"""Offline tests for the hosted reranker adapter (AGENT_33, v4).

Run with NO ``voyageai``/``cohere`` package and NO API key: the vendor call is
stubbed. Asserts the [0,1] calibration contract, order-independent cache keying,
and the no-fabrication (cache-miss-raises) contract.
"""
from __future__ import annotations

import pytest

from local_retrieval import hosted_rerank as hr


def _cands():
    # (slug, document_text)
    return [
        ("the-line-4-area", "area of a triangle given vertices"),
        ("complex-3-demoivre", "de moivre theorem roots of unity"),
        ("algebra-2-quadratics", "factorising quadratics"),
    ]


def test_cache_key_is_order_independent():
    a = hr.rerank_cache_key("rerank-2.5", "e1", ["b", "a", "c"])
    b = hr.rerank_cache_key("rerank-2.5", "e1", ["c", "a", "b"])
    assert a == b
    # but different eval_id / model / set → different key
    assert a != hr.rerank_cache_key("rerank-2.5", "e2", ["a", "b", "c"])
    assert a != hr.rerank_cache_key("rerank-2.5-lite", "e1", ["a", "b", "c"])


def test_cache_miss_without_api_raises(tmp_path):
    cache = hr.RerankCache(tmp_path / "rr.json")
    with pytest.raises(KeyError):
        hr.rerank(
            eval_id="e1", query="area of triangle", candidates=_cands(),
            cache=cache, allow_api=False,
        )


def test_calibration_to_unit_interval_and_order(tmp_path, monkeypatch):
    cache = hr.RerankCache(tmp_path / "rr.json")

    # Stub the vendor call: return raw relevance scores (unsorted) that the
    # adapter must sort + calibrate. Voyage returns relevance_score in [0,1];
    # we hand back arbitrary-scale values to prove calibration is robust.
    def fake_vendor(vendor, query, documents, slugs, *, model):
        raw = {"the-line-4-area": 4.0, "complex-3-demoivre": 1.0,
               "algebra-2-quadratics": 7.5}
        ranked = sorted(((s, raw[s]) for s in slugs), key=lambda kv: kv[1],
                        reverse=True)
        return ranked

    monkeypatch.setattr(hr, "_vendor_rerank", fake_vendor)

    out = hr.rerank(
        eval_id="e1", query="factorise", candidates=_cands(),
        cache=cache, allow_api=True,
    )
    slugs = [s for s, _ in out]
    scores = [sc for _, sc in out]
    # order: highest raw (quadratics) first, lowest (demoivre) last
    assert slugs[0] == "algebra-2-quadratics"
    assert slugs[-1] == "complex-3-demoivre"
    # calibration: all in [0,1], top == 1.0, monotonic non-increasing
    assert all(0.0 <= sc <= 1.0 for sc in scores)
    assert scores[0] == 1.0
    assert scores == sorted(scores, reverse=True)


def test_cache_hit_replays_offline(tmp_path, monkeypatch):
    cache = hr.RerankCache(tmp_path / "rr.json")
    calls = {"n": 0}

    def fake_vendor(vendor, query, documents, slugs, *, model):
        calls["n"] += 1
        return [(s, float(i)) for i, s in enumerate(reversed(slugs))]

    monkeypatch.setattr(hr, "_vendor_rerank", fake_vendor)

    hr.rerank(eval_id="e1", query="q", candidates=_cands(),
              cache=cache, allow_api=True)
    cache.save()
    assert calls["n"] == 1

    # Reload + replay with API disabled — must NOT call the vendor again.
    cache2 = hr.RerankCache(tmp_path / "rr.json")
    out = hr.rerank(eval_id="e1", query="q", candidates=_cands(),
                    cache=cache2, allow_api=False)
    assert calls["n"] == 1
    assert len(out) == len(_cands())


def test_top_k_truncation(tmp_path, monkeypatch):
    cache = hr.RerankCache(tmp_path / "rr.json")
    monkeypatch.setattr(
        hr, "_vendor_rerank",
        lambda v, q, d, s, *, model: [(x, float(i)) for i, x in enumerate(s)],
    )
    out = hr.rerank(eval_id="e1", query="q", candidates=_cands(),
                    cache=cache, allow_api=True, top_k=1)
    assert len(out) == 1
