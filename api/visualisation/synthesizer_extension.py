"""Synthesiser extension — decide whether to emit a graph, and which.

Two public functions:

* :func:`should_emit_graph` — deterministic-first + LLM-assisted (Haiku 4.5)
  decision on whether a graph would help the student. The deterministic
  side covers the high-precision majority of cases (explicit trigger phrases
  in the query, or retrieved tutorials from a graph-shaped strand). The
  LLM-assisted side covers the long tail and is only consulted when the
  deterministic check returns False.

* :func:`select_and_invoke_generator` — runs only if should_emit_graph
  returns True. Asks Haiku 4.5 with a strict tool-call schema which of the
  seven generators to invoke and with what parameters, validates the
  parameters, invokes the generator, returns the resulting Plotly JSON
  list. Returns ``[]`` on any failure (bad LLM output, unknown generator,
  generator raises ValueError) and logs a warning — the rest of the
  synthesis is unaffected.

Why Haiku 4.5 specifically: the call is short (one prompt, structured
tool output, no streaming), and the cost ceiling matters because the
synthesiser already pays for one Haiku call on the hard path; doubling
that with a second mid-tier model would dent the per-query budget. The
tool-call schema constraints the LLM to one of seven function names —
no free-text generation, no fabrication. The generator does the
deterministic Plotly JSON construction.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from typing import Any

from .generators import GENERATOR_REGISTRY

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic decision layer
# ---------------------------------------------------------------------------

# Phrases that strongly signal "the student wants a graph." Lower-cased
# regex tokens with word-boundary anchors so we don't false-positive on
# substrings (e.g. "asymptote" inside a longer word).
GRAPH_TRIGGER_PHRASES: tuple[str, ...] = (
    r"\bsketch\b",
    r"\bgraph\b",
    r"\bplot\b",
    r"\bshape of\b",
    r"\bdraw\b",
    r"\bbehaviour at infinity\b",
    r"\bbehavior at infinity\b",
    r"\bturning point\b",
    r"\bturning points\b",
    r"\basymptote\b",
    r"\basymptotes\b",
    r"\bcurve\b",
    r"\bvisualise\b",
    r"\bvisualize\b",
    r"\bwhat does .* look like\b",
)

_GRAPH_TRIGGER_RE = re.compile("|".join(GRAPH_TRIGGER_PHRASES), re.IGNORECASE)

# Slug prefixes whose tutorials are typically graph-shaped. Drawn from
# ``tutorials/LCHL_Functions_and_Graphs/``, ``tutorials/LCHL_Trigonometry_*``,
# ``tutorials/LCHL_Statistics/``, ``tutorials/LCHL_Indices_and_Logs/``,
# ``tutorials/LCHL_Differentiation/``.
GRAPH_SHAPED_SLUG_PREFIXES: tuple[str, ...] = (
    "functions-graphs-",
    "trigonometry-",
    "statistics-",
    "indices-logs-",
    "differentiation-",
)


# A tiny duck-typed RetrievedChunk-like protocol — we don't import the
# full pydantic model so this module stays import-cycle-free.
class _RetrievedLike:
    slug: str
    snippet: str
    score: float


# ---------------------------------------------------------------------------
# should_emit_graph
# ---------------------------------------------------------------------------


def should_emit_graph(
    query: str,
    query_class: str,
    retrieved: list[Any],
    *,
    llm_client: Callable[..., Any] | None = None,
) -> bool:
    """Return True iff the answer would benefit from a graph.

    Two-stage decision:

    1. **Deterministic.** Match against ``GRAPH_TRIGGER_PHRASES`` on the
       query; or the top retrieved tutorial slug begins with one of
       ``GRAPH_SHAPED_SLUG_PREFIXES``. Either trip → return True.
    2. **LLM-assisted fallback.** Only called if (1) returned False, the
       query is non-trivial, and ``llm_client`` is wired. Asks Haiku 4.5
       a yes/no question with a strict response shape. Returns the LLM's
       boolean answer; on any error, returns False (fail-closed — better
       to not show a graph than to show a wrong one).

    Args:
        query: The student's question, lower-cased internally.
        query_class: One of the ``QueryClass`` values (e.g. ``"concept"``).
                     Analytical queries never get a graph in v1 (the
                     v1 ship cut, per ADR-005 "out of scope").
        retrieved: List of retrieved chunks (anything with a ``.slug``
                   attribute / dict key works).
        llm_client: Optional callable that takes (prompt: str) → bool. If
                    None, the LLM-assisted layer is skipped. Tests inject
                    a fake; production wiring is in the route layer.

    Returns:
        True if a graph should be rendered.
    """
    if not query or not query.strip():
        return False

    # Analytical queries (Cortex Analyst rows / GROUP BY counts) don't get
    # a graph in v1 — see ADR-005 "out of scope".
    if query_class == "analytical":
        return False

    # --- Stage 1: deterministic --------------------------------------------
    if _GRAPH_TRIGGER_RE.search(query):
        logger.debug("should_emit_graph: deterministic trigger phrase matched")
        return True

    top_slug = _top_slug(retrieved)
    if top_slug and any(top_slug.startswith(p) for p in GRAPH_SHAPED_SLUG_PREFIXES):
        logger.debug(
            "should_emit_graph: top slug %r is graph-shaped", top_slug
        )
        return True

    # --- Stage 2: LLM-assisted fallback ------------------------------------
    if llm_client is None:
        return False

    try:
        return bool(_llm_should_emit_graph(query, query_class, top_slug, llm_client))
    except Exception:
        logger.warning("LLM-assisted should_emit_graph failed; defaulting to False",
                       exc_info=True)
        return False


def _top_slug(retrieved: list[Any]) -> str | None:
    """Pull the top retrieved chunk's slug, accepting both dict and pydantic."""
    if not retrieved:
        return None
    top = retrieved[0]
    if hasattr(top, "slug"):
        return str(top.slug)
    if isinstance(top, dict) and "slug" in top:
        return str(top["slug"])
    return None


