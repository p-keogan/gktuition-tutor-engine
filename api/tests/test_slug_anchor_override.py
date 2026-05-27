"""Tests for the AGENT_22 slug-anchor override.

Covers:

* Unit-level: ``slug_anchor_override`` returns True/False on the
  canonical pension case, below-floor scores, stopword-only overlaps,
  empty retrieval, and with the flag off.
* Bidirectional substring — slug-token in query *and* query-word in slug.
* Internal exceptions never propagate (returns False instead).
* End-to-end through ``synthesize()``: a sub-floor retrieval with a
  matching slug produces a real answer (not the guardrail) once the flag
  is on.
* Above-floor happy path is unperturbed (no override needed).
* Streaming sibling ``synthesize_stream()`` mirrors the same behaviour
  on both the guardrail and the override-fires branches.

The module reads ``SLUG_ANCHOR_OVERRIDE_ENABLED`` on every call, so each
test explicitly sets / clears it via monkeypatch.
"""
from __future__ import annotations

import pytest

from api.orchestrator import synthesizer
from api.orchestrator.contract import (
    Citation,
    QueryClass,
    RetrievalResult,
    RetrievedChunk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _retrieval(slug: str, score: float, *, query_class: QueryClass = QueryClass.CONCEPT) -> RetrievalResult:
    """Build a single-chunk RetrievalResult at the given score."""
    return RetrievalResult(
        query_class=query_class,
        chunks=[RetrievedChunk(slug=slug, snippet="x", score=score)],
        citations=[Citation(slug=slug, title=slug, timestamp_seconds=0, score=score)],
        top_reranker_score=score,
    )


@pytest.fixture
def enabled(monkeypatch) -> None:
    """Turn the override on for the duration of a test."""
    monkeypatch.setenv("SLUG_ANCHOR_OVERRIDE_ENABLED", "true")


@pytest.fixture
def disabled(monkeypatch) -> None:
    """Explicitly clear the flag — the conftest doesn't scrub it."""
    monkeypatch.delenv("SLUG_ANCHOR_OVERRIDE_ENABLED", raising=False)


@pytest.fixture(autouse=True)
def _wire_fakes():
    """Wire fake Cortex / Anthropic callers so the end-to-end tests don't
    try to dial out. Mirrors the autouse pattern in test_synthesizer.py."""
    calls: dict[str, list[tuple[str, ...]]] = {"cortex": [], "anthropic": []}

    def fake_cortex(model: str, prompt: str) -> str:
        calls["cortex"].append((model, prompt))
        return "[cortex] fake answer"

    def fake_anthropic(system_prompt: str, user_prompt: str) -> str:
        calls["anthropic"].append((system_prompt, user_prompt))
        return "[anthropic] fake answer"

    def fake_anthropic_stream(system_prompt, user_prompt):
        yield "[anthropic-stream] "
        yield "fake answer"

    synthesizer.set_cortex_caller(fake_cortex)
    synthesizer.set_anthropic_caller(fake_anthropic)
    synthesizer.set_anthropic_stream_caller(fake_anthropic_stream)
    yield calls
    synthesizer.set_cortex_caller(None)
    synthesizer.set_anthropic_caller(None)
    synthesizer.set_anthropic_stream_caller(None)


# ---------------------------------------------------------------------------
# Unit-level — slug_anchor_override
# ---------------------------------------------------------------------------


def test_fires_for_canonical_pension_case(enabled) -> None:
    """The DAY_31 canonical case — top-1 slug `financial-maths-8-pensions`
    at reranker score 0.030 (well below RETRIEVAL_FLOOR=0.30). The query
    word "pensions" is substring of the slug → override fires."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    assert synthesizer.slug_anchor_override(r, "explain pensions") is True


def test_fires_via_slug_token_in_query_direction(enabled) -> None:
    """Bidirectional check — slug-token ``pension`` appears in the query
    even though the query has the singular form."""
    r = _retrieval("financial-maths-8-pension", 0.030)
    assert synthesizer.slug_anchor_override(r, "what about pensions") is True


def test_below_soft_floor_does_not_fire(enabled) -> None:
    """Score below SLUG_ANCHOR_SOFT_FLOOR is treated as "retriever returned
    literal noise" and the override is suppressed even on a perfect slug
    match. Matches the canonical-fail row in the dispatch's sanity script."""
    r = _retrieval("financial-maths-8-pensions", 0.001)
    assert synthesizer.slug_anchor_override(r, "explain pensions") is False


def test_no_content_word_match_does_not_fire(enabled) -> None:
    """Score above SOFT_FLOOR but no content-word substring overlap →
    no fire. Matches the "hello world" row in the dispatch's sanity script."""
    r = _retrieval("financial-maths-8-pensions", 0.20)
    assert synthesizer.slug_anchor_override(r, "hello world") is False


def test_stopwords_only_overlap_does_not_fire(enabled) -> None:
    """A query made entirely of stopwords ("explain", "the", "what") has
    no content words to match against — override stays silent."""
    r = _retrieval("financial-maths-8-pensions", 0.20)
    assert synthesizer.slug_anchor_override(r, "explain the what") is False


def test_short_content_word_below_minimum_length_does_not_fire(enabled) -> None:
    """Words shorter than ``_SLUG_ANCHOR_MIN_WORD_LEN`` are excluded — e.g.
    "pin" (length 3) doesn't trigger on a slug containing "pin"."""
    # Slug here contains "pin" verbatim, but "pin" is length 3 so the
    # filter drops it. With no other content overlap the override stays off.
    r = _retrieval("probability-with-pin", 0.10)
    assert synthesizer.slug_anchor_override(r, "explain pin") is False


def test_empty_retrieval_does_not_fire(enabled) -> None:
    r = RetrievalResult(
        query_class=QueryClass.CONCEPT,
        chunks=[],
        citations=[],
        top_reranker_score=0.0,
    )
    assert synthesizer.slug_anchor_override(r, "explain pensions") is False


def test_flag_off_does_not_fire_even_on_perfect_match(disabled) -> None:
    """The override ships dark — even a perfect slug match should be False
    when the flag is off."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    assert synthesizer.slug_anchor_override(r, "explain pensions") is False


def test_flag_with_lowercase_false_does_not_fire(monkeypatch) -> None:
    """Explicit "false" must read as False (defensive against env-var typos
    elsewhere flipping behaviour unintentionally)."""
    monkeypatch.setenv("SLUG_ANCHOR_OVERRIDE_ENABLED", "false")
    r = _retrieval("financial-maths-8-pensions", 0.030)
    assert synthesizer.slug_anchor_override(r, "explain pensions") is False


def test_flag_truthy_values_all_enable(monkeypatch) -> None:
    """Accept ``1`` / ``true`` / ``yes`` / ``on`` (case-insensitive)."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    for truthy in ("1", "true", "TRUE", "yes", "On"):
        monkeypatch.setenv("SLUG_ANCHOR_OVERRIDE_ENABLED", truthy)
        assert synthesizer.slug_anchor_override(r, "explain pensions") is True, truthy


# ---------------------------------------------------------------------------
# End-to-end — synthesize()
# ---------------------------------------------------------------------------


def test_synthesize_emits_real_answer_when_override_fires(enabled, _wire_fakes) -> None:
    """Sub-floor retrieval with a matching slug — when the override is on,
    ``synthesize`` should hand off to a real model (not the guardrail)."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    res = synthesizer.synthesize("explain pensions", r)
    assert res.answer != synthesizer.GUARDRAIL_ANSWER
    assert res.model_used != synthesizer.NO_MODEL
    # Cortex was called (cheap path; score is below RETRIEVAL_FLOOR so the
    # cheap-path use_cheap gate is False — falls through to Anthropic).
    assert _wire_fakes["anthropic"], "should fall through to the hard path when below floor"


def test_synthesize_returns_guardrail_when_flag_off(disabled, _wire_fakes) -> None:
    """Same sub-floor retrieval + matching slug, but the flag is off →
    guardrail fires exactly as it did before AGENT_22."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    res = synthesizer.synthesize("explain pensions", r)
    assert res.answer == synthesizer.GUARDRAIL_ANSWER
    assert res.model_used == synthesizer.NO_MODEL
    assert not _wire_fakes["cortex"]
    assert not _wire_fakes["anthropic"]


def test_synthesize_returns_guardrail_when_no_word_match(enabled, _wire_fakes) -> None:
    """Flag on, sub-floor score, but no content-word overlap with the slug
    → guardrail still fires. The override is narrow on purpose."""
    r = _retrieval("financial-maths-8-pensions", 0.10)
    res = synthesizer.synthesize("hello world", r)
    assert res.answer == synthesizer.GUARDRAIL_ANSWER
    assert res.model_used == synthesizer.NO_MODEL


def test_above_floor_unperturbed_by_override(enabled, _wire_fakes) -> None:
    """A query that already meets RETRIEVAL_FLOOR routes through the
    cheap path regardless of the override — no change in behaviour."""
    r = _retrieval("financial-maths-8-pensions", 0.85)
    res = synthesizer.synthesize("explain pensions", r)
    assert res.answer != synthesizer.GUARDRAIL_ANSWER
    # Cheap path because CONCEPT + above floor.
    assert res.model_used == synthesizer.CORTEX_MODEL


# ---------------------------------------------------------------------------
# End-to-end — synthesize_stream() mirror
# ---------------------------------------------------------------------------


def _collect_events(query: str, retrieval: RetrievalResult) -> list[synthesizer.StreamEvent]:
    return list(
        synthesizer.synthesize_stream(
            query, retrieval, token_delay_seconds=0
        )
    )


def test_stream_emits_real_tokens_when_override_fires(enabled) -> None:
    """Streaming path mirrors the non-streaming behaviour — override on +
    sub-floor + slug match → real tokens, not the guardrail string."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    events = _collect_events("explain pensions", r)

    # Find the done event and confirm it's not the (none) model.
    done = [e for e in events if e.event == "done"]
    assert len(done) == 1
    assert done[0].data["model_used"] != synthesizer.NO_MODEL

    # Token text should not be the guardrail string.
    token_text = "".join(
        e.data["text"] for e in events if e.event == "token"
    )
    assert synthesizer.GUARDRAIL_ANSWER not in token_text


def test_stream_emits_guardrail_when_flag_off(disabled) -> None:
    """Streaming guardrail still fires when the flag is off — exactly the
    pre-AGENT_22 behaviour."""
    r = _retrieval("financial-maths-8-pensions", 0.030)
    events = _collect_events("explain pensions", r)

    assert events[0].event == "token"
    assert events[0].data["text"] == synthesizer.GUARDRAIL_ANSWER
    assert events[-1].event == "done"
    assert events[-1].data["model_used"] == synthesizer.NO_MODEL


def test_stream_emits_guardrail_when_no_word_match(enabled) -> None:
    """Flag on, sub-floor, but no slug-anchor overlap → guardrail still
    fires on the streaming path too."""
    r = _retrieval("financial-maths-8-pensions", 0.10)
    events = _collect_events("hello world", r)

    assert events[0].event == "token"
    assert events[0].data["text"] == synthesizer.GUARDRAIL_ANSWER
    assert events[-1].event == "done"
    assert events[-1].data["model_used"] == synthesizer.NO_MODEL


# ---------------------------------------------------------------------------
# Robustness — internal exceptions never propagate
# ---------------------------------------------------------------------------


def test_override_returns_false_on_internal_exception(enabled, monkeypatch) -> None:
    """If something inside the override blows up, the helper must swallow
    and return False — the override is additive UX and must never break
    the request path."""

    # Replace the module-level _SLUG_TOKEN_RE with a fake whose .findall
    # raises. Patching a real re.Pattern's .findall isn't possible (it's a
    # read-only built-in method) so we swap the whole attribute instead.
    class _Boom:
        def findall(self, _s):
            raise RuntimeError("simulated regex failure")

    monkeypatch.setattr(synthesizer, "_SLUG_TOKEN_RE", _Boom())

    bad = RetrievalResult(
        query_class=QueryClass.CONCEPT,
        chunks=[RetrievedChunk(slug="ok", snippet="x", score=0.1)],
        citations=[],
        top_reranker_score=0.1,
    )
    assert synthesizer.slug_anchor_override(bad, "explain ok") is False
