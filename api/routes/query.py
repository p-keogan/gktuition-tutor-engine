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
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

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
from ..orchestrator.query_rewrite import maybe_rewrite, maybe_rewrite_fallback
from ..orchestrator.retriever import RETRIEVAL_FLOOR, retrieve
from ..orchestrator.synthesizer import (
    GUARDRAIL_ANSWER,
    NO_MODEL,
    StreamEvent,
    augment_with_graphs,
    estimate_cost_cents,
    select_citations,
    slug_anchor_override,
    synthesize,
    synthesize_stream,
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
# /query/stream — AGENT_17 SSE streaming endpoint
# ---------------------------------------------------------------------------
#
# Design notes (see AGENT_17_DELIVERY.md for the full rationale):
#
# * Non-streaming ``/query`` contract is unchanged — both endpoints coexist.
#   CI smoke + eval harness keep using JSON; the widget switches to the
#   stream and falls back to JSON if EventSource is unavailable.
# * Auth is identical to ``/query`` (JWT decoded → tier; anonymous fallback).
# * When the firewall is enabled the stream endpoint short-circuits through
#   the existing non-streaming firewall path and re-emits the resulting
#   ``QueryResponse`` as a single ``token`` event + ``done`` — that
#   preserves L2 rate-limit / L3 cache / L4 breaker / L5 kill-switch
#   guarantees without re-implementing the firewall in streaming-shaped
#   form. Cache hits in particular are sub-10 ms; streaming them adds
#   latency without UX benefit.
# * On the streaming-direct path (firewall off OR firewall flags absent
#   in dev), classify + retrieve run in the request thread; the synthesiser
#   generator is consumed inside the StreamingResponse, with a thread pool
#   used to hop across sync boundaries (the Cortex + Anthropic clients are
#   blocking).
# * L6 observability: the query-log row is written when the stream closes
#   (not at request start) so ``elapsed_ms`` reflects end-to-end latency
#   including the time the client spent reading.


@router.post("/query/stream")
async def query_stream_endpoint(request: Request, body: QueryRequest) -> StreamingResponse:
    """SSE-streaming sibling of ``POST /query``.

    Returns ``text/event-stream``. Emits ``event: token`` / ``event: citation``
    / ``event: done`` records (in that order). The widget consumes the
    stream via ``EventSource`` for a "first ink in 1-2s" UX even on a 20s
    cold-start warehouse.

    See module docstring for the design notes.
    """
    token = _extract_bearer(request)
    try:
        decoded = _jwt.decode_or_anonymous(token)
    except _jwt.JWTValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid token"},
        ) from exc

    q = body.q.strip()
    tier = decoded.tier
    user_id = decoded.user_id
    debug = body.debug

    # Firewall short-circuit: if any firewall layer is enabled we fall
    # back to the non-streaming pipeline (so L2/L3/L4/L5 stay enforced)
    # and emit the resulting QueryResponse as a single token + done. The
    # cost is no progressive fill for firewall-enabled deployments; the
    # benefit is no re-implementation of the firewall on the stream path.
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
        # Re-read the raw body so the firewall's honeypot/anti-spam checks
        # can inspect arbitrary client-supplied keys, exactly like
        # ``/query`` does.
        raw_body: dict[str, object]
        try:
            raw_body = await request.json()
            if not isinstance(raw_body, dict):
                raw_body = {}
        except Exception:
            raw_body = {}

        from ..firewall.wire import run_with_firewall

        resp = await run_with_firewall(
            request,
            body=raw_body,
            q=q,
            tier=tier,
            user_id=user_id,
            debug=debug,
            extracted_from_image=False,
        )
        return StreamingResponse(
            _wrap_full_response_as_sse(resp),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )

    return StreamingResponse(
        _stream_pipeline(
            q=q,
            tier=tier,
            user_id=user_id,
            debug=debug,
        ),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


def _sse_headers() -> dict[str, str]:
    """SSE-friendly response headers.

    * ``Cache-Control: no-cache`` — proxies must not buffer the stream.
    * ``X-Accel-Buffering: no`` — nginx / Fly's proxy honour this and
      forward chunks immediately rather than batching for compression.
    * ``Connection: keep-alive`` — explicit; Starlette already does this
      for ``StreamingResponse`` but belt-and-braces.
    """
    return {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }


def _format_sse(event: str, data: dict[str, Any]) -> bytes:
    """Encode one ``StreamEvent`` as an SSE record.

    Format (per the SSE spec):

        event: <event_name>\\n
        data: <json>\\n
        \\n

    JSON is compact (no spaces) so a single line of ``data:`` is enough;
    we don't have to worry about multi-line continuation.
    """
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _stream_pipeline(
    *,
    q: str,
    tier: str,
    user_id: str,
    debug: bool,
) -> AsyncIterator[bytes]:
    """The streaming-direct pipeline.

    Mirrors :func:`_run_query` stage-by-stage but emits SSE bytes instead
    of returning a ``QueryResponse``. The synthesiser generator is
    consumed inside ``asyncio.to_thread`` per chunk because the underlying
    Cortex/Anthropic clients are sync — we don't want to block the event
    loop while the cheap path's ``time.sleep`` cadence loop runs.
    """
    started = time.perf_counter()
    request_id = str(uuid.uuid4())

    # 1. Classify
    cls_result = classify(q, return_matches=debug)
    query_class = cls_result.query_class

    # 1b. Query rewrite (AGENT_21) — same hook as ``_run_query``. The
    # ``done`` event's ``query`` field still carries the student's input;
    # only retrieval + synthesis see the rewritten form.
    q_retrieval = maybe_rewrite(q, query_class)
    if q_retrieval != q:
        logger.info(
            "stream query rewrite fired: original=%r rewritten=%r",
            q,
            q_retrieval,
        )

    # 2. Retrieve
    retrieval = await retrieve(q_retrieval, query_class)

    # 2b. AGENT_24 retrieve-then-rewrite fallback — same hook as
    # ``_run_query`` so the streaming-direct path stays behaviourally
    # equivalent to the non-streaming path on a retrieval miss. Hard
    # cap of one fallback per query; the ``q_retrieval == q`` guard
    # avoids firing back-to-back LLM calls when iter-1 already
    # rewrote.
    if retrieval.top_reranker_score < RETRIEVAL_FLOOR and q_retrieval == q:
        first_top = retrieval.top_reranker_score
        q_fallback_candidate = maybe_rewrite_fallback(q, query_class)
        if q_fallback_candidate != q:
            retrieval = await retrieve(q_fallback_candidate, query_class)
            q_retrieval = q_fallback_candidate
            logger.info(
                "stream query rewrite fallback fired: original=%r "
                "fallback=%r first_top=%.3f second_top=%.3f",
                q,
                q_fallback_candidate,
                first_top,
                retrieval.top_reranker_score,
            )

    # 3. Synthesize — streaming. The synthesiser generator is sync (calls
    # the blocking Cortex/Anthropic clients); we drain it on a thread so
    # the event loop stays responsive. Each StreamEvent is converted to
    # SSE bytes here.
    model_used = NO_MODEL
    stream_iter = synthesize_stream(q_retrieval, retrieval)

    # We need to peek the final ``done`` event so the route can augment it
    # with elapsed_ms/voice_anchor_strand before serialising. Strategy:
    # iterate, encode token/citation as we go, and hold the done event
    # back; emit our augmented done at the end.
    def _next_event() -> StreamEvent | None:
        try:
            return next(stream_iter)
        except StopIteration:
            return None

    while True:
        ev = await asyncio.to_thread(_next_event)
        if ev is None:
            break
        if ev.event == "done":
            # Capture the synthesiser's model_used; we emit our own
            # augmented done event below so we can attach elapsed_ms +
            # voice_anchor_strand.
            model_used = str(ev.data.get("model_used", NO_MODEL))
            continue
        yield _format_sse(ev.event, ev.data)

    # Voice-anchor strand for the eval harness — only meaningful when an
    # answer was actually produced (i.e. not the guardrail). Same logic as
    # the non-streaming route.
    voice_anchor_strand = (
        infer_strand_from_retrieval(retrieval) if model_used != NO_MODEL else None
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    done_payload: dict[str, Any] = {
        "query": q,
        "query_class": query_class.value,
        "model_used": model_used,
        "from_cache": False,
        "voice_anchor_strand": voice_anchor_strand,
        "elapsed_ms": elapsed_ms,
        # Curated exam appearances for the cited tutorials — the widget renders
        # the most recent couple as a "seen in exams" block under the answer.
        "exam_appearances": [a.model_dump() for a in retrieval.exam_appearances],
    }
    yield _format_sse("done", done_payload)

    # 4. L6 observability — write the query log row AFTER the stream
    # closes so elapsed_ms reflects end-to-end latency. Fire-and-await,
    # log failures non-fatally exactly like the non-streaming path.
    citations = select_citations(retrieval)
    try:
        await query_log.write_text_query_log_row(
            request_id=request_id,
            user_id=user_id,
            q=q,
            tier=tier,
            query_class=query_class.value,
            model_used=model_used,
            top_slug=(citations[0].slug if citations else None),
            top_reranker_score=retrieval.top_reranker_score,
            from_cache=False,
            elapsed_ms=elapsed_ms,
            cost_estimate_cents=estimate_cost_cents(model_used, retrieval.chunks),
            extracted_question=None,
        )
    except Exception:
        logger.exception(
            "stream query log write failed (non-fatal): request_id=%s", request_id
        )

    if model_used == NO_MODEL:
        logger.info(
            "stream guardrail fired: q=%r query_class=%s top_score=%.2f",
            q,
            query_class.value,
            retrieval.top_reranker_score,
        )


async def _wrap_full_response_as_sse(resp: QueryResponse) -> AsyncIterator[bytes]:
    """Re-emit a non-streaming ``QueryResponse`` as a 1-token-plus-citations-plus-done SSE stream.

    Used when the firewall is enabled (cache hits, rate-limited requests,
    breaker-open requests, etc.). The widget can't tell from the wire
    that this wasn't progressively streamed — the data shape is identical.
    """
    if resp.answer:
        yield _format_sse("token", {"text": resp.answer})

    for c in resp.citations:
        yield _format_sse(
            "citation",
            {
                "slug": c.slug,
                "title": c.title,
                "timestamp_seconds": c.timestamp_seconds,
                "score": c.score,
            },
        )

    yield _format_sse(
        "done",
        {
            "query": resp.query,
            "query_class": resp.query_class.value,
            "model_used": resp.model_used,
            "from_cache": resp.from_cache,
            "voice_anchor_strand": resp.voice_anchor_strand,
            "elapsed_ms": resp.elapsed_ms,
            "exam_appearances": [a.model_dump() for a in resp.exam_appearances],
        },
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

    # 1b. Query rewrite (AGENT_21) — translates conceptual "explain X" framings
    # into the corpus's domain language. No-op (returns ``q`` unchanged) when
    # the feature flag is off, when the deterministic pre-check rejects, or
    # for any non-concept route. The response's ``query`` field is still
    # bound from the original ``q`` below — the wire contract stays "echo the
    # student's input"; only retrieval and synthesis see the rewritten form.
    q_retrieval = maybe_rewrite(q, query_class)
    # Capture iter-1's outcome BEFORE the AGENT_24 fallback below can mutate
    # ``q_retrieval``, so the debug surfacing in step 4 can attribute each
    # rewrite to the right path without conflating them.
    q_rewritten_iter1: str | None = q_retrieval if q_retrieval != q else None
    if q_retrieval != q:
        logger.info(
            "query rewrite fired: original=%r rewritten=%r", q, q_retrieval
        )

    # 2. Retrieve
    retrieval = await retrieve(q_retrieval, query_class)

    # 2b. Retrieve-then-rewrite fallback (AGENT_24) — when the first
    # attempt missed the floor AND iter-1 hadn't already rewritten the
    # query, give the LLM a shot at translating into corpus domain
    # language and retry retrieval once. The ``q_retrieval == q`` guard
    # prevents firing back-to-back LLM calls on the same query when
    # AGENT_21's iter-1 path already ran. Hard cap of one fallback per
    # query — if the second retrieval still misses, the guardrail fires
    # downstream exactly as before.
    fallback_triggered = False
    q_fallback: str | None = None
    if retrieval.top_reranker_score < RETRIEVAL_FLOOR and q_retrieval == q:
        first_top = retrieval.top_reranker_score
        q_fallback_candidate = maybe_rewrite_fallback(q, query_class)
        if q_fallback_candidate != q:
            retrieval = await retrieve(q_fallback_candidate, query_class)
            q_retrieval = q_fallback_candidate
            q_fallback = q_fallback_candidate
            fallback_triggered = True
            logger.info(
                "query rewrite fallback fired: original=%r fallback=%r "
                "first_top=%.3f second_top=%.3f",
                q,
                q_fallback_candidate,
                first_top,
                retrieval.top_reranker_score,
            )

    # 3. Synthesize — runs in a thread because the underlying clients
    # (Snowflake connector / anthropic SDK) are sync. Keeps the event loop
    # free for other concurrent requests. We pass the rewritten string so
    # the synthesiser's evidence-bound prompt is consistent with what
    # retrieval saw; the response's ``query`` field still echoes the
    # student's input.
    synthesis = await asyncio.to_thread(synthesize, q_retrieval, retrieval)

    # 3b. Visualisation layer (Agent 13 / ADR-005) — independent of the
    # answer text, so a failure here never affects the answer. Also runs
    # in a thread because the deterministic check is cheap but the optional
    # Haiku call is a blocking HTTP request.
    graphs = await asyncio.to_thread(augment_with_graphs, q_retrieval, retrieval)

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
    # AGENT_22: mirror the synthesiser's slug-anchor decision into debug_info
    # so the paper trail surfaces on ``debug=True`` requests. Recomputed
    # rather than threaded out of the synth — the helper is a pure function
    # of ``(retrieval, query)`` and the recompute is microseconds.
    slug_anchor_fired = (
        slug_anchor_override(retrieval, q_retrieval)
        if synthesis.answer != GUARDRAIL_ANSWER
        else False
    )
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
        debug_info=_debug_info(
            retrieval,
            cls_result.matched_phrases,
            query_rewritten=q_rewritten_iter1,
            query_rewritten_fallback=q_fallback,
            fallback_triggered=fallback_triggered,
            slug_anchor_override_fired=slug_anchor_fired,
        )
        if debug
        else None,
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


def _debug_info(
    retrieval: Any,
    matched_phrases: tuple[str, ...],
    *,
    query_rewritten: str | None = None,
    query_rewritten_fallback: str | None = None,
    fallback_triggered: bool = False,
    slug_anchor_override_fired: bool = False,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "classifier_matches": list(matched_phrases),
        "services_called": retrieval.services_called,
        "top_reranker_score": retrieval.top_reranker_score,
        "analyst_sql": retrieval.analyst_sql,
        "n_chunks": len(retrieval.chunks),
        # AGENT_22 — present unconditionally so a caller can grep for the
        # field across a run of queries to see how often the override fired.
        "slug_anchor_override_fired": slug_anchor_override_fired,
        # AGENT_24 — present unconditionally for the same reason; False is
        # the no-fire signal. Pair this with ``query_rewritten_fallback`` to
        # see what the LLM produced.
        "fallback_triggered": fallback_triggered,
    }
    # Only present when AGENT_21's rewrite actually fired — None / absent
    # is the "no rewrite" signal. Mirrors the matched_phrases pattern: the
    # field exists in debug_info only when there's content to attach.
    if query_rewritten is not None:
        info["query_rewritten"] = query_rewritten
    # AGENT_24 — same presence convention as ``query_rewritten``: only
    # surfaced when the fallback actually rewrote.
    if query_rewritten_fallback is not None:
        info["query_rewritten_fallback"] = query_rewritten_fallback
    return info
