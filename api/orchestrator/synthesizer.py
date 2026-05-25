"""Synthesizer — two-tier LLM router that turns retrieval into an answer.

Routing logic per ADR-003 Decision item 2:

* **Cheap path (~80% of queries)** — Snowflake Cortex ``mistral-large2``.
  Used when ``query_class ∈ {concept, summary_request}`` AND the top
  reranker score meets ``RETRIEVAL_FLOOR``. Cortex is in-warehouse so this
  costs cents per query and no external API call.
* **Hard path (~20%)** — Claude Haiku 4.5 via the Anthropic API. Used for
  pedagogical-reasoning queries (``ambiguous``, ``solution_lookup``,
  ``image_extracted``), or whenever the cheap path's retrieval was too weak.
* **Analytical path** — when ``query_class == analytical`` the retrieval
  layer has already produced rows. The synthesiser turns the rows into a
  short prose answer using whichever path the router picks.

The "I don't know" guardrail: if every chunk falls below ``RETRIEVAL_FLOOR``
the synthesiser short-circuits — no LLM call, fixed string for ``answer``,
``retrieved`` is still surfaced so the widget can show the related-tutorial
tray. ``model_used`` becomes ``"(none)"`` in this branch.

All model clients are injectable via the ``set_*_caller`` seams so tests can
swap in fakes.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass

from .contract import (
    Citation,
    GraphSpec,
    QueryClass,
    RetrievalResult,
    RetrievedChunk,
)
from .retriever import RETRIEVAL_FLOOR
from .voice_anchor import build_voice_anchor

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CORTEX_MODEL = "cortex.mistral-large2"
ANTHROPIC_MODEL = "anthropic.claude-haiku-4-5"
ANALYST_MODEL = "cortex.analyst"
NO_MODEL = "(none)"

# Maximum number of evidence chunks we pass into the prompt. More than ~4
# stops materially improving answer quality and starts hurting latency.
EVIDENCE_CHUNKS_IN_PROMPT = 4

GUARDRAIL_ANSWER = (
    "I'm not sure — try one of these related tutorials"
)

SYSTEM_PROMPT = (
    "You are GKTuition's AI maths tutor. You answer questions about the "
    "Leaving Certificate Higher Level mathematics curriculum, grounding "
    "every answer in the evidence chunks provided below. RULES:\n"
    "1. NEVER fabricate exam years, paper references, or tutorial slugs.\n"
    "2. If the evidence does not contain enough to answer the question, "
    "say so plainly and recommend the closest tutorial from the evidence.\n"
    "3. Keep the answer short. Two to four sentences for a concept; five "
    "to eight for a worked-solution walkthrough; one sentence for an "
    "analytical question (the number plus a short interpretation).\n"
    "4. Use plain text. Markdown is fine; LaTeX is preferred for "
    "equations (wrap in $...$). Do not use code fences.\n"
    "5. Do not introduce yourself or thank the student.\n"
)


def _effective_system_prompt(retrieval: RetrievalResult) -> str:
    """Compose ``SYSTEM_PROMPT`` + the voice anchor prefix for a retrieval.

    The voice anchor (strand cram summary + ``_voice.md`` rules) is the
    Phase-2 load-bearing differentiator: without it the soft-path Cortex
    answer reads like generic Mistral output; with it, the answer adopts
    Paul's phrasing, log-tables citation discipline, and 'Therefore...'
    closing convention. See ``voice_anchor.build_voice_anchor`` for the
    cost trade-off (~3,000 tokens / ~€0.01 per request on Sonnet).

    Returns the bare ``SYSTEM_PROMPT`` unchanged when no anchor is
    available — keeps Phase-1 behaviour for solution-side queries, missing
    corpus, etc.
    """
    anchor = build_voice_anchor(retrieval)
    if anchor is None:
        return SYSTEM_PROMPT
    return f"{SYSTEM_PROMPT}\n\n{anchor}"


# ---------------------------------------------------------------------------
# Synthesis result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SynthesisResult:
    """In-process container returned to the route layer."""

    answer: str
    model_used: str


# ---------------------------------------------------------------------------
# Client seams
# ---------------------------------------------------------------------------


CortexCompleteCaller = Callable[[str, str], str]
AnthropicMessageCaller = Callable[[str, str], str]

_cortex_caller: CortexCompleteCaller | None = None
_anthropic_caller: AnthropicMessageCaller | None = None


def set_cortex_caller(fn: CortexCompleteCaller | None) -> None:
    """Register a (model, prompt) -> answer callable for the cheap path."""
    global _cortex_caller
    _cortex_caller = fn


def set_anthropic_caller(fn: AnthropicMessageCaller | None) -> None:
    """Register a (system_prompt, user_prompt) -> answer callable for the hard path."""
    global _anthropic_caller
    _anthropic_caller = fn


# ---------------------------------------------------------------------------
# Default client implementations (used at production runtime only)
# ---------------------------------------------------------------------------


def _default_cortex_caller(model: str, prompt: str) -> str:
    """Call ``SNOWFLAKE.CORTEX.COMPLETE(<model>, <prompt>)``.

    Runs synchronously via the pooled connection in ``retriever.py``. The
    route layer calls us from a thread so the asyncio event loop isn't
    blocked.
    """
    from .retriever import _cursor

    with _cursor() as cs:
        cs.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS answer",
            (model.removeprefix("cortex."), prompt),
        )
        row = cs.fetchone()
    return str(row[0]) if row and row[0] is not None else ""


def _default_anthropic_caller(system_prompt: str, user_prompt: str) -> str:
    """Call the Anthropic Messages API with Haiku 4.5.

    Reads ``ANTHROPIC_API_KEY`` from the environment. Imports the SDK lazily
    so test paths that mock the seam never have to install ``anthropic``.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set to call Claude Haiku 4.5.")
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = [b.text for b in resp.content if hasattr(b, "text")]
    return "".join(parts).strip()


