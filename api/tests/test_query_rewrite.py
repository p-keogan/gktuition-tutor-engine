"""Tests for the AGENT_21 query-rewrite layer.

Covers:

* Pre-check positives — short conceptual framings get rewritten.
* Pre-check negatives — concrete / domain-language queries don't get
  rewritten and the LLM is never called.
* LLM seam injection — the production system prompt is what we send, and
  the user prompt is the verbatim student input.
* LLM-raises → returns original (no exception propagation).
* Feature-flag off → bypass.
* Empty/whitespace query → return as-is.
* End-to-end through ``_run_query`` — retrieval sees the rewritten query;
  the response's ``query`` field still echoes the student's input.

The module reads ``QUERY_REWRITE_ENABLED`` on every call, so each test
explicitly sets / clears it via monkeypatch.
"""
from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.orchestrator import query_rewrite
from api.orchestrator.contract import QueryClass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enabled(monkeypatch) -> None:
    """Turn the layer on for the duration of a test."""
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")


@pytest.fixture
def disabled(monkeypatch) -> None:
    """Turn the layer off explicitly (the suite-wide conftest leaves the
    env var untouched, but tests can still see a stale shell value)."""
    monkeypatch.delenv("QUERY_REWRITE_ENABLED", raising=False)


@pytest.fixture
def fake_llm() -> dict[str, Any]:
    """Wire a fake rewrite-LLM seam that records every call.

    Returns a dict the test can inspect after the call:

    * ``calls``  — list of ``(system_prompt, user_prompt)`` tuples.
    * ``set_response(text)`` — what the seam returns on the next call.
    * ``raise_next(exc)`` — make the seam raise on the next call.
    """
    state: dict[str, Any] = {
        "calls": [],
        "response": "[fake rewrite]",
        "exc": None,
    }

    def fake(system_prompt: str, user_prompt: str) -> str:
        state["calls"].append((system_prompt, user_prompt))
        if state["exc"] is not None:
            raise state["exc"]
        return state["response"]

    state["set_response"] = lambda text: state.__setitem__("response", text)
    state["raise_next"] = lambda exc: state.__setitem__("exc", exc)

    query_rewrite.set_rewrite_llm_caller(fake)
    yield state
    query_rewrite.set_rewrite_llm_caller(None)


# ---------------------------------------------------------------------------
# Pre-check positives — short conceptual queries pass the pre-check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q",
    [
        "explain pensions",
        "explain pin codes",
        "what is a confidence interval",
        "tell me about logarithms",
    ],
)
def test_pre_check_positives_invoke_llm(enabled, fake_llm, q) -> None:
    out = query_rewrite.maybe_rewrite(q, QueryClass.CONCEPT)
    # LLM was called.
    assert len(fake_llm["calls"]) == 1
    sys_prompt, user_prompt = fake_llm["calls"][0]
    # System prompt is verbatim what production uses.
    assert sys_prompt == query_rewrite.REWRITE_SYSTEM_PROMPT
    # User prompt is the student's input, untouched.
    assert user_prompt == q
    # Output is the rewritten string.
    assert out == "[fake rewrite]"


# ---------------------------------------------------------------------------
# Pre-check negatives — concrete / domain-language queries skip the LLM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q",
    [
        # Domain-language operative keyword.
        "prove √2 is irrational",
        # LaTeX inline math.
        "what is $\\int x^2 dx$",
        # Equals sign — equation framing.
        "solve x² + 5x = 6",
        # Concrete maths verb + the unicode superscript glyph.
        "factorise x²-9",
        # Long query — content tokens exceed the cap (8 content tokens
        # after the prefix is stripped).
        "explain how the present value of an annuity is derived from first principles",
    ],
)
def test_pre_check_negatives_skip_llm(enabled, fake_llm, q) -> None:
    out = query_rewrite.maybe_rewrite(q, QueryClass.CONCEPT)
    # LLM was NOT called.
    assert fake_llm["calls"] == []
    # Output is the original query unchanged.
    assert out == q


def test_non_concept_class_skips_llm(enabled, fake_llm) -> None:
    """Even with a conceptual-looking prefix, non-CONCEPT classes pass through.

    The classifier already routed this to a different surface; rewriting
    would change the input that surface sees without an analogous test.
    """
    out = query_rewrite.maybe_rewrite(
        "explain pensions", QueryClass.ANALYTICAL
    )
    assert fake_llm["calls"] == []
    assert out == "explain pensions"


# ---------------------------------------------------------------------------
# Failure modes — exceptions, empty output
# ---------------------------------------------------------------------------


def test_llm_raises_returns_original(enabled, fake_llm) -> None:
    fake_llm["raise_next"](RuntimeError("network blew up"))
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    # LLM was called (and raised); the seam recorded the call.
    assert len(fake_llm["calls"]) == 1
    # Original returned, no exception propagated.
    assert out == "explain pensions"


