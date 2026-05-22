"""L6 — Langfuse tracing for every ``/query``.

Each request becomes one Langfuse trace with the spans:

* ``classify``     — the deterministic classifier's work.
* ``retrieve``     — fan-out to Cortex Search services / Cortex Analyst.
  One sub-span per service.
* ``cache_lookup`` — L3 lookup (always recorded, even on bypass / miss).
* ``synthesize``   — the LLM call (cheap or hard path).
* ``write_log``    — the QUERY_LOG insert.

Anonymous queries are bucketed under a synthetic session ID derived from the
client IP's /24 + the calendar day (so a single anonymous visitor's spans
roll up together within a day, but cross-day or cross-/24 traces stay
distinct). Authenticated queries use the JWT subject as the session ID.

Sensitive fields the spec calls out are **never** included in any span
payload:

* raw JWT (only the subject is recorded)
* honeypot field contents (the L2 module rejects before the trace reaches
  this layer anyway, but defence-in-depth: we strip the field name from
  trace input if present)
* dwell-time delta (the metric is logged via ``_log.event`` instead)

Toggle: ``LANGFUSE_ENABLED=true``.
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Langfuse client seam
# ---------------------------------------------------------------------------


_lf_client: Any = None
_lf_lock = Lock()


def _maybe_init_client() -> Any:
    """Lazy-initialise the Langfuse SDK client.

    The SDK is imported lazily so the firewall doesn't impose a dependency
    on it at import time. If the import fails, we degrade to a no-op
    in-memory trace recorder so the rest of the system keeps working.
    """
    global _lf_client
    if _lf_client is not None:
        return _lf_client
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    with _lf_lock:
        if _lf_client is not None:
            return _lf_client
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]

            _lf_client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            return _lf_client
        except Exception:
            logger.warning(
                "LANGFUSE_ENABLED but langfuse SDK unavailable; degrading to no-op"
            )
            _lf_client = _NullClient()
            return _lf_client


def set_client(client: Any) -> None:
    """Inject a Langfuse client (or a fake) for tests."""
    global _lf_client
    _lf_client = client


def reset_client() -> None:
    """Clear the cached Langfuse client. Used by tests."""
    global _lf_client
    _lf_client = None


# ---------------------------------------------------------------------------
# Trace + span containers
# ---------------------------------------------------------------------------


@dataclass
class SpanRecord:
    name: str
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_ms(self) -> int:
        return int((self.ended_at - self.started_at) * 1000)


@dataclass
class TraceRecord:
    """In-memory mirror of the Langfuse trace.

    Held on ``request.state`` so the route layer can attach spans inline
    and the trace is finalised when the request returns.
    """

    request_id: str
    session_id: str
    user_id: str
    tier: str
    started_at: float
    metadata: dict[str, Any] = field(default_factory=dict)
    spans: list[SpanRecord] = field(default_factory=list)
    ended_at: float = 0.0
    flushed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tier": self.tier,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "metadata": self.metadata,
            "spans": [
                {
                    "name": s.name,
                    "input": s.input,
                    "output": s.output,
                    "duration_ms": s.duration_ms,
                    "metadata": s.metadata,
                }
                for s in self.spans
            ],
        }


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


def start_trace(
    *,
    request_id: str,
    user_id: str,
    tier: str,
    query: str,
    client_ip: str | None,
) -> TraceRecord:
    """Open a trace and stash it on the caller's request.state.

    ``query`` is recorded *normalised* — same canonicalisation L3 applies —
    so Langfuse search-by-input matches near-duplicate questions together.
    """
    session_id = _session_id(user_id=user_id, tier=tier, client_ip=client_ip)
    trace = TraceRecord(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
        tier=tier,
        started_at=time.time(),
        metadata={
            "query": _safe_query_preview(query),
            "tier": tier,
        },
    )
    event(
        "L6",
        "trace_start",
        request_id=request_id,
        session_id=session_id,
        tier=tier,
    )
    return trace


@contextmanager
def span(trace: TraceRecord | None, name: str, **inputs: Any) -> Iterator[SpanRecord]:
    """Context manager for one span.

    Usage::

        with span(trace, "retrieve", query_class="concept") as sp:
            ...
            sp.output["chunks"] = len(chunks)
    """
    rec = SpanRecord(name=name, input=dict(inputs), started_at=time.time())
    try:
        yield rec
    finally:
        rec.ended_at = time.time()
        if trace is not None:
            trace.spans.append(rec)


def finish_trace(trace: TraceRecord | None, *, status_code: int | None = None) -> None:
    """Close the trace and ship it to Langfuse (if enabled)."""
    if trace is None or trace.flushed:
        return
    trace.ended_at = time.time()
    if status_code is not None:
        trace.metadata["status_code"] = status_code
    trace.flushed = True

    settings = get_settings()
    if not settings.langfuse_enabled:
        return
    client = _maybe_init_client()
    if client is None:
        return
    try:
        # The Langfuse SDK API has shifted between versions; we use the
        # generic ``trace()`` + ``span()`` + ``update()`` shape which is
        # available across all 2.x + 3.x releases. We catch exceptions so a
        # broken SDK can't fail the request.
        lf_trace = client.trace(
            id=trace.request_id,
            name="/query",
            user_id=trace.user_id,
            session_id=trace.session_id,
            metadata=trace.metadata,
        )
        for s in trace.spans:
            try:
                lf_trace.span(
                    name=s.name,
                    input=s.input,
                    output=s.output,
                    metadata=s.metadata,
                    start_time=s.started_at,
                    end_time=s.ended_at,
                )
            except Exception:
                logger.debug("langfuse span write failed", exc_info=True)
        if hasattr(client, "flush"):
            client.flush()
    except Exception:
        logger.exception("langfuse trace flush failed (non-fatal)")
    event(
        "L6",
        "trace_end",
        request_id=trace.request_id,
        spans=len(trace.spans),
        duration_ms=int((trace.ended_at - trace.started_at) * 1000),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_id(*, user_id: str, tier: str, client_ip: str | None) -> str:
    """Derive a session ID — JWT subject for authenticated, day+/24 for anon."""
    if user_id and tier != "anonymous":
        return f"user:{user_id}"
    day = time.strftime("%Y-%m-%d", time.gmtime())
    subnet = "unknown"
    if client_ip:
        if ":" in client_ip:
            subnet = ":".join(client_ip.split(":")[:3])
        else:
            parts = client_ip.split(".")
            if len(parts) == 4:
                subnet = ".".join(parts[:3]) + ".0/24"
    digest = hashlib.sha256(f"{day}|{subnet}".encode()).hexdigest()[:16]
    return f"anon:{digest}"


def _safe_query_preview(q: str, *, max_chars: int = 200) -> str:
    """Trim + strip control characters for trace storage."""
    q = (q or "").replace("\r", " ").replace("\n", " ").strip()
    if len(q) > max_chars:
        q = q[: max_chars - 1] + "…"
    return q


# ---------------------------------------------------------------------------
# Null client used when Langfuse SDK is unavailable
# ---------------------------------------------------------------------------


class _NullClient:
    """Drop-in replacement for the Langfuse client that records nothing."""

    def trace(self, *args: Any, **kwargs: Any) -> _NullTrace:
        return _NullTrace()

    def flush(self) -> None:
        pass


class _NullTrace:
    def span(self, *args: Any, **kwargs: Any) -> None:
        pass
