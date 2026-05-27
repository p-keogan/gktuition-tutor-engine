"""Glue module — wires every firewall layer into the existing /query path.

The wiring is deliberately concentrated in one place (rather than spread
across ``api/main.py``) so the dispatch order from ADR-002 is auditable in
a single file. The ordering is:

* L1 — Turnstile (anonymous + flagged-subnet escalation).
* L2 — Anti-spam (honeypot, dwell, bot-UA) + rate limit + subnet cap.
* L6 — Trace start.
* (Agent 09's pipeline: classify → retrieve → … )
* L3 — Cache lookup (after retrieve, before synthesize).
* L4 — Circuit breaker is installed at startup; it surfaces during synthesize.
* L5 — Kill switch precheck + post-call record_spend.
* L6 — Trace end.

This module exposes one function — :func:`run_with_firewall` — which the
``POST /query`` route calls in place of the bare ``_run_query``. The output
is the same ``QueryResponse``; the only behavioural difference is
``from_cache=True`` on cache hits and the additional response headers
(``X-RateLimit-Remaining-*``, ``X-Firewall-Cap-State``).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from fastapi import HTTPException, Request

from ..orchestrator.classifier import classify, classify_image_extracted
from ..orchestrator.contract import QueryClass, QueryResponse
from ..orchestrator.query_rewrite import maybe_rewrite
from ..orchestrator.retriever import retrieve
from ..orchestrator.synthesizer import (
    GUARDRAIL_ANSWER,
    estimate_cost_cents,
    select_citations,
    slug_anchor_override,
    synthesize,
)
from ..orchestrator.voice_anchor import infer_strand_from_retrieval
from ..services import query_log
from . import L1_turnstile, L2_rate_limit, L3_semantic_cache, L4_router
from . import L5_kill_switch as L5
from . import L6_tracing as L6
from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)


async def run_with_firewall(
    request: Request,
    *,
    body: dict[str, Any],
    q: str,
    tier: str,
    user_id: str,
    debug: bool,
    extracted_from_image: bool = False,
    request_id: str | None = None,
) -> QueryResponse:
    """Firewall-wrapped pipeline.

    Returns the canonical ``QueryResponse``. Raises ``HTTPException`` on any
    layer's hard block.
    """
    request_id = request_id or str(uuid.uuid4())
    started = time.perf_counter()

    # ---- L1 + L2 (front gate) ------------------------------------------
    # L2 anti-spam comes BEFORE Turnstile so a bot with a populated honeypot
    # gets rejected without ever round-tripping to Cloudflare. The order in
    # the ADR ("L1 → L2") is the *category* order; within L2 the cheap
    # rejections fire first.
    L2_rate_limit.check_anti_spam(request, body=body, tier=tier)

    # Flagged-subnet escalation — paying users on a flagged /24 still get
    # one Turnstile challenge before we let them through.
    client_ip = _client_ip(request)
    subnet = _subnet_24(client_ip) if client_ip else None
    forced_turnstile = L2_rate_limit.is_subnet_flagged(subnet)
    await L1_turnstile.require_turnstile_check(
        request, tier=tier, forced=forced_turnstile
    )

    L2_rate_limit.check_rate_limit(request, tier=tier, user_id=user_id)

    # ---- L5 precheck ---------------------------------------------------
    L5.precheck(tier)

    # ---- L6 trace start ------------------------------------------------
    trace = L6.start_trace(
        request_id=request_id,
        user_id=user_id,
        tier=tier,
        query=q,
        client_ip=client_ip,
    )

    try:
        # ---- Classify --------------------------------------------------
        with L6.span(trace, "classify", q_preview=L6._safe_query_preview(q)) as sp_c:
            if extracted_from_image:
                cls_result = classify_image_extracted(q)
                query_class = QueryClass.IMAGE_EXTRACTED
            else:
                cls_result = classify(q, return_matches=debug)
                query_class = cls_result.query_class
            sp_c.output["query_class"] = query_class.value
            sp_c.output["matched"] = list(cls_result.matched_phrases)

        # ---- Query rewrite (AGENT_21) ----------------------------------
        # Translate conceptual "explain X" framings into the corpus's
        # domain language so the reranker doesn't sub-floor on them. The
        # response's ``query`` field stays the student's input below; only
        # retrieval and synthesis see the rewritten string. Cache key
        # likewise stays the student's input — two students asking the
        # same conceptual question still share a cache slot.
        q_retrieval = maybe_rewrite(q, query_class)
        if q_retrieval != q:
            logger.info(
                "firewall query rewrite fired: original=%r rewritten=%r",
                q,
                q_retrieval,
            )

        # ---- Retrieve --------------------------------------------------
        with L6.span(trace, "retrieve", query_class=query_class.value) as sp_r:
            retrieval = await retrieve(q_retrieval, query_class)
            sp_r.output["chunks"] = len(retrieval.chunks)
            sp_r.output["top_score"] = retrieval.top_reranker_score
            sp_r.output["services_called"] = retrieval.services_called

        # ---- Decide intended model up-front (cache key needs it) -------
        # We can't perfectly know which model the synthesiser will pick (the
        # cheap path may fall back to the hard path on Cortex failure), but
        # the *intended* model is enough for the cache key — a cheap-path
        # response served from cache is what we want either way.
        intended_model = _intended_model(query_class, retrieval.top_reranker_score)

        # ---- Cache lookup ---------------------------------------------
        top_slugs = [c.slug for c in retrieval.chunks]
        with L6.span(
            trace,
            "cache_lookup",
            model=intended_model,
            n_slugs=len(top_slugs),
        ) as sp_cache:
            hit = L3_semantic_cache.lookup(
                query=q,
                top_k_slugs=top_slugs,
                model_used=intended_model,
                tier=tier,
                query_class=query_class.value,
            )
            sp_cache.output["hit"] = hit is not None

        if hit is not None:
            # ---- Cache HIT path ------------------------------------------
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            payload = dict(hit.response_json)
            payload["from_cache"] = True
            payload["elapsed_ms"] = elapsed_ms
            payload["query"] = q  # The cached query string may have differed
            # in casing/whitespace; respect the request's own echo contract.
            response = QueryResponse.model_validate(payload)
            event("L3", "served_hit", tier=tier, model=hit.model_used)
            await _write_log_safely(
                trace=trace,
                request_id=request_id,
                user_id=user_id,
                q=q,
                tier=tier,
                query_class=query_class.value,
                model_used=hit.model_used,
                top_slug=top_slugs[0] if top_slugs else None,
                top_reranker_score=retrieval.top_reranker_score,
                from_cache=True,
                elapsed_ms=elapsed_ms,
                cost_estimate_cents=0.0,
                extracted_question=q if extracted_from_image else None,
            )
            L6.finish_trace(trace, status_code=200)
            return _attach_state(request, response)

        # ---- Synthesise (cache miss) ---------------------------------
        # Pass the rewritten query into the synthesiser so its prompt is
        # consistent with what retrieval saw — same reasoning as the
        # non-firewall ``_run_query`` route.
        with L6.span(trace, "synthesize", intended_model=intended_model) as sp_s:
            synthesis = await asyncio.to_thread(
                _synthesize_with_breaker, q_retrieval, retrieval
            )
            sp_s.output["model_used"] = synthesis.model_used
            sp_s.output["answer_chars"] = len(synthesis.answer or "")

        citations = select_citations(retrieval)
        # Mirror the non-firewall ``_run_query`` route in ``routes/query.py``:
        # the synthesiser injects the voice anchor into the prompt; we surface
        # the strand decision on the wire so the eval harness can score
        # voice-match per strand and so manual QA can see at a glance whether
        # the anchor fired. Pure function — no second filesystem read.
        # AGENT_DAY_31 hot-fix: AGENT_15 wired this through the non-firewall
        # path but missed the firewall response builder, so live queries (all
        # of which take the firewall path in prod) were returning
        # ``voice_anchor_strand: null`` even after the corpus landed in /app.
        voice_anchor_strand = (
            infer_strand_from_retrieval(retrieval)
            if synthesis.answer != GUARDRAIL_ANSWER
            else None
        )
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        # AGENT_22 — mirror the synth's slug-anchor decision into debug_info
        # on the firewall path too. DAY_31 lesson: every response builder
        # needs the same fields surfaced; prod traffic takes this path.
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
            model_used=synthesis.model_used,
            from_cache=False,
            voice_anchor_strand=voice_anchor_strand,
            elapsed_ms=elapsed_ms,
            debug_info=_debug_info(
                retrieval,
                cls_result.matched_phrases,
                query_rewritten=(q_retrieval if q_retrieval != q else None),
                slug_anchor_override_fired=slug_anchor_fired,
            )
            if debug
            else None,
        )

        # ---- L5 record spend (post-call, so we know the realised model)
        try:
            L5.record_spend(tier=tier, model_used=synthesis.model_used)
        except Exception:
            logger.exception("L5 record_spend failed (non-fatal)")

        # ---- L3 store -------------------------------------------------
        # Only persist real grounded answers — the guardrail path stays out
        # of the cache so retries with better corpus coverage can succeed.
        if synthesis.answer != GUARDRAIL_ANSWER:
            L3_semantic_cache.store(
                query=q,
                top_k_slugs=top_slugs,
                model_used=synthesis.model_used,
                tier=tier,
                query_class=query_class.value,
                response_json=response.model_dump(mode="json"),
            )

        # ---- Log + trace end -----------------------------------------
        await _write_log_safely(
            trace=trace,
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
            cost_estimate_cents=estimate_cost_cents(
                synthesis.model_used, retrieval.chunks
            ),
            extracted_question=(q if extracted_from_image else None),
        )

        if synthesis.answer == GUARDRAIL_ANSWER:
            logger.info(
                "guardrail fired: q=%r query_class=%s top_score=%.2f",
                q,
                query_class.value,
                retrieval.top_reranker_score,
            )

        L6.finish_trace(trace, status_code=200)
        return _attach_state(request, response)
    except HTTPException as exc:
        L6.finish_trace(trace, status_code=exc.status_code)
        raise
    except Exception:
        L6.finish_trace(trace, status_code=500)
        raise


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _synthesize_with_breaker(q: str, retrieval: Any) -> Any:
    """Synthesise; if the circuit breaker yelps, fall back to the cheap path.

    The synthesiser is already injectable, so the L4 wrapper installed at
    startup decides whether to actually call Anthropic. If the breaker is
    open the wrapper raises ``BreakerOpen``, and we patch the retrieval's
    ``query_class`` for the duration of the call so the synthesiser picks
    the cheap path. This is the minimum change that doesn't require a
    second synthesise entrypoint.
    """
    try:
        return synthesize(q, retrieval)
    except L4_router.BreakerOpen:
        from ..orchestrator.contract import QueryClass

        # Force the cheap path by pretending this is a CONCEPT query at full
        # retrieval confidence.
        rebooted = retrieval.model_copy(
            update={
                "query_class": QueryClass.CONCEPT,
                "top_reranker_score": max(0.31, retrieval.top_reranker_score),
            }
        )
        return synthesize(q, rebooted)


def _intended_model(query_class: QueryClass, top_score: float) -> str:
    """Mirror the synthesiser's routing decision for cache-key purposes."""
    from ..orchestrator.retriever import RETRIEVAL_FLOOR
    from ..orchestrator.synthesizer import (
        ANALYST_MODEL,
        ANTHROPIC_MODEL,
        CORTEX_MODEL,
    )

    if query_class == QueryClass.ANALYTICAL:
        return ANALYST_MODEL
    if (
        query_class in (QueryClass.CONCEPT, QueryClass.SUMMARY_REQUEST)
        and top_score >= RETRIEVAL_FLOOR
    ):
        return CORTEX_MODEL
    return ANTHROPIC_MODEL


