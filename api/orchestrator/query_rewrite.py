"""Query-rewriting layer — translates conceptual student framings into the
corpus's domain language so the reranker doesn't sub-floor on them.

Background
==========

DAY_31 live-verification surfaced a failure mode: queries like
``"explain pensions"`` retrieve the canonically-correct tutorial
(``financial-maths-8-pensions``) at rank 1, but the reranker scores the
conceptual phrasing at ~0.03 — well below ``RETRIEVAL_FLOOR = 0.30`` — so
the synthesiser short-circuits to the "I'm not sure" guardrail and the
student gets nothing. Re-asked in domain language (``"how do I calculate
the present value of a pension"``) the same retrieval clears the floor
cleanly. This module is the AGENT_21 intervention: an LLM-backed
rewriting step inserted between classification and retrieval, gated by a
deterministic pre-check so the round-trip only fires on the ~10% of
queries that actually need it.

Pairs with AGENT_22's slug-anchor post-filter (the orthogonal lever).

Contract
========

The single public entry-point is :func:`maybe_rewrite`. It returns the
rewritten query when *all* of the following hold, and the original query
otherwise:

* ``QUERY_REWRITE_ENABLED`` is truthy in the environment (read every
  call, so flipping the Fly secret takes effect without a restart),
* ``query_class == QueryClass.CONCEPT``,
* the deterministic pre-check accepts the query as a short conceptual
  framing,
* the LLM call succeeds and returns a non-empty string.

The function never raises. On any exception the original query is
returned and the failure is logged.

Test seam
=========

:func:`set_rewrite_llm_caller` mirrors ``synthesizer.set_anthropic_caller``
so tests can inject deterministic fakes. The default implementation
(:func:`_default_rewrite_llm_caller`) lazy-imports the ``anthropic`` SDK
and calls Haiku 4.5.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable

from .contract import QueryClass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Conceptual-framing prefixes the pre-check looks for. Case-insensitive,
#: matched after :py:meth:`str.strip`. Trailing space is part of the token
#: so we don't match on ``"explainthings"``.
_CONCEPTUAL_PREFIXES: tuple[str, ...] = (
    "explain ",
    "describe ",
    "what is ",
    "what are ",
    "tell me about ",
    "how does ",
    "define ",
)

#: Common English stopwords stripped before counting "content" tokens.
#: Deliberately tiny — we only need to exclude function words that pad
#: short conceptual queries.
_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "of", "to", "for", "in", "on", "at", "by",
        "with", "and", "or", "but", "is", "are", "was", "were", "be",
        "as", "from", "into", "about",
    }
)

#: Maximum number of non-stopword content tokens (after stripping the
#: conceptual prefix) for the pre-check to accept the query as "short
#: conceptual framing". Longer queries usually carry enough domain
#: language on their own.
_MAX_CONTENT_TOKENS = 4

#: Domain-language signals — if any of these appear the query is already
#: in tutorial vocabulary and the rewrite would be a no-op (or worse,
#: drift the intent). Lower-cased substrings unless noted otherwise.
_DOMAIN_LANGUAGE_KEYWORDS: tuple[str, ...] = (
    "prove",
    "derive",
    "factorise",
    "factorize",
    "differentiate",
    "integrate",
    "solve for",
    "find the",
)

#: Single-character/glyph domain signals — checked directly on the raw
#: (pre-lowercase) query so ``²`` / ``³`` survive normalisation.
_DOMAIN_LANGUAGE_GLYPHS: tuple[str, ...] = ("=", "²", "³", "√")

#: LaTeX inline-math fence — ``$...$`` anywhere in the query is a strong
#: domain-language signal.
_LATEX_RE: re.Pattern[str] = re.compile(r"\$[^$]+\$")

#: System prompt for the rewrite LLM. Stable string; if this needs to
#: change, version-bump the module and update the test that pins it.
REWRITE_SYSTEM_PROMPT = (
    "You rewrite a Leaving Cert Higher Level mathematics student's conceptual\n"
    "question into the domain language a corresponding tutorial would use.\n"
    "Rules:\n"
    "1. Output ONE rewritten query and nothing else — no preamble, no\n"
    "   explanation, no quote marks.\n"
    "2. Use the LCHL maths vocabulary the student would see in a tutorial title\n"
    "   or formula sheet — \"present value of an annuity\", \"permutations with\n"
    "   repetition\", \"factorise a quadratic\", \"derive the quotient rule\".\n"
    "3. Keep it ≤ 15 words.\n"
    "4. Preserve the student's intent — don't add specificity they didn't ask\n"
    "   for (no \"of a 4-year pension\", no \"with 5 digits\", no example numbers).\n"
    "5. If the input is already in domain language, return it unchanged."
)

#: Anthropic model id used in production. Mirrors
#: ``synthesizer._default_anthropic_caller``'s pinning so the two paths
#: stay on the same Haiku build.
_REWRITE_MODEL = "claude-haiku-4-5-20251001"

#: Output cap. The system prompt asks for ≤ 15 words; 50 tokens is
#: comfortable headroom and prevents runaway output if the model
#: misbehaves.
_REWRITE_MAX_TOKENS = 50

#: Env var that gates the whole layer. Read on every call so a Fly
#: secret flip takes effect without restart.
_FEATURE_FLAG_ENV = "QUERY_REWRITE_ENABLED"


# ---------------------------------------------------------------------------
# Test seam
# ---------------------------------------------------------------------------


#: Callable shape: ``(system_prompt, user_prompt) -> rewritten_string``.
#: Returning empty string or raising is treated as "rewrite failed; pass
#: the original through".
RewriteLLMCaller = Callable[[str, str], str]

_rewrite_llm_caller: RewriteLLMCaller | None = None


def set_rewrite_llm_caller(fn: RewriteLLMCaller | None) -> None:
    """Register the (system_prompt, user_prompt) → rewritten_text seam.

    Mirrors :func:`api.orchestrator.synthesizer.set_anthropic_caller`. Tests
    inject fakes; production wiring leaves this ``None`` so the default
    :func:`_default_rewrite_llm_caller` is used.
    """
    global _rewrite_llm_caller
    _rewrite_llm_caller = fn


def _call_rewrite_llm(system_prompt: str, user_prompt: str) -> str:
    return (_rewrite_llm_caller or _default_rewrite_llm_caller)(
        system_prompt, user_prompt
    )


def _default_rewrite_llm_caller(system_prompt: str, user_prompt: str) -> str:
    """Call Anthropic Messages with Haiku 4.5 for the rewrite.

    Lazy-imports the SDK so test paths that mock the seam never have to
    install ``anthropic``. Reads ``ANTHROPIC_API_KEY`` from the
    environment.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY must be set to call the rewrite LLM."
        )
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=_REWRITE_MODEL,
        max_tokens=_REWRITE_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts = [b.text for b in resp.content if hasattr(b, "text")]
    return "".join(parts).strip()


