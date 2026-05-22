"""End-to-end /query test — exercises every query_class through TestClient.

Wires fake retrieval + fake synthesizer so the test runs offline. The point
of this test is to verify the route layer correctly invokes the orchestrator
pipeline and serialises the ADR-003 contract — NOT to test the orchestrator
internals (those have their own tests).
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Set the JWT secret BEFORE the app is built — the lifespan handler will
# look it up at startup.
os.environ.setdefault("WP_JWT_SECRET", "dev-only")
os.environ.setdefault("GKTUITION_ENV", "dev")


@pytest.fixture
def client() -> TestClient:
    from api.main import build_app
    from api.orchestrator import retriever, synthesizer

    # Wire fakes — same pattern as test_retriever and test_synthesizer.
    def fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
        if "TUTOR_SEARCH" in service:
            return [
                {"slug": "algebra-1-revision-of-jc-factorising",
                 "title": "Algebra 1 — Factorising",
                 "body": "Difference of squares: a²-b² = (a-b)(a+b)...",
                 "score": 0.92, "topic": "algebra"},
            ]
        if "SOLUTIONS_SEARCH" in service:
            return [
                {"part_id": "2024_main_P2_Q5a", "topic": "vectors",
                 "question_text": "Find the coordinates of B and C.",
                 "solution_text": "Using the area formula...",
                 "score": 0.88,
                 "tutorials_referenced": ["the-line-4-area-of-triangle"]},
            ]
        if "SUMMARY_SEARCH" in service:
            return [
                {"summary_id": "summary-the-line",
                 "strand_name": "The Line",
                 "body": "Strand cram sheet for The Line...",
                 "score": 0.81},
            ]
        return []

    class _FakeCursor:
        def __init__(self) -> None:
            self._last: list[Any] = []
            self.description = None

        def execute(self, sql: str, params: Any = None) -> None:
            if "SEARCH_PREVIEW" in sql:
                service, payload_json = params
                payload = json.loads(payload_json)
                self._last = [(fake_search_results(service, payload["query"]),)]
            else:
                self._last = []
                self.description = []

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

    retriever.set_snowflake_connection(_FakeConn())
    retriever.set_analyst_caller(
        lambda q: retriever.AnalystResponse(
            sql="SELECT COUNT(*) FROM EXAM_PARTS_FLAT",
            rows=[{"parts_count": 12}],
        )
    )
    synthesizer.set_cortex_caller(lambda model, prompt: "Difference of squares factors as (a-b)(a+b). [algebra-1-revision-of-jc-factorising]")
    synthesizer.set_anthropic_caller(lambda sysp, userp: "Walk through the worked solution... [2024_main_P2_Q5a]")

    app = build_app()
    tc = TestClient(app)
    yield tc

    retriever.set_snowflake_connection(None)
    retriever.set_analyst_caller(None)
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)


def _post(client: TestClient, q: str, **kw: Any) -> dict[str, Any]:
    payload = {"q": q, "tier": "anonymous", "debug": False, **kw}
    r = client.post("/query", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_concept_query_routes_to_tutor_search(client: TestClient) -> None:
    body = _post(client, "how do I factorise difference of squares")
    assert body["query_class"] == "concept"
    assert body["model_used"] == "cortex.mistral-large2"
    assert body["citations"]
    assert body["citations"][0]["slug"] == "algebra-1-revision-of-jc-factorising"
    assert body["from_cache"] is False
    assert body["elapsed_ms"] >= 0
    assert "answer" in body


def test_solution_lookup_routes_to_solutions_search(client: TestClient) -> None:
    body = _post(client, "How was 2024 P2 Q5 solved?")
    assert body["query_class"] == "solution_lookup"
    # Hard path → Anthropic.
    assert body["model_used"] == "anthropic.claude-haiku-4-5"
    assert "2024_main_P2_Q5a" in [c["slug"] for c in body["citations"]]


def test_summary_request_routes_to_summary_search(client: TestClient) -> None:
    body = _post(client, "I'm cramming The Line tonight — what do I need to know")
    assert body["query_class"] == "summary_request"
    assert body["model_used"] == "cortex.mistral-large2"
    assert any(c["title"] == "The Line" for c in body["citations"])


def test_analytical_routes_to_cortex_analyst(client: TestClient) -> None:
    body = _post(client, "How often has integration appeared on P1 since 2020?")
    assert body["query_class"] == "analytical"
    assert body["model_used"] == "cortex.analyst"


def test_ambiguous_fans_out(client: TestClient) -> None:
    body = _post(client, "Why has integration grown since 2020?")
    assert body["query_class"] == "ambiguous"
    # Ambiguous → hard path (anthropic).
    assert body["model_used"] == "anthropic.claude-haiku-4-5"


def test_debug_field_populated_when_requested(client: TestClient) -> None:
    body = _post(client, "How often has integration appeared on P1?", debug=True)
    assert body["debug_info"] is not None
    assert "classifier_matches" in body["debug_info"]


def test_empty_query_rejected_by_pydantic(client: TestClient) -> None:
    r = client.post("/query", json={"q": "", "tier": "anonymous"})
    assert r.status_code == 422


def test_healthz(client: TestClient) -> None:
    # Agent 12 enriched /healthz with sub-checks (snowflake, anthropic,
    # cache_table) + a version field. Without credentials, each sub-check
    # reports "skipped (...)" which still rolls up to status="ok".
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    for key in ("snowflake", "anthropic", "cache_table", "version", "elapsed_ms"):
        assert key in body, f"healthz body missing {key}: {body}"


def test_openapi_schema_renders(client: TestClient) -> None:
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    # The contract surfaces query_class as a literal enum on the response.
    paths = schema.get("paths", {})
    assert "/query" in paths


def test_anonymous_tier_default(client: TestClient) -> None:
    """No Authorization header → tier=anonymous, request succeeds."""
    body = _post(client, "how do I factorise difference of squares")
    assert body["query_class"] == "concept"


def test_paying_tier_via_jwt(client: TestClient) -> None:
    from api.auth.jwt import mint_dev_token

    token = mint_dev_token("u_42", "paying")
    r = client.post(
        "/query",
        json={"q": "how do I factorise"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200


def test_malformed_jwt_returns_401(client: TestClient) -> None:
    r = client.post(
        "/query",
        json={"q": "how do I factorise"},
        headers={"Authorization": "Bearer garbage.token.value"},
    )
    assert r.status_code == 401
