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

There are two public entry-points: :func:`maybe_rewrite` (the iter-1
pre-retrieval path) and :func:`maybe_rewrite_fallback` (the iter-2
post-retrieval fallback path added by AGENT_24).

:func:`maybe_rewrite` returns the rewritten query when *all* of the
following hold, and the original query otherwise:

* ``QUERY_REWRITE_ENABLED`` is truthy in the environment (read every
  call, so flipping the Fly secret takes effect without a restart),
* ``query_class == QueryClass.CONCEPT``,
* the deterministic pre-check accepts the query as a short conceptual
  framing,
* the LLM call succeeds and returns a non-empty string.

:func:`maybe_rewrite_fallback` is a separate, looser-gated path the
route layer calls *only* after a first retrieve has come back below
``RETRIEVAL_FLOOR``. Drops AGENT_21's conceptual-prefix gate so
single-word queries like ``"circumcentre"`` (which scored sub-floor on
the first try because the slug uses ``"circumcircle"``) get a second
chance. Gated by ``QUERY_REWRITE_FALLBACK_ENABLED``, orthogonal to the
iter-1 flag.

Both functions never raise. On any exception the original query is
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

#: Maximum non-stopword content tokens for the AGENT_24 *fallback*
#: pre-check. Wider than ``_MAX_CONTENT_TOKENS`` (4) because the fallback
#: drops AGENT_21's conceptual-prefix gate — a bare ``"circumcentre"`` has
#: 1 content token, and ``"explain the circumcentre"`` has 2 — but a full
#: sentence in domain language ("derive the present value of a four-year
#: annuity") would still trip the cap and be skipped. The looser bound is
#: safe here because the fallback only fires when retrieval already
#: missed: there is no first-attempt cost to widening the gate.
_MAX_FALLBACK_CONTENT_TOKENS = 6

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

#: Env var that gates the AGENT_24 fallback path independently of the
#: iter-1 pre-retrieval rewrite. Kept orthogonal so iter-1 and iter-2 can
#: be flipped (or rolled back) in isolation. Read on every call for the
#: same reason as :data:`_FEATURE_FLAG_ENV`.
_FALLBACK_FEATURE_FLAG_ENV = "QUERY_REWRITE_FALLBACK_ENABLED"


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


# ---------------------------------------------------------------------------
# AGENT_24 — fallback rewrite path
# ---------------------------------------------------------------------------
#
# DAY_32 evening surfaced a residual failure mode in iter-1: queries that
# don't begin with one of ``_CONCEPTUAL_PREFIXES`` (e.g. the single-word
# ``"circumcentre"``) skip the rewriter entirely, and on the first
# retrieval the reranker scores them sub-floor — so the guardrail fires
# even though the corpus *does* contain the right material (just under a
# lexically-different slug, in this case ``circumcircle``). The right
# response is to retrieve *first*, and only call the LLM when the first
# attempt actually misses. That keeps the per-query cost at zero on the
# ~99% of queries that retrieve cleanly on the first try, while letting a
# wider class of queries benefit from a rewrite when they need it.
#
# This sibling path is purely additive — :func:`maybe_rewrite` is
# unchanged. The two functions are gated by independent env flags so
# iter-1 and iter-2 can be rolled out and rolled back independently.


def _is_fallback_feature_enabled() -> bool:
    """Truthy-string check on ``QUERY_REWRITE_FALLBACK_ENABLED``.

    Same recognised values as :func:`_is_feature_enabled` (``"1"``,
    ``"true"``, ``"yes"``, ``"on"``; case-insensitive). Anything else —
    including unset — disables the fallback layer.
    """
    raw = os.environ.get(_FALLBACK_FEATURE_FLAG_ENV, "")
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _should_rewrite_fallback(query: str, query_class: QueryClass) -> bool:
    """Deterministic pre-check for the fallback path.

    Looser than :func:`_should_rewrite` in two specific ways:

    1. **No conceptual-prefix gate.** Single-word queries like
       ``"circumcentre"`` and bare-noun framings like
       ``"orthocentre"`` pass — which is the whole point of the
       fallback. AGENT_21's tighter pre-check filters those out
       because firing the LLM on every concept query upfront would be
       wasteful; the fallback only fires after a retrieval miss, so the
       cost calculus is different.
    2. **Wider content-token cap** (``_MAX_FALLBACK_CONTENT_TOKENS = 6``
       vs iter-1's ``4``). A 5-6 token bare-noun fragment is still
       plausibly a rewriteable target; a longer query is almost
       certainly already in domain language.

    The same domain-language exclusions as iter-1 still apply (no ``=``
    / ``²`` / ``√`` / LaTeX / "prove" / "derive" etc.) — if the query
    already carries domain signals, rewriting it would risk drifting
    intent without addressing the actual retrieval miss.
    """
    if query_class != QueryClass.CONCEPT:
        return False
    stripped = query.strip()
    if not stripped:
        return False
    # No prefix strip — the whole point of the fallback path is to admit
    # queries that AGENT_21's prefix gate filtered out. Count tokens on
    # the lower-cased query directly.
    if _content_token_count(stripped.lower()) > _MAX_FALLBACK_CONTENT_TOKENS:
        return False
    if _has_domain_language_signal(stripped):
        return False
    return True


