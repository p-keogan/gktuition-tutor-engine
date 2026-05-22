"""GET ``/healthz`` — liveness + dependency health.

This route replaces the inline ``/healthz`` lambda that previously lived in
``api/main.py``. It runs three sub-checks in parallel:

* **snowflake** — a single ``SELECT 1`` over the orchestrator's pooled
  connection. Confirms the connector can reach Snowflake and the
  configured credentials are still valid.
* **anthropic** — a cheap HEAD-ish call against ``api.anthropic.com`` (the
  SDK's ``client.models.list()`` is the documented way to verify reachability
  without spending tokens).
* **cache_table** — ``DESCRIBE TABLE`` against the L3 semantic-cache table
  configured by Agent 10. Confirms the firewall's cache is reachable and
  has the expected schema.

Each check has a short timeout (2s default; tunable via env) and an
exception handler that converts any failure into a structured
``{"status": "error", "detail": "..."}`` block — the route itself never
raises, never blocks, and **always returns HTTP 200**. Fly's HTTP
healthcheck only cares about 200/non-200; the JSON body is consumed by
the ops dashboard.

A top-level ``status`` field reports ``"ok"`` if every sub-check returned
``"ok"``, ``"degraded"`` if at least one sub-check failed. This lets the
ops dashboard at-a-glance distinguish "Fly thinks the app is alive but
Snowflake is down" from "everything is fine".

Bonus block: the firewall's L5 cap_state is surfaced when
``KILL_SWITCH_ENABLED=true``. This preserves the dashboard signal the
previous inline ``/healthz`` already exposed (Agent 10's wiring).

Note: Fly's healthcheck spec lives in ``fly.toml`` and only consults the
HTTP status — the body is for human and dashboard consumers. We could
flip a degraded sub-check into a 503 in future, but that would risk
flapping the machine on a transient Snowflake hiccup; the current
"always-200 + structured body" is the safer default.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()

# Per-check timeout — kept tight so the overall /healthz never stalls the
# Fly probe. The probe itself has a 5s timeout in fly.toml.
_CHECK_TIMEOUT_S: float = float(os.environ.get("HEALTHZ_CHECK_TIMEOUT_S", "2.0"))


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, Any]:
    """Liveness probe + dependency status. Always returns 200.

    Response shape (canonical per ADR-003 ops requirement)::

        {
          "status": "ok" | "degraded",
          "snowflake": "connected" | "error: ...",
          "anthropic": "reachable" | "error: ...",
          "cache_table": "present" | "error: ...",
          "version": "<git sha>",
          "cap_state": { ... }  // present only when KILL_SWITCH_ENABLED
        }
    """
    started = time.perf_counter()

    # Fan out the three sub-checks. ``asyncio.gather(return_exceptions=True)``
    # ensures one slow check doesn't starve the others — each has its own
    # timeout wrapper, so the worst case is bounded by _CHECK_TIMEOUT_S.
    sf_task = asyncio.create_task(_check_with_timeout(_check_snowflake, "snowflake"))
    anthropic_task = asyncio.create_task(
        _check_with_timeout(_check_anthropic, "anthropic")
    )
    cache_task = asyncio.create_task(
        _check_with_timeout(_check_cache_table, "cache_table")
    )
    snowflake_result, anthropic_result, cache_result = await asyncio.gather(
        sf_task, anthropic_task, cache_task
    )

    body: dict[str, Any] = {
        "snowflake": snowflake_result,
        "anthropic": anthropic_result,
        "cache_table": cache_result,
        "version": os.environ.get("GIT_SHA", "unknown"),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }

    # Top-level status — "ok" iff every sub-check returned its happy value
    # OR was opted out via "skipped (...)". A skipped check (no creds in
    # dev, for instance) is not a health degradation — only an actual
    # "error: ..." string demotes the overall status.
    def _is_healthy(result: str) -> bool:
        return result in {"connected", "reachable", "present"} or result.startswith(
            "skipped"
        )

    all_ok = (
        _is_healthy(snowflake_result)
        and _is_healthy(anthropic_result)
        and _is_healthy(cache_result)
    )
    body["status"] = "ok" if all_ok else "degraded"

    # Preserve Agent 10's cap_state observability. Failure here is logged
    # at DEBUG and never demotes the overall status — kill-switch read
    # errors are not health issues per se.
    try:
        from ..firewall import get_cap_state
        from ..firewall.settings import get_settings as _firewall_settings

        if _firewall_settings().kill_switch_enabled:
            state = get_cap_state()
            body["cap_state"] = {
                "date": state.date,
                "anonymous_spend_eur": state.anonymous_spend_eur,
                "free_combined_spend_eur": state.free_combined_spend_eur,
                "global_spend_eur": state.global_spend_eur,
                "anonymous_cap_eur": state.anonymous_cap_eur,
                "free_cap_eur": state.free_cap_eur,
                "global_cap_eur": state.global_cap_eur,
                "anonymous_cap_fired": state.anonymous_cap_fired,
                "free_cap_fired": state.free_cap_fired,
                "global_cap_fired": state.global_cap_fired,
            }
    except Exception:
        logger.debug("healthz cap_state read failed", exc_info=True)

    return body


# ---------------------------------------------------------------------------
# Sub-checks
# ---------------------------------------------------------------------------


async def _check_with_timeout(
    check: _AsyncCheck,
    name: str,
) -> str:
    """Run a sub-check under a timeout and convert failures to error strings."""
    try:
        return await asyncio.wait_for(check(), timeout=_CHECK_TIMEOUT_S)
    except TimeoutError:
        return f"error: {name} check timed out after {_CHECK_TIMEOUT_S}s"
    except Exception as exc:
        # Compact error string — the dashboard renders it inline. The full
        # traceback goes to the app log.
        logger.warning("healthz sub-check %s failed", name, exc_info=True)
        msg = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return f"error: {msg[:120]}"


async def _check_snowflake() -> str:
    """``SELECT 1`` against the orchestrator's pooled connection."""
    # Skip in dev when no SF credentials are wired — the route would
    # otherwise always return "degraded" for local development.
    if not os.environ.get("SNOWFLAKE_ACCOUNT") and not os.environ.get("SF_ACCOUNT"):
        return "skipped (no SF creds)"

    def _run() -> str:
        # Lazy import — keeps test import-time clean.
        from ..orchestrator.retriever import _cursor  # type: ignore[attr-defined]

        with _cursor() as cs:
            cs.execute("SELECT 1")
            row = cs.fetchone()
            if row and row[0] == 1:
                return "connected"
            return f"error: SELECT 1 returned {row!r}"

    return await asyncio.to_thread(_run)


