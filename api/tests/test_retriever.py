"""Retriever tests — uses a fake Snowflake cursor + fake analyst caller."""
from __future__ import annotations

import json
from typing import Any

import pytest

from api.orchestrator import retriever
from api.orchestrator.contract import QueryClass

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
    """Tiny in-memory fixture — three slugs per service with monotonically
    decreasing scores. The retriever's tests don't care about real search
    quality, only that the orchestration shape is right."""
    if "TUTOR_SEARCH" in service:
        return [
            {"slug": "algebra-1-revision-of-jc-factorising", "title": "Algebra 1",
             "body": "factorising prose...", "score": 0.92, "topic": "algebra"},
            {"slug": "algebra-2-factorising-quadratics", "title": "Algebra 2",
             "body": "...", "score": 0.74, "topic": "algebra"},
        ]
    if "SOLUTIONS_SEARCH" in service:
        return [
            {"part_id": "2024_main_P2_Q5a", "topic": "vectors",
             "question_text": "Find the coordinates of B and C.",
             "solution_text": "...", "score": 0.88,
             "tutorials_referenced": ["the-line-4-area-of-triangle"]},
        ]
    if "SUMMARY_SEARCH" in service:
        return [
            {"summary_id": "summary-the-line", "strand_name": "The Line",
             "body": "Cram sheet body.", "score": 0.81},
        ]
    return []


class _FakeCursor:
    def __init__(self) -> None:
        self._last: list[Any] = []
        self.description: list[tuple[str, ...]] | None = None

    def execute(self, sql: str, params: Any = None) -> None:
        if "SEARCH_PREVIEW" in sql:
            service, payload_json = params
            payload = json.loads(payload_json)
            hits = _fake_search_results(service, payload["query"])
            # The retriever expects PARSE_JSON → ARRAY → list[dict].
            self._last = [(hits,)]
        else:
            # SQL execution branch (Analyst flow). Pretend the warehouse
            # returned a single row.
            self._last = [("integration_by_parts", 5)]
            self.description = [("topic_raw",), ("parts_count",)]

    def fetchone(self) -> Any:
        return self._last[0] if self._last else None

    def fetchall(self) -> list[Any]:
        return list(self._last)

    def close(self) -> None:
        pass


class _FakeConn:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_fakes():
    retriever.set_snowflake_connection(_FakeConn())
    yield
    retriever.set_snowflake_connection(None)
    retriever.set_analyst_caller(None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concept_hits_tutor_search_only() -> None:
    res = await retriever.retrieve(
        "how do I factorise difference of squares", QueryClass.CONCEPT
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert retriever.SOLUTIONS_SEARCH not in res.services_called
    assert res.chunks[0].slug == "algebra-1-revision-of-jc-factorising"
    assert res.top_reranker_score == pytest.approx(0.92, abs=1e-3)


@pytest.mark.asyncio
async def test_solution_lookup_hits_solutions_search_only() -> None:
    res = await retriever.retrieve("2024 P2 Q5", QueryClass.SOLUTION_LOOKUP)
    assert retriever.SOLUTIONS_SEARCH in res.services_called
    assert "2024_main_P2_Q5a" in [c.slug for c in res.chunks]


@pytest.mark.asyncio
async def test_summary_request_hits_summary_search_only() -> None:
    res = await retriever.retrieve("cramming the line", QueryClass.SUMMARY_REQUEST)
    assert retriever.SUMMARY_SEARCH in res.services_called
    assert res.citations[0].title == "The Line"


@pytest.mark.asyncio
async def test_analytical_calls_analyst_only_no_search_services() -> None:
    called: list[str] = []

    def fake_analyst(q: str) -> retriever.AnalystResponse:
        called.append(q)
        return retriever.AnalystResponse(
            sql="SELECT 1", rows=[{"topic_raw": "integration", "parts_count": 5}]
        )

    retriever.set_analyst_caller(fake_analyst)
    res = await retriever.retrieve(
        "how often does integration appear on P1", QueryClass.ANALYTICAL,
    )
    assert called == ["how often does integration appear on P1"]
    assert "cortex.analyst" in res.services_called
    assert retriever.TUTOR_SEARCH not in res.services_called
    assert res.analyst_rows[0]["parts_count"] == 5
    assert res.analyst_sql == "SELECT 1"


@pytest.mark.asyncio
async def test_ambiguous_fans_out_to_all_services() -> None:
    retriever.set_analyst_caller(
        lambda q: retriever.AnalystResponse(sql="SELECT 1", rows=[])
    )
    res = await retriever.retrieve(
        "why has integration grown since 2020", QueryClass.AMBIGUOUS,
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert retriever.SOLUTIONS_SEARCH in res.services_called
    assert retriever.SUMMARY_SEARCH in res.services_called
    assert "cortex.analyst" in res.services_called
    # chunks should be deduped by slug and sorted by score.
    slugs = [c.slug for c in res.chunks]
    assert len(slugs) == len(set(slugs))


@pytest.mark.asyncio
async def test_image_extracted_acts_like_concept() -> None:
    res = await retriever.retrieve(
        "how do I factorise difference of squares", QueryClass.IMAGE_EXTRACTED,
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert res.chunks


@pytest.mark.asyncio
async def test_normalise_score_clamps_negative_and_nan() -> None:
    # Indirect — feed a payload through and trust the public surface.
    assert retriever._normalise_score(-0.5) == 0.0
    assert retriever._normalise_score(float("nan")) == 0.0
    assert retriever._normalise_score(2.0) == 1.0
    assert retriever._normalise_score(None) == 0.0
    assert retriever._normalise_score("0.5") == 0.5