def _call_cortex(model: str, prompt: str) -> str:
    return (_cortex_caller or _default_cortex_caller)(model, prompt)


def _call_anthropic(system_prompt: str, user_prompt: str) -> str:
    return (_anthropic_caller or _default_anthropic_caller)(system_prompt, user_prompt)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def synthesize(query: str, retrieval: RetrievalResult) -> SynthesisResult:
    """Build a prompt, call the right model, return an answer string."""
    # --- Guardrail: no usable retrieval ----------------------------------
    if retrieval.query_class != QueryClass.ANALYTICAL and (
        not retrieval.chunks or retrieval.top_reranker_score < RETRIEVAL_FLOOR
    ):
        # The retrieved chunks (if any) still get surfaced by the route; we
        # just refuse to invent an answer.
        return SynthesisResult(answer=GUARDRAIL_ANSWER, model_used=NO_MODEL)

    user_prompt = _build_prompt(query, retrieval)
    # Voice-anchored system prompt: SYSTEM_PROMPT + strand cram summary +
    # _voice.md rules. Falls back to bare SYSTEM_PROMPT when the corpus
    # files are unavailable. See `_effective_system_prompt` for the cost
    # trade-off.
    system_prompt = _effective_system_prompt(retrieval)

    # --- Analytical path -------------------------------------------------
    if retrieval.query_class == QueryClass.ANALYTICAL:
        # Wrap the analyst rows in prose. The cheap path is fine here — the
        # heavy lift was the SQL, the prose is a one-shot summarisation.
        try:
            answer = _call_cortex(CORTEX_MODEL, user_prompt)
        except Exception:
            logger.exception("cortex.complete failed for analytical path; falling back")
            answer = _call_anthropic(system_prompt, user_prompt)
            return SynthesisResult(answer=answer, model_used=ANTHROPIC_MODEL)
        # Tag with ANALYST_MODEL so callers can see this was the structured
        # path, even though the prose came from mistral-large2.
        return SynthesisResult(answer=answer.strip(), model_used=ANALYST_MODEL)

    # --- Two-tier routing for RAG paths ---------------------------------
    use_cheap = (
        retrieval.query_class in (QueryClass.CONCEPT, QueryClass.SUMMARY_REQUEST)
        and retrieval.top_reranker_score >= RETRIEVAL_FLOOR
    )

    if use_cheap:
        try:
            answer = _call_cortex(
                CORTEX_MODEL, _build_cortex_prompt(query, retrieval, system_prompt)
            )
            return SynthesisResult(answer=answer.strip(), model_used=CORTEX_MODEL)
        except Exception:
            logger.exception("cortex.complete failed; falling back to Anthropic")

    answer = _call_anthropic(system_prompt, user_prompt)
    return SynthesisResult(answer=answer.strip(), model_used=ANTHROPIC_MODEL)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