def _client_ip(request: Request) -> str | None:
    xff = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if xff:
        return xff.split(",")[0].strip()
    client: Any = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _subnet_24(ip: str) -> str:
    if ":" in ip:
        parts = ip.split(":")
        return ":".join(parts[:3]) + "::/48"
    parts = ip.split(".")
    if len(parts) != 4:
        return ip
    return ".".join(parts[:3]) + ".0/24"


def _debug_info(
    retrieval: Any,
    matched_phrases: tuple[str, ...],
    *,
    query_rewritten: str | None = None,
    slug_anchor_override_fired: bool = False,
) -> dict[str, Any]:
    info: dict[str, Any] = {
        "classifier_matches": list(matched_phrases),
        "services_called": retrieval.services_called,
        "top_reranker_score": retrieval.top_reranker_score,
        "analyst_sql": retrieval.analyst_sql,
        "n_chunks": len(retrieval.chunks),
        # AGENT_22 — present unconditionally so a caller running ``debug=true``
        # across a batch can grep for fire-rate without per-row presence
        # checks. False is the no-fire signal.
        "slug_anchor_override_fired": slug_anchor_override_fired,
    }
    # AGENT_21 — present only when the rewrite actually fired so callers
    # can tell "rewrite was disabled / not triggered" from "rewrite ran but
    # returned the input unchanged" if that ever matters in debugging.
    if query_rewritten is not None:
        info["query_rewritten"] = query_rewritten
    return info