def maybe_rewrite_fallback(query: str, query_class: QueryClass) -> str:
    """Sibling of :func:`maybe_rewrite` for the post-retrieval fallback path.

    Same total contract as :func:`maybe_rewrite` — never raises, always
    returns a string. Differences from the iter-1 entrypoint:

    * Gated by ``QUERY_REWRITE_FALLBACK_ENABLED`` (NOT
      ``QUERY_REWRITE_ENABLED``) so the two paths can be flipped
      independently.
    * Uses :func:`_should_rewrite_fallback` (looser pre-check; no prefix
      gate; wider content-token cap).
    * Reuses the same system prompt, LLM caller, and output-cleaner as
      iter-1 — once the gate is passed, the actual translation step is
      identical work.

    Intended caller: the orchestrator route (both
    ``routes/query.py:_run_query`` and ``firewall/wire.py:run_with_firewall``)
    invokes this *only* after the first ``retrieve`` call has come back
    with ``top_reranker_score < RETRIEVAL_FLOOR`` AND the first attempt
    was the un-rewritten query (i.e. AGENT_21's iter-1 path did not
    already rewrite). The route layer is responsible for that gate; this
    function is total over its inputs.

    Order of short-circuits (cheapest first):

    1. Fallback flag off → return ``query``.
    2. Query empty / whitespace → return ``query`` unchanged.
    3. Fallback pre-check rejects → return ``query``.
    4. LLM call raises or returns empty → log, return ``query``.
    5. Otherwise → return the rewritten string (whitespace + wrapping
       quote marks stripped).
    """
    if not _is_fallback_feature_enabled():
        return query
    if not query or not query.strip():
        return query
    if not _should_rewrite_fallback(query, query_class):
        return query

    try:
        rewritten = _call_rewrite_llm(REWRITE_SYSTEM_PROMPT, query)
    except Exception:
        logger.exception(
            "fallback query rewrite failed; passing original through: q=%r",
            query,
        )
        return query

    cleaned = _clean_llm_output(rewritten)
    if not cleaned:
        logger.info(
            "fallback query rewrite returned empty string; "
            "passing original through: q=%r",
            query,
        )
        return query
    return cleaned


# ---------------------------------------------------------------------------
# Topic-extraction retrieval — for image-extracted / long exam questions
# ---------------------------------------------------------------------------
#
# Distinct from maybe_rewrite / maybe_rewrite_fallback (which target SHORT
# concept fragments). A photographed or pasted exam question is long and full
# of surface terms ("numbers", "form", "∈ Q", specific values), so a
# full-question embedding ranks the wrong tutorials. Here we distil the
# question to its core topic+method and retrieve on THAT. The caller uses the
# result ONLY to drive retrieval; synthesis still answers the full question.

_IMAGE_TOPIC_FLAG_ENV = "IMAGE_TOPIC_RETRIEVAL_ENABLED"

TOPIC_EXTRACTION_SYSTEM_PROMPT = (
    "You are a Leaving Cert Higher Level (LCHL) Maths retrieval assistant. You "
    "are given the text of a maths exam question. Reply with ONE short phrase "
    "(at most ~12 words) naming the core topic and method the question tests, "
    "in standard LCHL terminology, suitable for searching a tutorial library. "
    "Examples:\n"
    "- 'Write 64, 1/16, 2 in the form 4^r' -> indices: writing numbers as powers with rational exponents\n"
    "- 'Integrate g''(x)=30x-18, slope -2 at (-1,8), find g(x)' -> integration: finding a function from its second derivative using an initial condition\n"
    "- 'Use de Moivre to find (3 - sqrt(3) i)^8' -> complex numbers: de Moivre's theorem and polar form\n"
    "Output ONLY the phrase. No preamble, no quotes, no markdown."
)


def _is_image_topic_enabled() -> bool:
    """Default ON. Only an explicit false-y value disables topic extraction."""
    raw = os.environ.get(_IMAGE_TOPIC_FLAG_ENV, "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def extract_topic_for_retrieval(query: str) -> str:
    """Distil a long/exam question to a short topic phrase for retrieval.

    Returns the topic phrase, or the original ``query`` if disabled or on any
    failure. NEVER raises. Used ONLY to drive retrieval — synthesis answers the
    full original question.
    """
    if not _is_image_topic_enabled():
        return query
    if not query or not query.strip():
        return query
    try:
        raw = _call_rewrite_llm(TOPIC_EXTRACTION_SYSTEM_PROMPT, query.strip())
    except Exception:
        logger.exception(
            "topic extraction failed; using original query: q=%r", query[:120]
        )
        return query
    phrase = _clean_llm_output(raw)
    # Guard against a degenerate (empty) or non-distilled (too-long) response.
    if not phrase or len(phrase) > 200:
        return query
    logger.info("topic-extraction: q=%r -> retrieval=%r", query[:80], phrase)
    return phrase