# ---------------------------------------------------------------------------
# LLM-assisted layer (Haiku 4.5)
# ---------------------------------------------------------------------------


_SHOULD_EMIT_PROMPT_TEMPLATE = """\
You are a deterministic gate that decides whether an interactive Plotly
chart would meaningfully help a Leaving Cert Higher Level maths student
answer their question. Reply with exactly one token: "yes" or "no".

Yes if the question would be answered more clearly by showing a curve,
discrete-points plot, asymptote, turning point, or similar visual maths
artefact. No otherwise.

Question: {query}
Routing class: {query_class}
Top retrieved tutorial: {top_slug}
"""


def _llm_should_emit_graph(
    query: str,
    query_class: str,
    top_slug: str | None,
    llm_client: Callable[..., Any],
) -> bool:
    """Default LLM-assisted decision: ask Haiku 4.5 a yes/no question.

    Tests inject a fake ``llm_client(prompt) -> str`` that returns
    "yes" / "no". Production wiring in the synthesiser passes the real
    Anthropic Haiku 4.5 client.
    """
    prompt = _SHOULD_EMIT_PROMPT_TEMPLATE.format(
        query=query.strip()[:600],
        query_class=query_class,
        top_slug=top_slug or "(none)",
    )
    out = llm_client(prompt)
    if isinstance(out, bool):
        return out
    text = str(out).strip().lower()
    return text.startswith("y")


# ---------------------------------------------------------------------------
# select_and_invoke_generator
# ---------------------------------------------------------------------------