def test_llm_empty_string_returns_original(enabled, fake_llm) -> None:
    fake_llm["set_response"]("")
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    assert out == "explain pensions"


def test_llm_quoted_output_is_stripped(enabled, fake_llm) -> None:
    """The system prompt forbids quotes but a few completions ship them."""
    fake_llm["set_response"]('"present value of an annuity"')
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    assert out == "present value of an annuity"


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


def test_feature_flag_off_returns_original(disabled, fake_llm) -> None:
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    # Flag off → no LLM call, no rewrite.
    assert fake_llm["calls"] == []
    assert out == "explain pensions"


@pytest.mark.parametrize("value", ["false", "0", "off", "no", ""])
def test_feature_flag_falsy_returns_original(monkeypatch, fake_llm, value) -> None:
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", value)
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    assert fake_llm["calls"] == []
    assert out == "explain pensions"


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_feature_flag_truthy_invokes_llm(monkeypatch, fake_llm, value) -> None:
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", value)
    out = query_rewrite.maybe_rewrite("explain pensions", QueryClass.CONCEPT)
    assert len(fake_llm["calls"]) == 1
    assert out == "[fake rewrite]"


# ---------------------------------------------------------------------------
# Empty / whitespace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("q", ["", "   ", "\n\t"])
def test_empty_whitespace_returns_as_is(enabled, fake_llm, q) -> None:
    out = query_rewrite.maybe_rewrite(q, QueryClass.CONCEPT)
    assert fake_llm["calls"] == []
    assert out == q


# ---------------------------------------------------------------------------
# End-to-end through _run_query — confirms the wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_client(monkeypatch) -> TestClient:
    """Spin up the full FastAPI app with retrieval + synthesis mocked.

    Mirrors the pattern in ``test_query_e2e.py`` so this test exercises
    the same call chain production traffic takes: classify → maybe_rewrite
    → retrieve → synthesize → response assembly.
    """
    import os

    os.environ.setdefault("WP_JWT_SECRET", "dev-only")
    os.environ.setdefault("GKTUITION_ENV", "dev")

    from api.main import build_app
    from api.orchestrator import retriever, synthesizer

    seen_retrieve_args: list[str] = []

    def fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
        # Record the query string retrieval actually saw — this is what
        # the test asserts against.
        seen_retrieve_args.append(query)
        if "TUTOR_SEARCH" in service:
            return [
                {
                    "slug": "financial-maths-8-pensions",
                    "title": "Financial Maths 8 — Pensions",
                    "body": "Present value of an annuity formula...",
                    "score": 0.88,
                    "topic": "financial-maths",
                },
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
    synthesizer.set_cortex_caller(
        lambda model, prompt: "Pensions use the present-value formula. [financial-maths-8-pensions]"
    )
    synthesizer.set_anthropic_caller(
        lambda sysp, userp: "Pensions use the PV formula. [financial-maths-8-pensions]"
    )

    # Wire the rewrite seam to a deterministic fake.
    query_rewrite.set_rewrite_llm_caller(
        lambda sysp, userp: "present value of an annuity for a pension"
    )
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")

    app = build_app()
    tc = TestClient(app)
    tc.seen_retrieve_args = seen_retrieve_args  # type: ignore[attr-defined]
    yield tc

    retriever.set_snowflake_connection(None)
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)
    query_rewrite.set_rewrite_llm_caller(None)


def test_e2e_retrieval_sees_rewritten_query(e2e_client: TestClient) -> None:
    """The full pipeline: student asks "explain pensions", retrieval gets
    the rewritten string, but the response echoes the student's input."""
    payload = {"q": "explain pensions", "tier": "anonymous", "debug": True}
    r = e2e_client.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    # Wire contract: response.query echoes the student's input verbatim.
    assert body["query"] == "explain pensions"

    # Retrieval saw the rewritten string.
    seen = e2e_client.seen_retrieve_args  # type: ignore[attr-defined]
    assert seen, "retrieval was never invoked"
    assert "present value of an annuity" in seen[0]
    assert seen[0] != "explain pensions"

    # debug_info surfaces the rewritten string when debug=True.
    assert body["debug_info"] is not None
    assert (
        body["debug_info"].get("query_rewritten")
        == "present value of an annuity for a pension"
    )


def test_e2e_no_rewrite_when_pre_check_rejects(monkeypatch, e2e_client: TestClient) -> None:
    """A domain-language query passes through unchanged end-to-end."""
    payload = {
        "q": "factorise x²-9",
        "tier": "anonymous",
        "debug": True,
    }
    r = e2e_client.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["query"] == "factorise x²-9"
    seen = e2e_client.seen_retrieve_args  # type: ignore[attr-defined]
    assert seen[0] == "factorise x²-9"

    # No rewrite key in debug_info because no rewrite fired.
    assert body["debug_info"] is not None
    assert "query_rewritten" not in body["debug_info"]