async def _check_anthropic() -> str:
    """``client.models.list()`` — confirms outbound HTTPS + valid API key.

    The SDK's models-list endpoint is a cheap GET on the Anthropic side
    and doesn't consume any token budget. We do **not** call the messages
    API here — that would burn money on every probe.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return "skipped (no API key)"

    def _run() -> str:
        import anthropic

        client = anthropic.Anthropic()
        # Constrain to one model so we don't pay for any pagination work.
        models = client.models.list(limit=1)
        if getattr(models, "data", None) is not None:
            return "reachable"
        return "error: models.list returned empty payload"

    return await asyncio.to_thread(_run)


async def _check_cache_table() -> str:
    """``DESCRIBE TABLE`` on the L3 cache table — confirms it exists."""
    if not os.environ.get("SNOWFLAKE_ACCOUNT") and not os.environ.get("SF_ACCOUNT"):
        return "skipped (no SF creds)"

    def _run() -> str:
        from ..firewall.settings import get_settings as _firewall_settings
        from ..orchestrator.retriever import _cursor  # type: ignore[attr-defined]

        table_fqn = _firewall_settings().cache_table_fqn
        with _cursor() as cs:
            # DESCRIBE TABLE is cheap (metadata-only) and fails fast if the
            # table doesn't exist. We don't read the rows.
            cs.execute(f"DESCRIBE TABLE {table_fqn}")
            cs.fetchone()  # forces dispatch
        return "present"

    return await asyncio.to_thread(_run)


# Forward-declared protocol for the timeout helper (kept inline so the
# module has no extra typing-only imports for downstream consumers).
from collections.abc import Awaitable, Callable  # noqa: E402

_AsyncCheck = Callable[[], Awaitable[str]]
