"""Tests for the AGENT_24 retrieve-then-rewrite fallback layer.

Covers:

* Fallback pre-check positives — single-word / bare-noun concept queries
  pass (the cases AGENT_21's prefix gate filtered out).
* Fallback pre-check negatives — domain-language queries skip the LLM
  (same exclusions as iter-1).
* LLM seam injection — production system prompt is sent, user prompt is
  the verbatim student input.
* LLM raises → original returned (no exception propagation).
* Flag off → bypass.
* Flag on, but iter-1 also on and iter-1 already rewrote → fallback
  NOT invoked (the ``q_retrieval == q`` guard at the call-site).
* Flag on, first retrieval clears the floor → fallback NOT invoked.
* Flag on, first retrieval below floor + un-rewritten query → fallback
  IS invoked, second retrieval is called, debug surfacing is correct.

The module reads ``QUERY_REWRITE_FALLBACK_ENABLED`` on every call, so
each test explicitly sets / clears it via monkeypatch — the suite-wide
conftest leaves the env var untouched.

End-to-end tests use the same FastAPI ``TestClient`` pattern as
``test_query_rewrite.py`` so the call chain production traffic takes
(classify → maybe_rewrite → retrieve → maybe_rewrite_fallback →
retrieve again → synthesize → response) is exercised in full.
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
def fallback_enabled(monkeypatch) -> None:
    """Turn the fallback layer on for the duration of a test."""
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", "true")


@pytest.fixture
def fallback_disabled(monkeypatch) -> None:
    """Turn the fallback layer off explicitly."""
    monkeypatch.delenv("QUERY_REWRITE_FALLBACK_ENABLED", raising=False)


@pytest.fixture
def iter1_disabled(monkeypatch) -> None:
    """Disable AGENT_21's iter-1 rewrite so tests exercise the fallback
    path in isolation (no iter-1 mutation of ``q_retrieval`` upstream)."""
    monkeypatch.delenv("QUERY_REWRITE_ENABLED", raising=False)


@pytest.fixture
def fake_llm() -> dict[str, Any]:
    """Wire a fake rewrite-LLM seam that records every call.

    Same shape as the fixture in ``test_query_rewrite.py``: both
    ``maybe_rewrite`` and ``maybe_rewrite_fallback`` share the same LLM
    seam, so the recording fixture works for both.
    """
    state: dict[str, Any] = {
        "calls": [],
        "response": "[fake fallback rewrite]",
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
# Pre-check positives — looser-gated queries that iter-1 would reject
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q",
    [
        # The canonical DAY_32 case — single word, slug uses a different
        # lexical form ("circumcircle"). Iter-1's prefix gate skips this.
        "circumcentre",
        # Sibling cases — bare nouns the prefix gate also skips.
        "orthocentre",
        "centroid",
        "bernoulli",
        "pensions",
        # Slightly longer fragment — still within the wider 6-token cap.
        "the orthocentre of a triangle",
    ],
)
def test_fallback_pre_check_positives_invoke_llm(
    fallback_enabled, fake_llm, q
) -> None:
    out = query_rewrite.maybe_rewrite_fallback(q, QueryClass.CONCEPT)
    # LLM was called once.
    assert len(fake_llm["calls"]) == 1
    sys_prompt, user_prompt = fake_llm["calls"][0]
    # System prompt is verbatim what production uses — shared between
    # iter-1 and iter-2 since the actual translation task is identical.
    assert sys_prompt == query_rewrite.REWRITE_SYSTEM_PROMPT
    # User prompt is the student's input, untouched.
    assert user_prompt == q
    # Output is the rewritten string.
    assert out == "[fake fallback rewrite]"


# ---------------------------------------------------------------------------
# Pre-check negatives — domain-language queries still skip the LLM
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "q",
    [
        # Domain-language operative keywords.
        "prove √2 is irrational",
        "differentiate sin(x)",
        "factorise the expression",
        # Equals sign — equation framing.
        "x² + 5x = 6",
        # LaTeX inline math.
        "what is $\\int x^2 dx$",
        # Unicode superscript glyph.
        "x² - 9 expansion",
        # Too long — more than 6 content tokens, even though the prefix
        # gate is dropped the wider cap still rejects sentences.
        "how does the present value of an annuity work in financial mathematics",
    ],
)
def test_fallback_pre_check_negatives_skip_llm(
    fallback_enabled, fake_llm, q
) -> None:
    out = query_rewrite.maybe_rewrite_fallback(q, QueryClass.CONCEPT)
    # LLM was NOT called — domain signals or length cap tripped first.
    assert fake_llm["calls"] == []
    # Output is the original query unchanged.
    assert out == q


def test_fallback_non_concept_class_skips_llm(
    fallback_enabled, fake_llm
) -> None:
    """Non-CONCEPT classes pass through unchanged even with a short query."""
    out = query_rewrite.maybe_rewrite_fallback(
        "circumcentre", QueryClass.ANALYTICAL
    )
    assert fake_llm["calls"] == []
    assert out == "circumcentre"


# ---------------------------------------------------------------------------
# Looser-gate contrast with iter-1 — same query, different gate decisions
# ---------------------------------------------------------------------------


def test_iter1_rejects_what_iter2_accepts(
    fallback_enabled, monkeypatch, fake_llm
) -> None:
    """The canonical DAY_32 case: ``"circumcentre"`` fails iter-1's
    prefix gate but passes iter-2's looser pre-check.

    This is the precise behaviour change AGENT_24 is shipping — without
    this delta the dispatch would be a no-op.
    """
    # Iter-1 ON, iter-2 ON.
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")

    # Iter-1 is a no-op on "circumcentre" — prefix gate doesn't match.
    out_iter1 = query_rewrite.maybe_rewrite("circumcentre", QueryClass.CONCEPT)
    assert out_iter1 == "circumcentre"
    assert fake_llm["calls"] == []  # iter-1 didn't call the LLM

    # Iter-2 (fallback) calls the LLM and returns the rewrite.
    out_iter2 = query_rewrite.maybe_rewrite_fallback(
        "circumcentre", QueryClass.CONCEPT
    )
    assert out_iter2 == "[fake fallback rewrite]"
    assert len(fake_llm["calls"]) == 1


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_fallback_llm_raises_returns_original(
    fallback_enabled, fake_llm
) -> None:
    fake_llm["raise_next"](RuntimeError("network blew up"))
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    # LLM was called (and raised); the seam recorded the call.
    assert len(fake_llm["calls"]) == 1
    # Original returned, no exception propagated.
    assert out == "circumcentre"


def test_fallback_llm_empty_string_returns_original(
    fallback_enabled, fake_llm
) -> None:
    fake_llm["set_response"]("")
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    assert out == "circumcentre"


def test_fallback_llm_quoted_output_is_stripped(
    fallback_enabled, fake_llm
) -> None:
    """The output cleaner is shared between iter-1 and iter-2."""
    fake_llm["set_response"]('"circumcircle of a triangle"')
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    assert out == "circumcircle of a triangle"


# ---------------------------------------------------------------------------
# Feature flag — independent of iter-1's flag
# ---------------------------------------------------------------------------


def test_fallback_flag_off_returns_original(
    fallback_disabled, fake_llm
) -> None:
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    # Flag off → no LLM call, no rewrite.
    assert fake_llm["calls"] == []
    assert out == "circumcentre"


@pytest.mark.parametrize("value", ["false", "0", "off", "no", ""])
def test_fallback_feature_flag_falsy_returns_original(
    monkeypatch, fake_llm, value
) -> None:
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", value)
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    assert fake_llm["calls"] == []
    assert out == "circumcentre"


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_fallback_feature_flag_truthy_invokes_llm(
    monkeypatch, fake_llm, value
) -> None:
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", value)
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    assert len(fake_llm["calls"]) == 1
    assert out == "[fake fallback rewrite]"


def test_iter1_flag_does_not_gate_fallback(
    monkeypatch, fake_llm
) -> None:
    """``QUERY_REWRITE_ENABLED=false`` must NOT block the fallback.

    The two flags are orthogonal — iter-2 can ship while iter-1 is rolled
    back, or vice versa. Regression test for that contract.
    """
    monkeypatch.delenv("QUERY_REWRITE_ENABLED", raising=False)
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", "true")
    out = query_rewrite.maybe_rewrite_fallback("circumcentre", QueryClass.CONCEPT)
    assert len(fake_llm["calls"]) == 1
    assert out == "[fake fallback rewrite]"


# ---------------------------------------------------------------------------
# Empty / whitespace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("q", ["", "   ", "\n\t"])
def test_fallback_empty_whitespace_returns_as_is(
    fallback_enabled, fake_llm, q
) -> None:
    out = query_rewrite.maybe_rewrite_fallback(q, QueryClass.CONCEPT)
    assert fake_llm["calls"] == []
    assert out == q


# ---------------------------------------------------------------------------
# End-to-end through _run_query — confirms call-site wiring
# ---------------------------------------------------------------------------


def _make_e2e_client(
    monkeypatch,
    *,
    first_top_score: float,
    second_top_score: float,
    fallback_rewrite: str = "circumcircle of a triangle",
) -> TestClient:
    """Spin up the FastAPI app with retrieval + synthesis mocked, where
    the first retrieve returns a sub-floor score and the second (after
    fallback) returns an above-floor score.

    Returns a TestClient with a ``seen_retrieve_args`` list attached so
    tests can assert which query strings retrieval saw.
    """
    import os

    os.environ.setdefault("WP_JWT_SECRET", "dev-only")
    os.environ.setdefault("GKTUITION_ENV", "dev")

    from api.main import build_app
    from api.orchestrator import retriever, synthesizer

    seen_retrieve_args: list[str] = []
    # The fake will return a different score for the first vs second
    # retrieve call so the call-site's floor check sees the expected
    # values in sequence.
    call_counter = {"n": 0}

    def fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
        seen_retrieve_args.append(query)
        call_counter["n"] += 1
        # Raw reranker score that the sigmoid will map onto the desired
        # ``top_reranker_score`` for this call. σ(raw) = target ⇒
        # raw = -ln(1/target - 1). For target=0.1 → raw ≈ -2.197; for
        # target=0.5 → raw = 0.0. We approximate by passing values that
        # land cleanly on either side of RETRIEVAL_FLOOR=0.30.
        target = first_top_score if call_counter["n"] == 1 else second_top_score
        # Solve σ(raw) = target — closed form.
        import math
        if target <= 0:
            raw = -10.0
        elif target >= 1:
            raw = 10.0
        else:
            raw = math.log(target / (1.0 - target))
        if "TUTOR_SEARCH" in service:
            return [
                {
                    "slug": "geometry-1-circumcircle-construction",
                    "title": "Geometry 1 — Circumcircle",
                    "body": "Construct the circumcircle of a triangle...",
                    "score": raw,
                    "topic": "geometry",
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
        lambda model, prompt: "Geometry-1 builds the circumcircle. [geometry-1-circumcircle-construction]"
    )
    synthesizer.set_anthropic_caller(
        lambda sysp, userp: "Geometry-1 builds the circumcircle. [geometry-1-circumcircle-construction]"
    )

    # Wire the rewrite seam to a deterministic fake.
    query_rewrite.set_rewrite_llm_caller(lambda sysp, userp: fallback_rewrite)
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", "true")
    # Iter-1 OFF — exercise iter-2 in isolation.
    monkeypatch.delenv("QUERY_REWRITE_ENABLED", raising=False)

    app = build_app()
    tc = TestClient(app)
    tc.seen_retrieve_args = seen_retrieve_args  # type: ignore[attr-defined]
    tc.call_counter = call_counter  # type: ignore[attr-defined]
    return tc


@pytest.fixture(autouse=True)
def _reset_seams() -> None:
    """Ensure each test starts with clean retriever / synthesizer seams.

    Without this a previous test's e2e_client teardown could leak a fake
    cursor into the next test. The fixture is autouse so every test in
    the module gets the reset cheap.
    """
    yield
    from api.orchestrator import retriever, synthesizer
    retriever.set_snowflake_connection(None)
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)
    query_rewrite.set_rewrite_llm_caller(None)


def test_e2e_fallback_fires_on_first_retrieval_miss(monkeypatch) -> None:
    """First retrieve scores below the floor → fallback rewrites →
    second retrieve sees the rewritten query and clears the floor.

    Asserts: retrieve was called twice, the second call carried the
    rewritten query, debug_info surfaces ``fallback_triggered=True`` and
    ``query_rewritten_fallback`` set to the LLM's output, and the
    response's ``query`` field still echoes the student's input.
    """
    tc = _make_e2e_client(
        monkeypatch,
        first_top_score=0.10,
        second_top_score=0.55,
    )

    payload = {"q": "circumcentre", "tier": "anonymous", "debug": True}
    r = tc.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    # Wire contract — response.query echoes student's input verbatim.
    assert body["query"] == "circumcentre"

    # Retrieval was called twice — first with the original, then with the
    # fallback rewrite.
    seen = tc.seen_retrieve_args  # type: ignore[attr-defined]
    assert len(seen) == 2, f"expected 2 retrieve calls, got {seen}"
    assert seen[0] == "circumcentre"
    assert seen[1] == "circumcircle of a triangle"

    # debug_info surfaces both fields.
    assert body["debug_info"] is not None
    assert body["debug_info"]["fallback_triggered"] is True
    assert (
        body["debug_info"]["query_rewritten_fallback"]
        == "circumcircle of a triangle"
    )
    # Iter-1 didn't fire — the iter-1 field stays absent.
    assert "query_rewritten" not in body["debug_info"]


def test_e2e_fallback_not_fired_when_first_retrieval_clears_floor(
    monkeypatch,
) -> None:
    """First retrieve already clears the floor → fallback does not
    fire, LLM is never called, only one retrieve call."""
    tc = _make_e2e_client(
        monkeypatch,
        first_top_score=0.55,
        second_top_score=0.55,  # irrelevant; fallback shouldn't fire
    )

    payload = {"q": "circumcentre", "tier": "anonymous", "debug": True}
    r = tc.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    seen = tc.seen_retrieve_args  # type: ignore[attr-defined]
    assert len(seen) == 1, f"expected 1 retrieve call, got {seen}"

    assert body["debug_info"]["fallback_triggered"] is False
    assert "query_rewritten_fallback" not in body["debug_info"]


def test_e2e_fallback_not_fired_when_iter1_already_rewrote(monkeypatch) -> None:
    """Iter-1 already rewrote (``q_retrieval != q``) → fallback does NOT
    fire even if the first retrieval missed the floor.

    Regression test for the ``q_retrieval == q`` guard. Without it, a
    query that iter-1 rewrote but still scored sub-floor would consume
    two LLM round-trips on the same request.
    """
    tc = _make_e2e_client(
        monkeypatch,
        first_top_score=0.10,  # below floor
        second_top_score=0.55,
    )

    # Turn iter-1 on; the fixture wires the same LLM seam for both,
    # but iter-1 will mutate q_retrieval before retrieve fires.
    monkeypatch.setenv("QUERY_REWRITE_ENABLED", "true")
    # The shared LLM seam will return the same string for both iter-1
    # and iter-2 calls, but the call-site guard should mean only one
    # rewrite happens (iter-1) regardless of the fact that the score
    # remained below the floor.
    payload = {"q": "explain pensions", "tier": "anonymous", "debug": True}
    r = tc.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    seen = tc.seen_retrieve_args  # type: ignore[attr-defined]
    # Only one retrieve — iter-1 rewrote upstream, fallback's
    # ``q_retrieval == q`` guard refuses to fire a second LLM call.
    assert len(seen) == 1, f"expected 1 retrieve call, got {seen}"

    assert body["debug_info"]["fallback_triggered"] is False
    assert "query_rewritten_fallback" not in body["debug_info"]
    # Iter-1 DID fire — it's the field that should be set.
    assert "query_rewritten" in body["debug_info"]


def test_e2e_fallback_disabled_by_flag(monkeypatch) -> None:
    """``QUERY_REWRITE_FALLBACK_ENABLED=false`` → fallback bypassed even
    on a retrieval miss."""
    tc = _make_e2e_client(
        monkeypatch,
        first_top_score=0.10,
        second_top_score=0.55,
    )
    monkeypatch.setenv("QUERY_REWRITE_FALLBACK_ENABLED", "false")

    payload = {"q": "circumcentre", "tier": "anonymous", "debug": True}
    r = tc.post("/query", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()

    seen = tc.seen_retrieve_args  # type: ignore[attr-defined]
    assert len(seen) == 1, f"expected 1 retrieve call, got {seen}"

    assert body["debug_info"]["fallback_triggered"] is False
    assert "query_rewritten_fallback" not in body["debug_info"]
