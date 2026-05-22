"""Shared fixtures for the cost-firewall test suite.

The fixtures here:

* Set ``WP_JWT_SECRET=dev-only`` + ``GKTUITION_ENV=dev`` so the app boots
  cleanly inside the suite (the lifespan handler requires the JWT secret).
* Reset every firewall layer's in-memory state between tests so tests can
  rely on a clean slate.
* Provide a ``firewall_env`` fixture that lets a test enable any subset of
  the layer toggles and reload the cached settings snapshot.
* Provide an ``app`` + ``client`` fixture that builds the FastAPI app with
  the same fake-retriever / fake-synthesiser plumbing as Agent 09's
  ``test_query_e2e.py`` — so we can test the firewall end-to-end without
  hitting Snowflake or Anthropic.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest

os.environ.setdefault("WP_JWT_SECRET", "dev-only")
os.environ.setdefault("GKTUITION_ENV", "dev")

# Reset the firewall settings cache between tests — each test mutates
# os.environ via ``firewall_env`` and needs a fresh snapshot.


def _scrub_firewall_state() -> None:
    """Wipe every in-process firewall datum AND env-var toggle.

    Called both BEFORE each test (so a test starts clean) and AFTER each
    test (so state never leaks into Agent 09's existing tests that don't
    know about the firewall).
    """
    from api.firewall import L1_turnstile, L2_rate_limit, L3_semantic_cache, L4_router, L6_tracing
    from api.firewall import L5_kill_switch as L5
    from api.firewall.settings import reload_settings
    from api.orchestrator import synthesizer

    L1_turnstile.clear_cache()
    L1_turnstile.set_verifier(None)
    L2_rate_limit.clear_buckets()
    L3_semantic_cache.clear_in_memory_cache()
    L3_semantic_cache.set_cache_backends(lookup=None, store=None)
    L4_router.reset()
    # Unwrap the L4 breaker if it was installed during the test.
    if getattr(synthesizer._anthropic_caller, "_l4_wrapped", False):
        synthesizer.set_anthropic_caller(None)
    L5.clear_memory_state()
    L5.set_storage(reader=L5._default_read, incrementer=L5._default_increment)
    L6_tracing.reset_client()

    for k in list(os.environ.keys()):
        if k.startswith(
            (
                "TURNSTILE_",
                "RATE_LIMIT_",
                "FIREWALL_",
                "SEMANTIC_CACHE_",
                "CIRCUIT_BREAKER_",
                "KILL_SWITCH_",
                "LANGFUSE_",
            )
        ):
            del os.environ[k]
    reload_settings()


@pytest.fixture(autouse=True)
def _reset_firewall_state() -> Any:
    _scrub_firewall_state()
    yield
    _scrub_firewall_state()


@pytest.fixture
def firewall_env() -> Any:
    """Helper to set firewall env vars and reload settings.

    Usage::

        firewall_env(TURNSTILE_ENABLED="true", RATE_LIMIT_ENABLED="true")
    """
    from api.firewall.settings import reload_settings

    def _apply(**kw: str) -> None:
        for k, v in kw.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reload_settings()

    return _apply


@pytest.fixture
def fake_retrieval_chunks() -> dict[str, list[dict[str, Any]]]:
    """The fake retrieval results the e2e client returns. Tests can mutate
    this to simulate different retrieval outputs.
    """
    return {
        "TUTOR_SEARCH": [
            {
                "slug": "algebra-1-revision-of-jc-factorising",
                "title": "Algebra 1 — Factorising",
                "body": "Difference of squares: a^2 - b^2 = (a-b)(a+b).",
                "score": 0.92,
                "topic": "algebra",
            }
        ],
        "SOLUTIONS_SEARCH": [
            {
                "part_id": "2024_main_P2_Q5a",
                "topic": "vectors",
                "question_text": "Find the coordinates of B and C.",
                "solution_text": "Using the area formula.",
                "score": 0.88,
                "tutorials_referenced": ["the-line-4-area-of-triangle"],
            }
        ],
        "SUMMARY_SEARCH": [
            {
                "summary_id": "summary-the-line",
                "strand_name": "The Line",
                "body": "Strand cram sheet for The Line.",
                "score": 0.81,
            }
        ],
    }


@pytest.fixture
def app(fake_retrieval_chunks: dict[str, list[dict[str, Any]]]) -> Any:
    """Build the FastAPI app with fake retriever + synthesiser seams wired."""
    from api.main import build_app
    from api.orchestrator import retriever, synthesizer

    def fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
        if "TUTOR_SEARCH" in service:
            return fake_retrieval_chunks["TUTOR_SEARCH"]
        if "SOLUTIONS_SEARCH" in service:
            return fake_retrieval_chunks["SOLUTIONS_SEARCH"]
        if "SUMMARY_SEARCH" in service:
            return fake_retrieval_chunks["SUMMARY_SEARCH"]
        return []

    class _FakeCursor:
        def __init__(self) -> None:
            self._last: list[Any] = []
            self.description: Any = None

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
    synthesizer.set_cortex_caller(
        lambda model, prompt: "Cortex answer [algebra-1-revision-of-jc-factorising]"
    )
    synthesizer.set_anthropic_caller(
        lambda sysp, userp: "Anthropic answer [2024_main_P2_Q5a]"
    )

    app = build_app()
    yield app

    retriever.set_snowflake_connection(None)
    retriever.set_analyst_caller(None)
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)


@pytest.fixture
def client(app: Any) -> Any:
    from fastapi.testclient import TestClient

    return TestClient(app)
