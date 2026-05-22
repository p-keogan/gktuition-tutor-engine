"""
RAW.QUERY_LOG writer for text and image queries.

Agent 09 extension: the canonical text-query schema (per ``api/sql/query_log_table.sql``)
is:

    query_id             VARCHAR
    q                    VARCHAR
    tier                 VARCHAR    -- 'anonymous' | 'authenticated_free' | 'paying'
    query_class          VARCHAR    -- 'concept' | 'solution_lookup' | ...
    model_used           VARCHAR    -- 'cortex.mistral-large2' | 'anthropic.claude-haiku-4-5' | ...
    top_slug             VARCHAR    -- top citation slug, NULL on guardrail
    top_reranker_score   FLOAT
    from_cache           BOOLEAN
    elapsed_ms           INTEGER
    cost_estimate_cents  FLOAT
    extracted_question   VARCHAR    -- NULL except on image-extracted queries
    created_at           TIMESTAMP

Agent 06's image rows reuse this table with the ``query_type`` column set to
``'image'`` and additional image-specific fields (``image_bytes_size``,
``extraction_outcome``). Both writers share one injected writer callable so
production wiring is a single ``set_query_log_writer(...)`` call.

The actual DB writer is injected via ``set_query_log_writer`` so we never
import a DB driver at module-import time and tests stay fast.
"""
from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

QueryLogWriter = Callable[[dict], None | Awaitable[None]]
_writer: QueryLogWriter | None = None


def set_query_log_writer(fn: QueryLogWriter) -> None:
    global _writer
    _writer = fn


async def write_image_query_log_row(
    *,
    request_id: str,
    user_id: str,
    image_bytes_size: int,
    extraction_outcome: str,
    extracted_question: str | None = None,
) -> None:
    row: dict[str, Any] = {
        "request_id": request_id,
        "user_id": user_id,
        "query_type": "image",
        "question_text": extracted_question,
        "image_bytes_size": image_bytes_size,
        "extraction_outcome": extraction_outcome,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if _writer is None:
        # Don't blow up the request if logging isn't wired — degrade gracefully
        # to a structured log line so the request still completes.
        logger.warning(
            "QUERY_LOG writer not configured; row not persisted: %s", row
        )
        return
    try:
        result = _writer(row)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.exception("Failed to write QUERY_LOG row: %s", row)


async def write_text_query_log_row(
    *,
    request_id: str,
    user_id: str,
    q: str,
    tier: str,
    query_class: str,
    model_used: str,
    top_slug: str | None,
    top_reranker_score: float,
    from_cache: bool,
    elapsed_ms: int,
    cost_estimate_cents: float,
    extracted_question: str | None = None,
) -> None:
    """Agent 09: log one row per ``/query`` invocation.

    Schema matches ``api/sql/query_log_table.sql``. The shared injected
    writer (``set_query_log_writer``) is reused — production wires one
    Snowflake writer for both text and image rows.
    """
    row: dict[str, Any] = {
        "query_id": request_id,
        "user_id": user_id,
        "q": q,
        "tier": tier,
        "query_type": "image" if extracted_question is not None else "text",
        "query_class": query_class,
        "model_used": model_used,
        "top_slug": top_slug,
        "top_reranker_score": top_reranker_score,
        "from_cache": from_cache,
        "elapsed_ms": elapsed_ms,
        "cost_estimate_cents": cost_estimate_cents,
        "extracted_question": extracted_question,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if _writer is None:
        logger.warning(
            "QUERY_LOG writer not configured; row not persisted: %s", row
        )
        return
    try:
        result = _writer(row)
        if inspect.isawaitable(result):
            await result
    except Exception:
        logger.exception("Failed to write QUERY_LOG row: %s", row)
