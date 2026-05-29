"""Offline tests for the Voyage hosted-embedding backend (AGENT_33, v4).

These run with NO ``voyageai`` package and NO API key: the live client is
stubbed, so the tests assert the *wiring* that matters — above all the
query/document ``input_type`` asymmetry that produced a false NO-GO for arctic
in AGENT_31 — plus cache determinism and the no-fabrication contract.
"""
from __future__ import annotations

import numpy as np
import pytest

from local_retrieval import voyage_embed as ve


class _FakeClient:
    """Records every ``embed`` call's input_type and returns deterministic
    vectors derived only from the *text* (so the same text → same direction
    regardless of input_type — lets us assert a query matches its own chunk)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def embed(self, texts, model, input_type):  # noqa: A002 - mirror the SDK
        self.calls.append({"model": model, "input_type": input_type, "n": len(texts)})
        embs = []
        for t in texts:
            # A crude but deterministic text→vector: byte histogram over 8 bins.
            v = np.zeros(8, dtype=np.float32)
            for ch in (t or " "):
                v[ord(ch) % 8] += 1.0
            embs.append(v.tolist())

        class _Resp:
            embeddings = embs

        return _Resp()


@pytest.fixture
def fake_client(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(ve, "_get_client", lambda: client)
    return client


def _fresh_cache(tmp_path):
    return ve.VoyageEmbedCache("voyage-3.5", cache_dir=tmp_path).load()


def test_document_path_uses_document_input_type(fake_client, tmp_path):
    cache = _fresh_cache(tmp_path)
    ve.embed_documents(["the line: area of triangle"], cache=cache, allow_api=True)
    assert fake_client.calls, "API should have been hit on a cold cache"
    assert all(c["input_type"] == "document" for c in fake_client.calls)


def test_query_path_uses_query_input_type(fake_client, tmp_path):
    cache = _fresh_cache(tmp_path)
    ve.embed_queries(["find the area of the triangle"], cache=cache, allow_api=True)
    assert fake_client.calls
    assert all(c["input_type"] == "query" for c in fake_client.calls)


def test_query_matches_its_own_chunk_high_similarity(fake_client, tmp_path):
    """The dispatch's 'prove it' sanity: a query and its own chunk land close.

    With correct wiring (both embedded + L2-normalised), identical text yields
    cosine ~1.0. (The live API adds an input_type-specific prompt; this stub
    isolates the *wiring* — the real cross-input_type similarity is captured by
    the operator's build-cache pass and recorded in the delivery note.)
    """
    cache = _fresh_cache(tmp_path)
    text = "de moivre: prove that omega^n = 1"
    d = ve.embed_documents([text], cache=cache, allow_api=True)[0]
    q = ve.embed_queries([text], cache=cache, allow_api=True)[0]
    cos = float(np.dot(d, q))
    assert cos > 0.99
    assert abs(float(np.linalg.norm(d)) - 1.0) < 1e-5  # L2-normalised


def test_cache_hit_is_offline_and_deterministic(fake_client, tmp_path):
    cache = _fresh_cache(tmp_path)
    v1 = ve.embed_documents(["alpha"], cache=cache, allow_api=True)
    cache.save()
    n_calls = len(fake_client.calls)
    # Reload from disk; a second embed must hit cache (no new API call) and match.
    cache2 = _fresh_cache(tmp_path)
    v2 = ve.embed_documents(["alpha"], cache=cache2, allow_api=False)
    assert len(fake_client.calls) == n_calls  # no new spend
    np.testing.assert_array_equal(v1, v2)


def test_cache_miss_without_api_raises(tmp_path):
    cache = _fresh_cache(tmp_path)
    with pytest.raises(KeyError):
        ve.embed_documents(["never-seen"], cache=cache, allow_api=False)


def test_cache_key_distinguishes_input_type():
    assert ve.cache_key("x", "document") != ve.cache_key("x", "query")
    assert ve.cache_key("x", "document") == ve.cache_key("x", "document")


def test_token_estimate_is_conservative():
    assert ve.estimate_tokens(["abcd" * 25]) >= 1
    assert ve.estimate_cost_usd(1_000_000) == pytest.approx(0.06, abs=1e-6)