# ---------------------------------------------------------------------------
# Pre-check
# ---------------------------------------------------------------------------


def _is_feature_enabled() -> bool:
    """Truthy-string check on ``QUERY_REWRITE_ENABLED``.

    Recognises ``"1"``, ``"true"``, ``"yes"``, ``"on"`` (case-insensitive)
    as enabled. Anything else — including unset — disables the layer.
    """
    raw = os.environ.get(_FEATURE_FLAG_ENV, "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _strip_conceptual_prefix(q_lower: str) -> str | None:
    """Return ``q_lower`` with its conceptual prefix removed, or None.

    ``None`` means the query did not start with any recognised prefix.
    The matched prefix's trailing space is consumed; the remainder is
    returned without further stripping (the caller does that).
    """
    for prefix in _CONCEPTUAL_PREFIXES:
        if q_lower.startswith(prefix):
            return q_lower[len(prefix):]
    return None


def _content_token_count(remainder: str) -> int:
    """Count non-stopword tokens in ``remainder``.

    Tokens are split on whitespace; punctuation other than apostrophes is
    stripped before stopword comparison. The result is the count of
    "content-bearing" tokens — what the pre-check uses to decide whether
    the query is short enough to be a candidate for rewriting.
    """
    tokens = remainder.split()
    count = 0
    for raw in tokens:
        clean = re.sub(r"[^\w']+", "", raw).lower()
        if not clean:
            continue
        if clean in _STOPWORDS:
            continue
        count += 1
    return count


def _has_domain_language_signal(query: str) -> bool:
    """True if ``query`` carries a signal that it's already in domain language.

    Domain signals include LaTeX inline math (``$...$``), the glyphs
    ``= ² ³ √``, and certain operative keywords (``prove``, ``derive``,
    ``factorise`` etc.). Presence of any of these short-circuits the
    rewrite so we don't redundantly translate (or worse, drift the intent
    of) a query the corpus would already match well.
    """
    if _LATEX_RE.search(query):
        return True
    for glyph in _DOMAIN_LANGUAGE_GLYPHS:
        if glyph in query:
            return True
    lower = query.lower()
    for kw in _DOMAIN_LANGUAGE_KEYWORDS:
        if kw in lower:
            return True
    return False


def _should_rewrite(query: str, query_class: QueryClass) -> bool:
    """Deterministic pre-check — decides whether to call the rewrite LLM.

    All conditions must hold (see module docstring for the rationale):

    1. ``query_class == QueryClass.CONCEPT``.
    2. After :py:meth:`str.strip` + :py:meth:`str.lower`, the query begins
       with one of :data:`_CONCEPTUAL_PREFIXES`.
    3. After stripping the prefix, the remainder has
       ≤ :data:`_MAX_CONTENT_TOKENS` non-stopword content tokens.
    4. The query carries no domain-language signal (see
       :func:`_has_domain_language_signal`).
    """
    if query_class != QueryClass.CONCEPT:
        return False
    stripped = query.strip()
    if not stripped:
        return False
    q_lower = stripped.lower()
    remainder = _strip_conceptual_prefix(q_lower)
    if remainder is None:
        return False
    if _content_token_count(remainder) > _MAX_CONTENT_TOKENS:
        return False
    if _has_domain_language_signal(stripped):
        return False
    return True


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------


def maybe_rewrite(query: str, query_class: QueryClass) -> str:
    """Return a domain-language rewrite of ``query``, or ``query`` unchanged.

    Cheap and total: never raises, always returns a string. Order of
    short-circuits (cheapest first):

    1. Feature flag off → return ``query``.
    2. Query empty / whitespace → return ``query`` unchanged.
    3. Pre-check rejects → return ``query``.
    4. LLM call raises or returns empty → log, return ``query``.
    5. Otherwise → return the rewritten string (stripped of surrounding
       whitespace and any wrapping quote marks the model might have added
       despite the system prompt).

    The route layer logs every successful rewrite at INFO level (both
    original and rewritten strings); when ``QueryRequest.debug=True`` the
    rewritten string is also attached to ``QueryResponse.debug_info``.
    """
    if not _is_feature_enabled():
        return query
    if not query or not query.strip():
        return query
    if not _should_rewrite(query, query_class):
        return query

    try:
        rewritten = _call_rewrite_llm(REWRITE_SYSTEM_PROMPT, query)
    except Exception:
        logger.exception(
            "query rewrite failed; passing original through: q=%r", query
        )
        return query

    cleaned = _clean_llm_output(rewritten)
    if not cleaned:
        logger.info(
            "query rewrite returned empty string; passing original through: q=%r",
            query,
        )
        return query
    return cleaned


def _clean_llm_output(raw: str) -> str:
    """Strip whitespace and wrapping quote marks from the LLM's output.

    The system prompt instructs the model to omit quote marks but a small
    fraction of completions still arrive wrapped in ``"..."`` or ``'...'``.
    We strip a single matched pair if present, then trim whitespace again.
    """
    s = (raw or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"', "“", "”"):
        s = s[1:-1].strip()
    return s