_TOOL_CALL_SCHEMA: dict[str, dict[str, Any]] = {
    "plot_polynomial": {
        "required": ["coefficients"],
        "optional": ["x_range", "title", "show_zeros", "show_turning_points"],
    },
    "plot_trig": {
        "required": ["family"],
        "optional": [
            "amplitude",
            "period",
            "phase",
            "vertical_shift",
            "x_range",
            "title",
        ],
    },
    "plot_exponential": {
        "required": [],
        "optional": ["base", "multiplier", "growth_rate", "offset", "x_range", "title"],
    },
    "plot_log": {
        "required": [],
        "optional": ["base", "multiplier", "inner_scale", "offset", "x_range", "title"],
    },
    "plot_piecewise": {
        "required": ["pieces"],
        "optional": ["title", "samples_per_piece", "x_label", "y_label"],
    },
    "plot_data_points": {
        "required": ["points"],
        "optional": ["title", "x_label", "y_label", "show_best_fit"],
    },
    "plot_overlay": {
        "required": ["figures"],
        "optional": ["title", "x_label", "y_label"],
    },
}
"""Per-tool parameter contract. Used to validate the LLM's tool-call
arguments before we invoke the matching generator."""


SELECT_GENERATOR_SYSTEM_PROMPT = """\
You are a tool-router for a maths-tutor visualisation layer. Given a
student question and the retrieved tutorials, pick exactly ONE of the
following functions and emit ONLY a JSON object of the shape:

  {"name": "<one_of_the_seven_functions>", "arguments": {...}}

Functions available:

* plot_polynomial(coefficients, x_range?, title?, show_zeros?, show_turning_points?)
   — for quadratics/cubics/quartics. coefficients in highest-degree-first order.
* plot_trig(family, amplitude?, period?, phase?, vertical_shift?, x_range?, title?)
   — family ∈ {"sin","cos","tan","sec","cosec","cot"}.
* plot_exponential(base?, multiplier?, growth_rate?, offset?, x_range?, title?)
* plot_log(base?, multiplier?, inner_scale?, offset?, x_range?, title?)
* plot_piecewise(pieces, title?)  — pieces is JSON-incompatible (callables);
   PREFER plot_polynomial or plot_trig when possible.
* plot_data_points(points, title?, show_best_fit?)
   — points is [[x,y], ...].
* plot_overlay(figures, title?)  — only when explicitly comparing curves.

Rules:
- Pick the SMALLEST applicable function. If the question is about a
  quadratic, pick plot_polynomial — not plot_overlay.
- coefficients/parameters MUST come from the question text or the
  retrieved tutorials. Never invent.
- If no specific function/numbers are present, return:
  {"name": "none", "arguments": {}}
"""

SELECT_GENERATOR_USER_PROMPT_TEMPLATE = """\
Question: {query}

Top retrieved tutorial: {top_slug}

Snippet from top tutorial:
{snippet}

Emit the JSON object now.
"""


