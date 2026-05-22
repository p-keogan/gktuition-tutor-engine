"""FastAPI application entrypoint.

Mounts:

* ``POST /query``        — the text query endpoint (Agent 09).
* ``POST /image_query``  — the multimodal endpoint (Agent 06).
* ``GET  /healthz``      — liveness probe.

CORS is scoped to ``https://gktuition.ie`` only (dev origins added when
``GKTUITION_ENV=dev``). The structured query log writes to
``GKTUITION_TUTOR.RAW.QUERY_LOG`` via the seam in ``services.query_log``.

Run locally::

    uvicorn api.main:app --reload --port 8000

Required env vars at boot:

* ``WP_JWT_SECRET``       — HS256 signing secret (in dev: ``dev-only``)
* ``SNOWFLAKE_ACCOUNT``   — for Cortex Search + Analyst + Complete calls
* ``SNOWFLAKE_USER``      — Snowflake user
* ``SNOWFLAKE_PASSWORD``  *or* ``SNOWFLAKE_PRIVATE_KEY_PATH``
* ``ANTHROPIC_API_KEY``   — Claude Haiku 4.5 for the hard path

In dev all of these can be missing — the orchestrator returns the
"I don't know" guardrail because retrieval fails (the test suite uses
injected fakes for all four seams).
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.health import router as health_router
from .routes.image_query import router as image_query_router
from .routes.query import router as query_router
from .routes.query import run_text_query
from .services import auth as svc_auth
from .services import query_pipeline

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — wire the dependency seams at startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _wire_seams()
    logger.info(
        "GKTuition tutor API ready (env=%s)",
        os.environ.get("GKTUITION_ENV", "prod"),
    )
    yield
    # No teardown needed — the Snowflake connection pool is process-lived.


def _wire_seams() -> None:
    """Wire the dependency-injection seams the routes + services expose.

    Done at startup so import order is stable and the seams are deterministic
    in tests (which override them in their own fixtures).
    """
    # 1. JWT decoder used by /image_query (services/auth.py seam).
    from .auth.jwt import decode_jwt_payload_compat
    svc_auth.set_jwt_decoder(decode_jwt_payload_compat)

    # 2. Register the text-query runner so /image_query can hand off the
    # extracted question to /query's pipeline.
    query_pipeline.set_text_query_runner(run_text_query)

    # 3. Production Snowflake QUERY_LOG writer would be wired here. In dev
    # the writer is left at its default (warning log) and rows are not
    # persisted; tests inject a list-capturing writer.
    _maybe_wire_production_query_log()

    # 4. Production Anthropic client for /image_query would be wired here.
    _maybe_wire_anthropic_client_for_image_query()

    # 5. Cost firewall — install the L4 circuit breaker around the
    # Anthropic seam. The other layers (L1, L2, L3, L5, L6) are pure
    # request-time checks and don't need startup wiring beyond what's
    # already in place. Toggles via env vars; see firewall.settings.
    from .firewall.wire import install_firewall_at_startup
    install_firewall_at_startup()


def _maybe_wire_production_query_log() -> None:
    """Install the batched Snowflake log sink, if SF creds are set.

    Agent 12 replaces the previous per-row INSERT writer with the batched
    sink in ``api/observability/snowflake_log_sink.py`` — see ADR-003 on
    why observability must never block request handling. The sink owns
    its own buffer + background flush thread and is enabled by
    ``SNOWFLAKE_LOG_SINK_ENABLED=true`` (set in ``fly.toml``).

    Skipped silently in dev (no SF creds, or env var unset).
    """
    # Dual-prefix read: SNOWFLAKE_ACCOUNT (canonical) OR SF_ACCOUNT (the
    # name scripts/setup_fly_secrets.sh pushes). Matches the same
    # defensive pattern used in api/routes/health.py and the orchestrator's
    # retriever helper.
    if (
        not (
            os.environ.get("SNOWFLAKE_ACCOUNT")
            or os.environ.get("SF_ACCOUNT")
        )
        or os.environ.get("GKTUITION_DISABLE_QUERY_LOG")
    ):
        return
    try:
        from .observability.snowflake_log_sink import install_default_sink
    except Exception:
        logger.exception("failed to import snowflake_log_sink; query_log disabled")
        return

    install_default_sink()


def _maybe_wire_anthropic_client_for_image_query() -> None:
    """Wire ``anthropic.Anthropic()`` for the /image_query route.

    Skipped if no API key is set; the image_query route will then 502 if
    invoked, which is the right behaviour for misconfiguration.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        import anthropic

        from .routes import image_query as image_query_module

        image_query_module.set_anthropic_client(anthropic.Anthropic())
    except Exception:
        logger.exception("failed to wire anthropic client for /image_query")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def build_app() -> FastAPI:
    """Construct the FastAPI app. Kept separate so tests can build their own."""
    app = FastAPI(
        title="GKTuition AI Tutor",
        version="0.9.0",
        description=(
            "Single HTTP entrypoint for the GKTuition LCHL Maths tutor. "
            "Routes text and image queries through a deterministic intent "
            "classifier and fan-out across Snowflake Cortex Search + Cortex "
            "Analyst, then synthesises a grounded answer via the two-tier "
            "LLM router defined in ADR-003."
        ),
        lifespan=lifespan,
    )

    allowed_origins = _allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    app.include_router(query_router, tags=["query"])
    app.include_router(image_query_router, tags=["query"])
    # ``/healthz`` is owned by ``routes.health`` (Agent 12). It performs
    # parallel sub-checks (snowflake, anthropic, cache_table) and includes
    # the ``cap_state`` block previously rendered inline here — strictly
    # additive to the contract.
    app.include_router(health_router, tags=["meta"])

    return app


def _allowed_origins() -> list[str]:
    env = os.environ.get("GKTUITION_ENV", "prod")
    if env == "dev":
        return [
            "https://gktuition.ie",
            "https://www.gktuition.ie",
            "http://localhost:3000",
            "http://localhost:5173",  # vite default
            "http://127.0.0.1:3000",
        ]
    return ["https://gktuition.ie", "https://www.gktuition.ie"]


app = build_app()