def _build_prompt(query: str, retrieval: RetrievalResult) -> str:
    """Build the user-facing prompt for the Anthropic (Messages) call.

    Includes:
    * the routing decision (so the model knows what kind of answer to write),
    * the evidence chunks (capped at ``EVIDENCE_CHUNKS_IN_PROMPT``),
    * analyst rows for the analytical / ambiguous paths.
    """
    parts: list[str] = []
    parts.append(f"Question: {query.strip()}")
    parts.append("")
    parts.append(f"Routing decision: {retrieval.query_class.value}")

    if retrieval.analyst_rows:
        parts.append("")
        parts.append("Analyst rows (from Cortex Analyst over EXAM_PARTS):")
        for row in retrieval.analyst_rows[:5]:
            parts.append(f"- {row}")
        if retrieval.analyst_sql:
            parts.append(f"  (SQL: {retrieval.analyst_sql})")

    if retrieval.chunks:
        parts.append("")
        parts.append("Evidence chunks (cite by slug):")
        for c in retrieval.chunks[:EVIDENCE_CHUNKS_IN_PROMPT]:
            parts.append(f"- [{c.slug}] (score={c.score:.2f}): {c.snippet}")

    parts.append("")
    parts.append(
        "Write the answer now. Cite at least one slug from the evidence list "
        "in square brackets at the end of the relevant sentence."
    )
    return "\n".join(parts)


def _build_cortex_prompt(
    query: str,
    retrieval: RetrievalResult,
    system_prompt: str | None = None,
) -> str:
    """The cheap path uses the same prompt but with the system prompt inlined.

    Cortex ``COMPLETE(model, prompt)`` doesn't separate system from user the
    way the Anthropic API does, so we glue them together. When the caller
    passes a ``system_prompt`` (the voice-anchored one), use that; otherwise
    fall back to bare ``SYSTEM_PROMPT`` (kept for backwards-compatibility
    with any caller that might still be on the Phase-1 signature).
    """
    sys_prompt = system_prompt if system_prompt is not None else SYSTEM_PROMPT
    return sys_prompt + "\n\n" + _build_prompt(query, retrieval)


# ---------------------------------------------------------------------------
# Cost estimation (used by the route's query log writer)
# ---------------------------------------------------------------------------


def estimate_cost_cents(model_used: str, chunks: list[RetrievedChunk]) -> float:
    """Rough cost estimate in cents.

    The point of logging the cost is to feed Agent 10's kill-switch maths.
    The number does not need to be exact — order-of-magnitude is enough.

    Cortex mistral-large2: ~0.05 cents per query (XS warehouse + tokens).
    Claude Haiku 4.5:      ~0.30 cents per query (input + output).
    Cortex Analyst:        ~0.10 cents per query (one analyst call + SQL exec).
    Guardrail (NO_MODEL):  ~0.02 cents (search only, no generation).
    """
    base = {
        CORTEX_MODEL: 0.05,
        ANTHROPIC_MODEL: 0.30,
        ANALYST_MODEL: 0.10,
        NO_MODEL: 0.02,
    }.get(model_used, 0.05)
    # Roughly proportional to evidence size; +0.01c per chunk over the
    # baseline 4.
    extra = 0.01 * max(0, len(chunks) - EVIDENCE_CHUNKS_IN_PROMPT)
    return round(base + extra, 4)