def select_and_invoke_generator(
    query: str,
    retrieved: list[Any],
    llm_client: Callable[..., Any] | None = None,
) -> list[dict[str, Any]]:
    """Ask the LLM which generator to invoke; invoke it; return Plotly JSON.

    Returns ``[]`` if:
    * ``llm_client`` is None (no model available),
    * the LLM returns malformed JSON,
    * the LLM picks ``name="none"``,
    * the LLM picks an unknown generator,
    * the picked generator raises ``ValueError`` on the supplied args.

    Args:
        query: Student question.
        retrieved: List of retrieved chunks (must expose ``.slug`` and
                   ``.snippet`` — pydantic ``RetrievedChunk`` or dict).
        llm_client: Optional callable taking (system_prompt, user_prompt)
                    → str (a JSON string). Tests inject a fake; production
                    wiring is in the route layer.

    Returns:
        A list of Plotly figure dicts. v1 always emits 0 or 1 entries; the
        list shape is forward-compatible with future multi-figure responses.
    """
    if llm_client is None:
        logger.debug("select_and_invoke_generator: no llm_client wired; returning []")
        return []

    top_slug = _top_slug(retrieved) or "(none)"
    snippet = _top_snippet(retrieved) or "(none)"

    user_prompt = SELECT_GENERATOR_USER_PROMPT_TEMPLATE.format(
        query=query.strip()[:1200],
        top_slug=top_slug,
        snippet=snippet[:800],
    )

    try:
        raw = llm_client(SELECT_GENERATOR_SYSTEM_PROMPT, user_prompt)
    except Exception:
        logger.warning("select_and_invoke_generator: llm_client raised", exc_info=True)
        return []

    tool_call = _parse_tool_call(raw)
    if tool_call is None:
        return []

    name, arguments = tool_call

    if name == "none":
        logger.debug("select_and_invoke_generator: LLM chose 'none'")
        return []

    if name not in GENERATOR_REGISTRY:
        logger.warning("select_and_invoke_generator: unknown generator %r", name)
        return []

    contract = _TOOL_CALL_SCHEMA.get(name, {"required": [], "optional": []})
    missing = [k for k in contract["required"] if k not in arguments]
    if missing:
        logger.warning(
            "select_and_invoke_generator: %r missing required args %s", name, missing
        )
        return []

    # Drop any keys not in the contract — defends against the LLM passing
    # ``__class__`` or other Python footguns.
    allowed = set(contract["required"]) | set(contract["optional"])
    safe_args = {k: v for k, v in arguments.items() if k in allowed}

    # Coerce x_range list → tuple if present (LLMs emit lists from JSON).
    if "x_range" in safe_args and isinstance(safe_args["x_range"], list):
        safe_args["x_range"] = tuple(safe_args["x_range"])

    # plot_piecewise requires callables; the LLM cannot emit callables in
    # JSON, so refuse this generator at the tool-router boundary and let
    # the upper layer fall back to one of the algebraic generators.
    if name == "plot_piecewise":
        logger.info(
            "select_and_invoke_generator: refusing LLM-driven plot_piecewise "
            "(callables not JSON-serialisable). Use direct generator call instead."
        )
        return []

    fn = GENERATOR_REGISTRY[name]
    try:
        figure = fn(**safe_args)
    except (ValueError, TypeError) as exc:
        logger.warning(
            "select_and_invoke_generator: generator %r raised %s", name, exc
        )
        return []

    return [figure]


def _top_snippet(retrieved: list[Any]) -> str | None:
    if not retrieved:
        return None
    top = retrieved[0]
    if hasattr(top, "snippet"):
        return str(top.snippet)
    if isinstance(top, dict) and "snippet" in top:
        return str(top["snippet"])
    return None


def _parse_tool_call(raw: Any) -> tuple[str, dict[str, Any]] | None:
    """Best-effort parse of the LLM's tool-call response.

    Accepts a JSON string, a dict, or an Anthropic-style content-block list
    whose first entry is a dict with ``"input"``. Returns ``(name, arguments)``
    or ``None`` on any structural failure.
    """
    import json

    if raw is None:
        return None

    # Already a dict?
    if isinstance(raw, dict):
        obj = raw
    elif isinstance(raw, list):
        # Anthropic SDK returns a list of content blocks; if the first one
        # carries ``input``, treat that as the tool-use arguments.
        if not raw:
            return None
        first = raw[0]
        if isinstance(first, dict) and "input" in first and "name" in first:
            return str(first["name"]), dict(first["input"])
        return None
    else:
        text = str(raw).strip()
        if not text:
            return None
        # Strip Markdown code fences if present.
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            logger.warning("select_and_invoke_generator: malformed JSON from LLM: %r",
                           text[:200])
            return None

    if not isinstance(obj, dict):
        logger.warning("select_and_invoke_generator: parsed object is not a dict")
        return None

    name = obj.get("name")
    args = obj.get("arguments")
    if not isinstance(name, str):
        return None
    if not isinstance(args, dict):
        args = {}
    return name, dict(args)


# ---------------------------------------------------------------------------
# Default LLM client (Anthropic Haiku 4.5) — lazy-imported.
# ---------------------------------------------------------------------------


def default_anthropic_haiku_client(
    system_prompt: str, user_prompt: str
) -> str:
    """Default Haiku-4.5 client. Tests should never call this; they inject fakes.

    Reads ``ANTHROPIC_API_KEY`` from the environment. Imports the SDK
    lazily so unit tests that mock the seam never need ``anthropic``
    installed.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY must be set to call Haiku 4.5.")
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=400,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = [b.text for b in resp.content if hasattr(b, "text")]
    return "".join(parts).strip()
