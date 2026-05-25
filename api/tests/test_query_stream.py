"""Tests for ``POST /query/stream`` — AGENT_17 SSE streaming endpoint.

Covers the three required cases from the AGENT_17 dispatch:

1. A concept query produces ≥1 ``token`` event + ≥1 ``citation`` event +
   exactly 1 ``done`` event.
2. A query whose retrieval falls below ``RETRIEVAL_FLOOR`` produces the
   guardrail fallback as a single ``token`` event + 1 ``done`` event
   with ``model_used="(none)"``.
3. The cache-hit path (firewall on) returns the cached response as a
   single ``token`` event + ``done`` event with ``from_cache=True``.

Plus a fast sanity check that the SSE wire format is well-formed
(``event:`` + ``data:`` + blank line per record) and a check that the
existing non-streaming ``/query`` contract is unchanged.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Set the JWT secret BEFORE the app is built — same as test_query_e2e.
os.environ.setdefault("WP_JWT_SECRET", "dev-only")
os.environ.setdefault("GKTUITION_ENV", "dev")


# ---------------------------------------------------------------------------
# Shared fakes (mirrors test_query_e2e patterns)
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    from api.main import build_app
    from api.orchestrator import retriever, synthesizer

    def fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
        # Drive the floor branch via a magic phrase — no results = guardrail.
        if "below floor" in query.lower():
            return []
        if "TUTOR_SEARCH" in service:
            return [
                {
                    "slug": "algebra-1-revision-of-jc-factorising",
                    "title": "Algebra 1 — Factorising",
                    "body": "Difference of squares: a²-b² = (a-b)(a+b)...",
                    "score": 0.92,
                    "topic": "algebra",
                },
            ]
        if "SOLUTIONS_SEARCH" in service:
            return [
                {
                    "part_id": "2024_main_P2_Q5a",
                    "topic": "vectors",
                    "question_text": "Find the coordinates of B and C.",
                    "solution_text": "Using the area formula...",
                    "score": 0.88,
                    "tutorials_referenced": ["the-line-4-area-of-triangle"],
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
    retriever.set_analyst_caller(
        lambda q: retriever.AnalystResponse(
            sql="SELECT COUNT(*) FROM EXAM_PARTS_FLAT",
            rows=[{"parts_count": 12}],
        )
    )

    # Cheap-path caller — Cortex doesn't stream, so the streaming endpoint
    # chunks this string word-by-word.
    synthesizer.set_cortex_caller(
        lambda model, prompt: (
            "To factorise a difference of squares, you use the formula "
            "[algebra-1-revision-of-jc-factorising]."
        )
    )

    # Hard-path streaming caller — yields deterministic deltas.
    def fake_anthropic_stream(sysp: str, userp: str):
        yield from ["In ", "2024 ", "P2 ", "Q5, ", "the ", "candidate..."]

    synthesizer.set_anthropic_caller(
        lambda sysp, userp: "Walk through the worked solution... [2024_main_P2_Q5a]"
    )
    synthesizer.set_anthropic_stream_caller(fake_anthropic_stream)

    app = build_app()
    tc = TestClient(app)
    yield tc

    retriever.set_snowflake_connection(None)
    retriever.set_analyst_caller(None)
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)
    synthesizer.set_anthropic_stream_caller(None)


# ---------------------------------------------------------------------------
# SSE parsing helper
# ---------------------------------------------------------------------------


def _parse_sse(text: str) -> list[dict[str, Any]]:
    """Parse an SSE response body into a list of {event, data} dicts.

    Records are blank-line delimited per the SSE spec. ``data`` is parsed
    as JSON (the streaming endpoint always emits compact one-line JSON).
    """
    records: list[dict[str, Any]] = []
    text = text.replace("\r\n", "\n")
    for raw_record in text.split("\n\n"):
        record = raw_record.strip("\n")
        if not record:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in record.split("\n"):
            if not line or line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            if value.startswith(" "):
                value = value[1:]
            if field == "event":
                event_name = value
            elif field == "data":
                data_lines.append(value)
        if not data_lines:
            continue
        records.append(
            {"event": event_name, "data": json.loads("\n".join(data_lines))}
        )
    return records


def _stream(client: TestClient, q: str, **kw: Any) -> list[dict[str, Any]]:
    payload = {"q": q, "tier": "anonymous", "debug": False, **kw}
    r = client.post("/query/stream", json=payload)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream"), r.headers
    # TestClient buffers the full body; that's fine — we want to assert on
    # the complete record set, not on the streaming behaviour (which is a
    # transport concern verified by the live curl -N check).
    return _parse_sse(r.text)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_streaming_concept_emits_tokens_citations_and_one_done(
    client: TestClient,
) -> None:
    """Case 1 from the AGENT_17 dispatch.

    A concept query routes to the cheap path. The synthesiser chunks the
    Cortex output word-by-word; we expect multiple ``token`` events,
    ≥1 ``citation`` event, and exactly one ``done`` event.
    """
    records = _stream(client, "how do I factorise difference of squares")
    tokens = [r for r in records if r["event"] == "token"]
    citations = [r for r in records if r["event"] == "citation"]
    dones = [r for r in records if r["event"] == "done"]

    assert len(tokens) >= 1
    assert len(citations) >= 1
    assert len(dones) == 1

    # The concatenation of token texts reconstructs the answer.
    full = "".join(t["data"]["text"] for t in tokens)
    assert "factorise" in full
    assert "[algebra-1-revision-of-jc-factorising]" in full

    # done payload carries the cheap-path model + Phase 2 fields.
    done = dones[0]["data"]
    assert done["model_used"] == "cortex.mistral-large2"
    assert done["from_cache"] is False
    assert done["query_class"] == "concept"
    assert done["query"] == "how do I factorise difference of squares"
    assert done["elapsed_ms"] >= 0
    # voice_anchor_strand is allowed to be either None (corpus absent in
    # tests) or a real strand name; both are valid in a dev env without
    # the corpus mounted.
    assert "voice_anchor_strand" in done

    # First citation matches the top retrieval.
    assert citations[0]["data"]["slug"] == "algebra-1-revision-of-jc-factorising"


def test_streaming_below_floor_emits_guardrail_single_token(
    client: TestClient,
) -> None:
    """Case 2 from the AGENT_17 dispatch.

    When retrieval falls below ``RETRIEVAL_FLOOR``, the synthesiser short-
    circuits to the "I'm not sure" guardrail. The streaming endpoint must
    emit exactly one ``token`` (the guardrail string) + exactly one
    ``done`` with ``model_used="(none)"``. No citations.
    """
    from api.orchestrator.synthesizer import GUARDRAIL_ANSWER

    records = _stream(client, "below floor synthetic query")
    tokens = [r for r in records if r["event"] == "token"]
    citations = [r for r in records if r["event"] == "citation"]
    dones = [r for r in records if r["event"] == "done"]

    assert len(tokens) == 1
    assert tokens[0]["data"]["text"] == GUARDRAIL_ANSWER
    assert citations == []
    assert len(dones) == 1
    assert dones[0]["data"]["model_used"] == "(none)"
    # voice_anchor_strand is suppressed on the guardrail path.
    assert dones[0]["data"]["voice_anchor_strand"] is None


def test_streaming_cache_hit_passthrough(client: TestClient, monkeypatch) -> None:
    """Case 3 from the AGENT_17 dispatch — firewall-on cache-hit path.

    When the firewall is enabled, ``/query/stream`` short-circuits through
    ``run_with_firewall`` (which serves the cached ``QueryResponse``) and
    re-emits the response as a single ``token`` + citations + ``done``
    with ``from_cache=True``. The point of this test is not to exercise
    the cache itself (covered by the firewall suite) but to verify the
    streaming endpoint's adapter shape.
    """
    from types import SimpleNamespace

    from api.firewall import settings as fw_settings
    from api.firewall import wire as fw_wire
    from api.orchestrator.contract import Citation, QueryClass, QueryResponse

    # Force the cache_enabled flag so the streaming route takes the
    # firewall short-circuit path. FirewallSettings is a frozen dataclass,
    # so we monkeypatch get_settings() to return a fresh fake snapshot
    # with the cache flag flipped.
    fake_fw = SimpleNamespace(
        turnstile_enabled=False,
        rate_limit_enabled=False,
        cache_enabled=True,
        breaker_enabled=False,
        kill_switch_enabled=False,
        langfuse_enabled=False,
    )
    monkeypatch.setattr(fw_settings, "get_settings", lambda: fake_fw)

    cached = QueryResponse(
        query="cached q",
        answer="Cached answer text.",
        query_class=QueryClass.CONCEPT,
        citations=[
            Citation(
                slug="cached-slug", title="Cached Title", timestamp_seconds=None,
                score=0.88,
            ),
        ],
        retrieved=[],
        exam_appearances=[],
        related_learning_work=[],
        graphs=[],
        model_used="cortex.mistral-large2",
        from_cache=True,
        voice_anchor_strand="LCHL_Algebra",
        elapsed_ms=7,
    )

    async def fake_firewall_run(*args, **kwargs):
        return cached

    monkeypatch.setattr(fw_wire, "run_with_firewall", fake_firewall_run)

    records = _stream(client, "cached q")
    tokens = [r for r in records if r["event"] == "token"]
    citations = [r for r in records if r["event"] == "citation"]
    dones = [r for r in records if r["event"] == "done"]

    assert len(tokens) == 1
    assert tokens[0]["data"]["text"] == "Cached answer text."
    assert len(citations) == 1
    assert citations[0]["data"]["slug"] == "cached-slug"
    assert len(dones) == 1
    assert dones[0]["data"]["from_cache"] is True
    assert dones[0]["data"]["model_used"] == "cortex.mistral-large2"
    assert dones[0]["data"]["voice_anchor_strand"] == "LCHL_Algebra"


# ---------------------------------------------------------------------------
# Wire-format + contract preservation
# ---------------------------------------------------------------------------


def test_sse_wire_format_records_are_well_formed(client: TestClient) -> None:
    """The raw response must look like SSE — ``event:`` + ``data:`` + blank line.

    Future debugging shortcut: if this test breaks but the others pass,
    the wire format has drifted away from the spec even though the parsed
    records still happen to be JSON-decodable.
    """
    r = client.post(
        "/query/stream",
        json={"q": "how do I factorise difference of squares", "tier": "anonymous"},
    )
    assert r.status_code == 200
    text = r.text
    assert "event: token" in text
    assert "event: done" in text
    # Blank line as the record separator.
    assert "\n\n" in text


def test_non_streaming_query_contract_unchanged(client: TestClient) -> None:
    """``/query`` (non-streaming) must continue returning a JSON QueryResponse.

    Pinned here so the AGENT_17 changes don't accidentally rewire the
    existing endpoint. The full /query contract is covered by
    test_query_e2e.py — this is a one-call sanity check.
    """
    r = client.post(
        "/query",
        json={"q": "how do I factorise difference of squares", "tier": "anonymous"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["query_class"] == "concept"
    assert body["citations"]


def test_streaming_hard_path_emits_anthropic_deltas(client: TestClient) -> None:
    """Solution-lookup routes to the hard path, which uses the streaming
    Anthropic seam (the test fixture's fake yields 6 deterministic chunks).
    Expect 6 ``token`` events with the matching text + ≥1 citation + done.
    """
    records = _stream(client, "How was 2024 P2 Q5 solved?")
    tokens = [r for r in records if r["event"] == "token"]
    dones = [r for r in records if r["event"] == "done"]

    assert len(tokens) == 6  # exactly the chunks our fake yields
    assert "".join(t["data"]["text"] for t in tokens).startswith("In 2024 P2")
    assert dones[0]["data"]["model_used"] == "anthropic.claude-haiku-4-5"
