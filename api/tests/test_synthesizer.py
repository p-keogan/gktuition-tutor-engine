"""Synthesizer tests — verifies routing + guardrail."""
from __future__ import annotations

import pytest

from api.orchestrator import synthesizer
from api.orchestrator.contract import (
    Citation,
    QueryClass,
    RetrievalResult,
    RetrievedChunk,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strong_retrieval(query_class: QueryClass) -> RetrievalResult:
    """Build a RetrievalResult that meets the floor."""
    return RetrievalResult(
        query_class=query_class,
        chunks=[
            RetrievedChunk(slug="algebra-1", snippet="factoring lesson", score=0.85),
            RetrievedChunk(slug="algebra-2", snippet="more factoring", score=0.70),
        ],
        citations=[
            Citation(slug="algebra-1", title="Algebra 1", timestamp_seconds=42, score=0.85),
        ],
        top_reranker_score=0.85,
    )


def _weak_retrieval(query_class: QueryClass) -> RetrievalResult:
    """Below the floor — guardrail should fire."""
    return RetrievalResult(
        query_class=query_class,
        chunks=[RetrievedChunk(slug="algebra-1", snippet="weak match", score=0.10)],
        citations=[],
        top_reranker_score=0.10,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_fakes():
    calls: dict[str, list[tuple[str, ...]]] = {"cortex": [], "anthropic": []}

    def fake_cortex(model: str, prompt: str) -> str:
        calls["cortex"].append((model, prompt))
        return f"[cortex] answer to: {prompt.splitlines()[1].removeprefix('Question: ')}"

    def fake_anthropic(system_prompt: str, user_prompt: str) -> str:
        calls["anthropic"].append((system_prompt, user_prompt))
        return f"[anthropic] {user_prompt.splitlines()[0]}"

    synthesizer.set_cortex_caller(fake_cortex)
    synthesizer.set_anthropic_caller(fake_anthropic)
    yield calls
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_concept_with_strong_retrieval_uses_cortex(_wire_fakes) -> None:
    res = synthesizer.synthesize(
        "how do I factorise", _strong_retrieval(QueryClass.CONCEPT)
    )
    assert res.model_used == synthesizer.CORTEX_MODEL
    assert _wire_fakes["cortex"]
    assert not _wire_fakes["anthropic"]


def test_summary_with_strong_retrieval_uses_cortex(_wire_fakes) -> None:
    res = synthesizer.synthesize(
        "cramming the line", _strong_retrieval(QueryClass.SUMMARY_REQUEST)
    )
    assert res.model_used == synthesizer.CORTEX_MODEL


def test_solution_lookup_uses_anthropic(_wire_fakes) -> None:
    res = synthesizer.synthesize(
        "how was 2024 P2 Q5 solved",
        _strong_retrieval(QueryClass.SOLUTION_LOOKUP),
    )
    assert res.model_used == synthesizer.ANTHROPIC_MODEL


def test_ambiguous_uses_anthropic(_wire_fakes) -> None:
    res = synthesizer.synthesize(
        "why has integration grown since 2020",
        _strong_retrieval(QueryClass.AMBIGUOUS),
    )
    assert res.model_used == synthesizer.ANTHROPIC_MODEL


def test_image_extracted_uses_anthropic(_wire_fakes) -> None:
    res = synthesizer.synthesize(
        "how do I factorise",
        _strong_retrieval(QueryClass.IMAGE_EXTRACTED),
    )
    assert res.model_used == synthesizer.ANTHROPIC_MODEL


def test_analytical_tags_analyst_model(_wire_fakes) -> None:
    retrieval = RetrievalResult(
        query_class=QueryClass.ANALYTICAL,
        chunks=[],
        citations=[],
        analyst_rows=[{"year": 2024, "count": 12}],
        analyst_sql="SELECT 1",
        top_reranker_score=0.0,
    )
    res = synthesizer.synthesize("how many", retrieval)
    assert res.model_used == synthesizer.ANALYST_MODEL


def test_weak_retrieval_fires_guardrail(_wire_fakes) -> None:
    res = synthesizer.synthesize("garbled", _weak_retrieval(QueryClass.CONCEPT))
    assert res.answer == synthesizer.GUARDRAIL_ANSWER
    assert res.model_used == synthesizer.NO_MODEL
    # No model called.
    assert not _wire_fakes["cortex"]
    assert not _wire_fakes["anthropic"]


def test_select_citations_empty_on_weak_retrieval() -> None:
    citations = synthesizer.select_citations(_weak_retrieval(QueryClass.CONCEPT))
    assert citations == []


def test_select_citations_returns_top_5_on_strong_retrieval() -> None:
    r = _strong_retrieval(QueryClass.CONCEPT)
    citations = synthesizer.select_citations(r)
    assert len(citations) == len(r.citations)


def test_estimate_cost_cents_models() -> None:
    chunks: list[RetrievedChunk] = []
    assert synthesizer.estimate_cost_cents(synthesizer.CORTEX_MODEL, chunks) == 0.05
    assert synthesizer.estimate_cost_cents(synthesizer.ANTHROPIC_MODEL, chunks) == 0.30
    assert synthesizer.estimate_cost_cents(synthesizer.ANALYST_MODEL, chunks) == 0.10
    assert synthesizer.estimate_cost_cents(synthesizer.NO_MODEL, chunks) == 0.02
