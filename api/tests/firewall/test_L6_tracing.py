"""L6 — Langfuse tracing tests.

The Langfuse SDK is not assumed to be installed — the layer is tested by
injecting a fake client and asserting on the trace shape / sensitive-field
exclusion.
"""
from __future__ import annotations

from typing import Any

from api.firewall import L6_tracing as L6


class _FakeLangfuse:
    """Records every trace + span call so tests can assert on them."""

    def __init__(self) -> None:
        self.traces: list[dict[str, Any]] = []

    def trace(self, **kw: Any) -> "_FakeTrace":
        t: dict[str, Any] = {"meta": kw, "spans": []}
        self.traces.append(t)
        return _FakeTrace(t)

    def flush(self) -> None:
        pass


class _FakeTrace:
    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store

    def span(self, **kw: Any) -> None:
        self._store["spans"].append(kw)


def test_trace_shape(firewall_env: Any) -> None:
    firewall_env(
        LANGFUSE_ENABLED="true",
        LANGFUSE_PUBLIC_KEY="pk",
        LANGFUSE_SECRET_KEY="sk",
        LANGFUSE_HOST="http://localhost:3000",
    )
    fake = _FakeLangfuse()
    L6.set_client(fake)

    trace = L6.start_trace(
        request_id="r1",
        user_id="u_42",
        tier="paying",
        query="how do I factorise",
        client_ip="1.2.3.4",
    )
    with L6.span(trace, "classify") as sp:
        sp.output["query_class"] = "concept"
    with L6.span(trace, "retrieve", query_class="concept") as sp:
        sp.output["chunks"] = 4
    with L6.span(trace, "cache_lookup") as sp:
        sp.output["hit"] = False
    with L6.span(trace, "synthesize") as sp:
        sp.output["model_used"] = "cortex.mistral-large2"
    with L6.span(trace, "write_log") as sp:
        sp.output["wrote"] = True
    L6.finish_trace(trace, status_code=200)

    assert len(fake.traces) == 1
    spans = fake.traces[0]["spans"]
    names = [s["name"] for s in spans]
    assert names == ["classify", "retrieve", "cache_lookup", "synthesize", "write_log"]


def test_anonymous_session_id_is_synthetic(firewall_env: Any) -> None:
    """Anonymous traces share a session ID keyed off /24 + day."""
    firewall_env(LANGFUSE_ENABLED="true")
    L6.set_client(_FakeLangfuse())
    t1 = L6.start_trace(
        request_id="r1",
        user_id="anonymous",
        tier="anonymous",
        query="q",
        client_ip="1.2.3.4",
    )
    t2 = L6.start_trace(
        request_id="r2",
        user_id="anonymous",
        tier="anonymous",
        query="q",
        client_ip="1.2.3.55",  # same /24
    )
    t3 = L6.start_trace(
        request_id="r3",
        user_id="anonymous",
        tier="anonymous",
        query="q",
        client_ip="9.9.9.9",
    )
    assert t1.session_id == t2.session_id
    assert t1.session_id != t3.session_id
    assert t1.session_id.startswith("anon:")


def test_authenticated_session_id_uses_user(firewall_env: Any) -> None:
    firewall_env(LANGFUSE_ENABLED="true")
    L6.set_client(_FakeLangfuse())
    t = L6.start_trace(
        request_id="r1",
        user_id="u_42",
        tier="paying",
        query="q",
        client_ip="1.2.3.4",
    )
    assert t.session_id == "user:u_42"


def test_sensitive_fields_not_in_spans(firewall_env: Any) -> None:
    """The trace must NOT carry raw JWT, honeypot value, or dwell delta."""
    firewall_env(LANGFUSE_ENABLED="true")
    fake = _FakeLangfuse()
    L6.set_client(fake)
    trace = L6.start_trace(
        request_id="r1",
        user_id="u_42",
        tier="paying",
        query="q",
        client_ip="1.2.3.4",
    )
    with L6.span(trace, "classify") as sp:
        sp.output["query_class"] = "concept"
    L6.finish_trace(trace, status_code=200)
    blob = repr(fake.traces)
    assert "Bearer" not in blob
    assert "website_url" not in blob
    assert "x-dwell-ms" not in blob
    assert "X-Dwell-Ms" not in blob


def test_disabled_is_passthrough(firewall_env: Any) -> None:
    """With LANGFUSE_ENABLED=false the trace records nothing externally."""
    fake = _FakeLangfuse()
    L6.set_client(fake)  # client is set but not used
    trace = L6.start_trace(
        request_id="r1",
        user_id="u_42",
        tier="paying",
        query="q",
        client_ip="1.2.3.4",
    )
    with L6.span(trace, "classify"):
        pass
    L6.finish_trace(trace, status_code=200)
    # The trace object still records spans locally (so the route layer can
    # introspect them) but we did NOT ship them to the fake client.
    assert fake.traces == []


def test_long_query_is_truncated(firewall_env: Any) -> None:
    """Trace input previews are capped to ~200 chars to bound trace size."""
    firewall_env(LANGFUSE_ENABLED="true")
    L6.set_client(_FakeLangfuse())
    huge = "x" * 5000
    trace = L6.start_trace(
        request_id="r1",
        user_id="u_42",
        tier="paying",
        query=huge,
        client_ip="1.2.3.4",
    )
    assert len(trace.metadata["query"]) <= 201