# ---------------------------------------------------------------------------
# Citation construction helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Visualisation extension (Agent 13 / ADR-005)
# ---------------------------------------------------------------------------


# Injectable LLM seam for the graph-routing call. Tests inject a fake; the
# route layer wires the real Anthropic Haiku 4.5 client at startup.
_graph_llm_client: Callable[..., str] | None = None


def set_graph_llm_client(fn: Callable[..., str] | None) -> None:
    """Register the LLM tool-router used by select_and_invoke_generator."""
    global _graph_llm_client
    _graph_llm_client = fn


def augment_with_graphs(
    query: str, retrieval: RetrievalResult
) -> list[GraphSpec]:
    """Decide whether to emit a graph, and if so build the Plotly JSON.

    Wraps :mod:`api.visualisation.synthesizer_extension`. Wired by the
    route layer after :func:`synthesize` produces the answer text — graph
    generation is independent of the answer string, so failures here never
    affect the answer. Returns an empty list on any failure (graphs are
    additive UX; absence is degraded but valid).

    The deterministic check (``should_emit_graph``) runs without consulting
    the LLM in the common case. Only when neither a trigger phrase nor a
    graph-shaped slug fires do we ask the LLM, and even then the LLM
    output is validated against ``_TOOL_CALL_SCHEMA`` before invocation.
    """
    try:
        from ..visualisation.synthesizer_extension import (
            select_and_invoke_generator,
            should_emit_graph,
        )
    except Exception:
        logger.warning("visualisation package not importable; skipping graph step",
                       exc_info=True)
        return []

    if not should_emit_graph(
        query,
        retrieval.query_class.value,
        list(retrieval.chunks),
        llm_client=None,  # Stage-1 only at this gate; keep latency tight.
    ):
        return []

    figures = select_and_invoke_generator(
        query, list(retrieval.chunks), llm_client=_graph_llm_client
    )
    return [_to_graph_spec(fig) for fig in figures if fig]


def _to_graph_spec(figure: dict[str, object]) -> GraphSpec:
    """Wrap a raw Plotly dict into a GraphSpec, inferring the ``kind`` from
    the figure's first-trace name. Failure-safe — falls back to 'overlay'
    if the shape is unrecognised so the widget still renders something.
    """
    kind = "overlay"
    try:
        data = figure.get("data") if isinstance(figure, dict) else None
        if isinstance(data, list) and data:
            name = str(data[0].get("name", "")).lower()
            if name in ("sin", "cos", "tan", "sec", "cosec", "csc", "cot"):
                kind = "trig"
            elif name == "data":
                kind = "data_points"
            elif name == "f(x)":
                # Could be polynomial / exponential / log / piecewise — the
                # title carries the disambiguation if needed by the eval
                # harness. v1 doesn't disambiguate further here.
                kind = "polynomial"
    except Exception:
        pass
    return GraphSpec(kind=kind, figure=figure)


def select_citations(retrieval: RetrievalResult) -> list[Citation]:
    """Return the citations to surface in the response.

    The guardrail path emits no citations even if the chunks are still in
    ``retrieved`` — we don't want the widget to render a "we used these
    sources" UI when the answer text is "I'm not sure".
    """
    if not retrieval.chunks or retrieval.top_reranker_score < RETRIEVAL_FLOOR:
        if retrieval.query_class == QueryClass.ANALYTICAL:
            return retrieval.citations[:5]
        return []
    return retrieval.citations[:5]
