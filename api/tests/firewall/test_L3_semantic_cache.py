"""L3 — semantic cache tests."""
from __future__ import annotations

import time
from typing import Any

from api.firewall import L3_semantic_cache as L3


def _resp(answer: str = "hello", model: str = "cortex.mistral-large2") -> dict[str, Any]:
    return {
        "query": "q",
        "answer": answer,
        "query_class": "concept",
        "citations": [],
        "retrieved": [],
        "exam_appearances": [],
        "related_learning_work": [],
        "model_used": model,
        "from_cache": False,
        "elapsed_ms": 0,
    }


def test_cache_miss_then_hit(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    # No previous entry → miss.
    assert (
        L3.lookup(
            query="how do I factorise",
            top_k_slugs=["a", "b"],
            model_used="cortex.mistral-large2",
            tier="anonymous",
            query_class="concept",
        )
        is None
    )
    L3.store(
        query="how do I factorise",
        top_k_slugs=["a", "b"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp("Answer A"),
    )
    hit = L3.lookup(
        query="how do I factorise",
        top_k_slugs=["a", "b"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
    )
    assert hit is not None
    assert hit.response_json["answer"] == "Answer A"
    assert hit.model_used == "cortex.mistral-large2"


def test_cache_normalises_query_whitespace_and_symbols(firewall_env: Any) -> None:
    """Two queries that differ only in whitespace/maths-symbols share a row."""
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    L3.store(
        query="solve 5 × 4 + 2",
        top_k_slugs=["x"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(),
    )
    hit = L3.lookup(
        query="  Solve 5 * 4 + 2  ",
        top_k_slugs=["x"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
    )
    assert hit is not None


def test_cache_keys_differ_by_tier(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    L3.store(
        query="q",
        top_k_slugs=["a"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(),
    )
    assert (
        L3.lookup(
            query="q",
            top_k_slugs=["a"],
            model_used="cortex.mistral-large2",
            tier="paying",
            query_class="concept",
        )
        is None
    )


def test_cache_keys_differ_by_model(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    L3.store(
        query="q",
        top_k_slugs=["a"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(model="cortex.mistral-large2"),
    )
    assert (
        L3.lookup(
            query="q",
            top_k_slugs=["a"],
            model_used="anthropic.claude-haiku-4-5",
            tier="anonymous",
            query_class="concept",
        )
        is None
    )


def test_cache_keys_differ_by_top_slugs(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    L3.store(
        query="q",
        top_k_slugs=["a", "b"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(),
    )
    assert (
        L3.lookup(
            query="q",
            top_k_slugs=["c", "d"],
            model_used="cortex.mistral-large2",
            tier="anonymous",
            query_class="concept",
        )
        is None
    )


def test_cache_keys_invariant_under_slug_order(firewall_env: Any) -> None:
    """Top-K slugs are sorted into the key — different orderings collide."""
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    L3.store(
        query="q",
        top_k_slugs=["a", "b"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp("first"),
    )
    hit = L3.lookup(
        query="q",
        top_k_slugs=["b", "a"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
    )
    assert hit is not None
    assert hit.response_json["answer"] == "first"


def test_analytical_bypass(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true")
    # Storing under analytical is a no-op.
    L3.store(
        query="how many integration questions since 2020",
        top_k_slugs=[],
        model_used="cortex.analyst",
        tier="anonymous",
        query_class="analytical",
        response_json=_resp(model="cortex.analyst"),
    )
    # Lookup also bypasses → None.
    assert (
        L3.lookup(
            query="how many integration questions since 2020",
            top_k_slugs=[],
            model_used="cortex.analyst",
            tier="anonymous",
            query_class="analytical",
        )
        is None
    )


def test_stale_eviction(firewall_env: Any) -> None:
    firewall_env(SEMANTIC_CACHE_ENABLED="true", SEMANTIC_CACHE_TTL_SECONDS="1")
    L3.store(
        query="q",
        top_k_slugs=["a"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(),
    )
    time.sleep(1.1)
    assert (
        L3.lookup(
            query="q",
            top_k_slugs=["a"],
            model_used="cortex.mistral-large2",
            tier="anonymous",
            query_class="concept",
        )
        is None
    )


def test_disabled_is_passthrough(firewall_env: Any) -> None:
    # No env vars set → SEMANTIC_CACHE_ENABLED=false.
    L3.store(
        query="q",
        top_k_slugs=["a"],
        model_used="cortex.mistral-large2",
        tier="anonymous",
        query_class="concept",
        response_json=_resp(),
    )
    assert (
        L3.lookup(
            query="q",
            top_k_slugs=["a"],
            model_used="cortex.mistral-large2",
            tier="anonymous",
            query_class="concept",
        )
        is None
    )
