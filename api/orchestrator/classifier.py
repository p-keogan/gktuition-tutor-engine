"""Deterministic intent classifier — implementation of ``routing_contract.md``.

Pure Python: keyword + regex, no LLM call, sub-millisecond latency. The
emitted ``QueryClass`` decides which retrieval surface(s) the orchestrator
calls. See ``snowflake/cortex_analyst/routing_contract.md`` for the rationale
behind every entry in ``ANALYTICAL_KEYWORDS`` and ``ANALYTICAL_REGEXES``.

If this classifier ever needs to be promoted to LLM-backed, the route labels
(``QueryClass``) are the stable contract — the implementation is swap-in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .contract import QueryClass

# ---------------------------------------------------------------------------
# Keyword + regex sets — verbatim from routing_contract.md
# ---------------------------------------------------------------------------
# The analytical bucket is keyword-matched on substrings (lowercased).
ANALYTICAL_KEYWORDS: tuple[str, ...] = (
    "how often",
    "how many times",
    "frequency",
    "what percentage",
    "percentage of",
    "proportion of",
    "average marks",
    "mean marks",
    "marks per part",
    "trend",
    "trends",
    "year-over-year",
    "year over year",
    "compared to",
    " versus ",
    " vs ",
    " vs. ",
    "deferred vs main",
    "which strand has",
    "which strands have",
    "most cited",
    "most-cited",
    "most often",
    "appearance count",
    "appearance counts",
    "how common",
    "how frequently",
)

# Regexes that the contract pins explicitly (case-insensitive).
ANALYTICAL_REGEXES: tuple[re.Pattern[str], ...] = (
    # "how many <X> questions/parts/appearances/times" — the contract's
    # disambiguation against incidental "how many" usage like "how many roots".
    re.compile(r"\bhow many\b.*\b(questions|parts|appearances|times)\b", re.IGNORECASE),
    # "since 20XX" with the digit prefix narrowing the match.
    re.compile(r"\bsince\s+20\d{2}\b", re.IGNORECASE),
    # "in the last N years" — both numeric and word forms.
    re.compile(
        r"\bin the last\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+years\b",
        re.IGNORECASE,
    ),
)

# Conceptual signals — when present alongside an analytical match, the route
# becomes "ambiguous" (fan out to both paths). Verbatim per routing_contract.md.
CONCEPTUAL_SIGNALS: tuple[str, ...] = (
    "why",
    "explain",
    "how does",
    "how do i",
    "prove",
)

# Solution-lookup regex — recognises exam-paper references in any of the forms
# students actually use. Each pattern is checked case-insensitively.
#
# Examples that should hit:
#   "How was 2024 P2 Q5 solved?"            -> year + paper + question
#   "2019 paper 1 question 5b"
#   "show me 2022 deferred P2 Q3(c)(ii)"
#   "solve 2025 main P1 Q4"
#   "walk me through Q5b from 2023"
SOLUTION_LOOKUP_REGEXES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(19|20)\d{2}\b.*\b(p|paper)\s*[12]\b.*\bq\s*\d+", re.IGNORECASE),
    re.compile(r"\b(p|paper)\s*[12]\b.*\bq\s*\d+.*\b(19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"\bq\s*\d+[a-z]?(?:\([a-z]+\))*\b.*\b(from|in|on)\b.*\b(19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"\b(19|20)\d{2}\b.*\bq\s*\d+[a-z]?\b", re.IGNORECASE),
    re.compile(r"\b(walk me through|show me|solve|solution to|how was)\b.*\bq\s*\d+", re.IGNORECASE),
)

# Summary-request signals.
SUMMARY_SIGNALS: tuple[str, ...] = (
    "cram",
    "cramming",
    "revision",
    "revise",
    "i need to revise",
    "summary of",
    "summarise",
    "summarize",
    "overview of",
    "what do i need to know",
    "what's important",
    "what is important",
    "what should i focus",
    "tonight",  # student vernacular for "I have an exam tomorrow"
    "exam tomorrow",
    "exam next week",
    "in a rush",
    "quick refresher",
    "tldr",
    "tl;dr",
)


@dataclass(frozen=True)
class ClassificationResult:
    """Output of ``classify``.

    The ``matched_phrases`` field is populated only when the caller passes
    ``return_matches=True`` — it's a debug aid surfaced via ``debug_info`` in
    the API response.
    """

    query_class: QueryClass
    matched_phrases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify(query: str, *, return_matches: bool = False) -> ClassificationResult:
    """Classify ``query`` into a ``QueryClass``.

    Algorithm (mirrors ``routing_contract.md``):

    1. **Analytical detection** — substring scan + regex scan for any of the
       analytical keywords / patterns.
    2. **Conceptual-signal detection** — substring scan for ``why``, ``explain``,
       ``how does``, ``how do i``, ``prove``.
    3. **Solution-lookup detection** — regex scan for year × paper × question
       references.
    4. **Summary-request detection** — substring scan for cram / revise / TLDR /
       tonight-style signals.
    5. **Resolution:**
       * analytical + conceptual ⇒ ``ambiguous``
       * analytical only          ⇒ ``analytical``
       * solution_lookup only     ⇒ ``solution_lookup``
       * summary_signal only      ⇒ ``summary_request``
       * else                     ⇒ ``concept`` (default)

    The empty / whitespace string falls through to ``concept`` rather than
    raising — the FastAPI layer enforces non-empty via Pydantic.
    """
    if not query or not query.strip():
        return ClassificationResult(QueryClass.CONCEPT)

    q_lower = query.lower()
    matches: list[str] = []

    # --- 1. analytical ----------------------------------------------------
    analytical_hits: list[str] = []
    for kw in ANALYTICAL_KEYWORDS:
        if kw.strip() in q_lower or kw in q_lower:
            analytical_hits.append(kw.strip())
    for pat in ANALYTICAL_REGEXES:
        m = pat.search(query)
        if m:
            analytical_hits.append(m.group(0).strip())
    is_analytical = bool(analytical_hits)

    # --- 2. conceptual signals (for ambiguous resolution) ----------------
    conceptual_hits: list[str] = [s for s in CONCEPTUAL_SIGNALS if _word_in(s, q_lower)]
    is_conceptual_signal = bool(conceptual_hits)

    # --- 3. solution lookup ----------------------------------------------
    solution_lookup_hits: list[str] = []
    for pat in SOLUTION_LOOKUP_REGEXES:
        m = pat.search(query)
        if m:
            solution_lookup_hits.append(m.group(0).strip())
    is_solution_lookup = bool(solution_lookup_hits)

    # --- 4. summary request ----------------------------------------------
    summary_hits: list[str] = [s for s in SUMMARY_SIGNALS if s in q_lower]
    is_summary_request = bool(summary_hits)

    # --- 5. resolve ------------------------------------------------------
    if is_analytical and is_conceptual_signal:
        matches = analytical_hits + conceptual_hits
        return _result(QueryClass.AMBIGUOUS, matches, return_matches)

    if is_analytical:
        # Analytical wins outright when there's no concurrent conceptual cue,
        # even if there's a summary or solution_lookup signal. The Analyst
        # is the cheapest correct answer for "how many" / "how often" / "since
        # 2020" — sending those to RAG would be a deliberate downgrade.
        return _result(QueryClass.ANALYTICAL, analytical_hits, return_matches)

    if is_solution_lookup:
        return _result(QueryClass.SOLUTION_LOOKUP, solution_lookup_hits, return_matches)

    if is_summary_request:
        return _result(QueryClass.SUMMARY_REQUEST, summary_hits, return_matches)

    return _result(QueryClass.CONCEPT, [], return_matches)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _word_in(needle: str, haystack: str) -> bool:
    """Word-boundary-aware containment check.

    ``"why"`` should not match ``"whyalla"``. ``"prove"`` should not match
    ``"approve"``. For multi-word needles (``"how do i"``) the boundary check
    is at both ends.
    """
    # Already-lowered haystack.
    pat = r"\b" + re.escape(needle) + r"\b"
    return re.search(pat, haystack) is not None


def _result(
    qc: QueryClass, hits: list[str], return_matches: bool
) -> ClassificationResult:
    if return_matches:
        return ClassificationResult(qc, tuple(dict.fromkeys(hits)))  # de-dup, keep order
    return ClassificationResult(qc)


def classify_image_extracted(extracted_text: str) -> ClassificationResult:
    """Variant for queries whose text was extracted from an image.

    Per ADR-004 Decision 3, image_extracted queries are funneled through the
    standard classifier; the only difference is that the route surface tags
    the response with ``query_class = image_extracted`` so the widget knows
    the request originated from a photo. Internally we treat the underlying
    text as a normal query for routing purposes — concept fallback if no
    other signal fires.
    """
    res = classify(extracted_text)
    return ClassificationResult(
        QueryClass.IMAGE_EXTRACTED,
        res.matched_phrases,
    )
