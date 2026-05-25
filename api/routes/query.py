"""``POST /query`` — the FastAPI entrypoint for the tutor.

Pipeline (Agent 09's happy path; Agent 10 wraps cost firewall around this):

1. Decode the JWT → resolve tier (anonymous fallback).
2. Classify the query (deterministic; sub-millisecond).
3. Fan out retrieval to the right Cortex surface(s).
4. Synthesise via the two-tier router (Cortex mistral-large2 / Claude Haiku 4.5).
5. Assemble the ADR-003 JSON contract.
6. Write one row to ``RAW.QUERY_LOG``.

The image_extracted code path also funnels through this endpoint — Agent 06's
``/image_query`` route invokes ``run_text_query`` (registered at startup as
the text-query runner) with the already-extracted text. We tag the response
``query_class = image_extracted`` in that branch.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from ..auth import jwt as _jwt

# We reference _jwt.JWTValidationError and _jwt.decode_or_anonymous via the
# module rather than importing them as names, so that ``importlib.reload()``
# on the jwt module (used by integration/test_jwt_round_trip.py to refresh
# env vars) doesn't leave us holding a stale class identity. If we imported
# the class directly into this module's namespace, a later reload would
# replace the in-module class but leave our captured reference dangling, and
# our ``except`` clause would silently stop matching the freshly-raised
# exception.
from ..orchestrator.classifier import classify, classify_image_extracted
from ..orchestrator.contract import (
    QueryClass,
    QueryRequest,
    QueryResponse,
)
from ..orchestrator.retriever import retrieve
from ..orchestrator.synthesizer import (
    GUARDRAIL_ANSWER,
    augment_with_graphs,
    estimate_cost_cents,
    select_citations,
    synthesize,
)
from ..orchestrator.voice_anchor import infer_strand_from_retrieval
from ..services import query_log

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# /query
# ---------------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: Request, body: QueryRequest) -> QueryResponse:
    """The student's typed question hits this endpoint.

    JWT-derived tier always wins over any ``tier`` value the client sets in
    the request body — we accept the field in the schema for OpenAPI / test
    ergonomics but never trust it on the wire.

    The firewall (Agent 10) wraps the pipeline via ``firewall.wire`` when the
    relevant env vars are set. With all firewall flags disabled, this route
    behaves identically to Agent 09's bare path.
    """
    token = _extract_bearer(request)
    try:
        decoded = _jwt.decode_or_anonymous(token)
    except _jwt.JWTValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid token"},
        ) from exc

    # Re-parse the body as a dict so the firewall's honeypot/anti-spam check
    # can inspect arbitrary client-supplied keys (the Pydantic model strips
    # them out by default).
    raw_body: dict[str, object]
    try:
        raw_body = await request.json()
        if not isinstance(raw_body, dict):
            raw_body = {}
    except Exception:
        raw_body = {}

    from ..firewall.settings import get_settings as _firewall_settings

    fw = _firewall_settings()
    any_firewall_on = any(
        (
            fw.turnstile_enabled,
            fw.rate_limit_enabled,
            fw.cache_enabled,
            fw.breaker_enabled,
            fw.kill_switch_enabled,
            fw.langfuse_enabled,
        )
    )
    if any_firewall_on:
        from ..firewall.wire import run_with_firewall

        return await run_with_firewall(
            request,
            body=raw_body,
            q=body.q.strip(),
            tier=decoded.tier,
            user_id=decoded.user_id,
            debug=body.debug,
            extracted_from_image=False,
        )

    return await _run_query(
        q=body.q.strip(),
        tier=decoded.tier,
        user_id=decoded.user_id,
        debug=body.debug,
        extracted_from_image=False,
    )


# ---------------------------------------------------------------------------
# Internal — used by /query and by /image_query (via query_pipeline.run_text_query)
# ---------------------------------------------------------------------------


async def _run_query(
    *,
    q: str,
    tier: str,
    user_id: str,
    debug: bool,
    extracted_from_image: bool,
    request_id: str | None = None,
) -> QueryResponse:
    """The shared pipeline for typed and image-extracted queries.

    Kept module-level (rather than a method on an `Orchestrator` class) so
    the function is trivially callable from ``query_pipeline.run_text_query``
    and from tests without instantiating a wrapper object.
    """
    started = time.perf_counter()
    request_id = request_id or str(uuid.uuid4())

    # 1. Classify
    if extracted_from_image:
        cls_result = classify_image_extracted(q)
        query_class = QueryClass.IMAGE_EXTRACTED
    else:
        cls_result = classify(q, return_matches=debug)
        query_class = cls_result.query_class

    # 2. Retrieve
    retrieval = await retrieve(q, query_class)

    # 3. Synthesize — runs in a thread because the underlying clients
    # (Snowflake connector / anthropic SDK) are sync. Keeps the event loop
    # free for other concurrent requests.
    synthesis = await asyncio.to_thread(synthesize, q, retrieval)

    # 3b. Visualisation layer (Agent 13 / ADR-005) — independent of the
    # answer text, so a failure here never affects the answer. Also runs
    # in a thread because the deterministic check is cheap but the optional
    # Haiku call is a blocking HTTP request.
    graphs = await asyncio.to_thread(augment_with_graphs, q, retrieval)

    # 4. Assemble response
    citations = select_citations(retrieval)
    # The synth injects the voice anchor into the prompt; we mirror the
    # decision on the wire so the eval harness can score "voice match" per
    # strand. Pure function — no second filesystem read.
    voice_anchor_strand = (
        infer_strand_from_retrieval(retrieval)
        if synthesis.answer != GUARDRAIL_ANSWER
        else None
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    response = QueryResponse(
        query=q,
        answer=synthesis.answer,
        query_class=query_class,
        citations=citations,
        retrieved=retrieval.chunks,
        exam_appearances=retrieval.exam_appearances,
        related_learning_work=retrieval.related_learning_work,
        graphs=graphs,
        model_used=synthesis.model_used,
        from_cache=False,
        voice_anchor_strand=voice_anchor_strand,
        elapsed_ms=elapsed_ms,
        debug_info=_debug_info(retrieval, cls_result.matched_phrases) if debug else None,
    )

    # 5. Log — fire-and-await, don't let log failures fail the request.
    try:
        await query_log.write_text_query_log_row(
            request_id=request_id,
            user_id=user_id,
            q=q,
            tier=tier,
            query_class=query_class.value,
            model_used=synthesis.model_used,
            top_slug=(citations[0].slug if citations else None),
            top_reranker_score=retrieval.top_reranker_score,
            from_cache=False,
            elapsed_ms=elapsed_ms,
            cost_estimate_cents=estimate_cost_cents(synthesis.model_used, retrieval.chunks),
            extracted_question=(q if extracted_from_image else None),
        )
    except Exception:
        logger.exception("query log write failed (non-fatal): request_id=%s", request_id)

    if synthesis.answer == GUARDRAIL_ANSWER:
        logger.info(
            "guardrail fired: q=%r query_class=%s top_score=%.2f",
            q, query_class.value, retrieval.top_reranker_score,
        )

    return response


# Callable Agent 06's /image_query route will register at startup.
async def run_text_query(question: str, *, user_id: str, request_id: str) -> dict[str, Any]:
    """Adapter for ``services.query_pipeline.set_text_query_runner``.

    Image queries arrive here with the maths question already extracted from
    the upload. We tag ``query_class = image_extracted`` and return the
    response as a plain dict so the existing image_query handler can nest it
    under ``rag_response``.
    """
    resp = await _run_query(
        q=question.strip(),
        # image_query has already enforced tier=paying at its own auth gate.
        tier="paying",
        user_id=user_id,
        debug=False,
        extracted_from_image=True,
        request_id=request_id,
    )
    return resp.model_dump()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_bearer(request: Request) -> str | None:
    authz = request.headers.get("authorization") or request.headers.get("Authorization")
    if not authz:
        return None
    parts = authz.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


def _debug_info(retrieval: Any, matched_phrases: tuple[str, ...]) -> dict[str, Any]:
    return {
        "classifier_matches": list(matched_phrases),
        "services_called": retrieval.services_called,
        "top_reranker_score": retrieval.top_reranker_score,
        "analyst_sql": retrieval.analyst_sql,
        "n_chunks": len(retrieval.chunks),
    }