async def _write_log_safely(
    *,
    trace: L6.TraceRecord | None,
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
    extracted_question: str | None,
) -> None:
    with L6.span(trace, "write_log", from_cache=from_cache) as sp:
        try:
            await query_log.write_text_query_log_row(
                request_id=request_id,
                user_id=user_id,
                q=q,
                tier=tier,
                query_class=query_class,
                model_used=model_used,
                top_slug=top_slug,
                top_reranker_score=top_reranker_score,
                from_cache=from_cache,
                elapsed_ms=elapsed_ms,
                cost_estimate_cents=cost_estimate_cents,
                extracted_question=extracted_question,
            )
            sp.output["wrote"] = True
        except Exception:
            logger.exception(
                "query log write failed (non-fatal): request_id=%s", request_id
            )
            sp.output["wrote"] = False


def _attach_state(request: Request, response: QueryResponse) -> QueryResponse:
    """Stash response metadata on ``request.state`` so the route can lift
    it into HTTP headers in the response.

    Headers are added by the route layer (not here) because we return a
    ``QueryResponse`` Pydantic model and FastAPI handles serialisation.
    """
    # Capture cap state every request for the /healthz observer.
    try:
        request.state.firewall_cap_state = L5.get_cap_state()
    except Exception:
        request.state.firewall_cap_state = None
    return response


# ---------------------------------------------------------------------------
# Startup wiring
# ---------------------------------------------------------------------------


def install_firewall_at_startup() -> None:
    """Call once at app startup.

    * Installs the L4 circuit-breaker wrapper around the Anthropic seam.
    * Wires the default Snowflake-backed L3 + L5 storage backends — these
      remain no-ops in dev because the Snowflake connector is absent until
      explicitly wired by the lifespan handler.
    """
    settings = get_settings()
    if settings.breaker_enabled:
        L4_router.install()
