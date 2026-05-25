"""Voice-anchor tests.

Phase 2 / AGENT_15 — the synthesiser prepends a strand cram-summary + the
``_voice.md`` rules to every generation prompt. These tests exercise the
pure-function surface of ``api.orchestrator.voice_anchor`` plus the
injection point in the synthesiser.

The corpus files live in a sibling repo
(``career-transition-2026/tutorials/``); the tests build a synthetic corpus
on disk under ``tmp_path`` and point ``CORPUS_ROOT`` at it, so the suite
never depends on the real corpus existing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from api.orchestrator import synthesizer, voice_anchor
from api.orchestrator.contract import (
    QueryClass,
    RetrievalResult,
    RetrievedChunk,
)

# ---------------------------------------------------------------------------
# Cache hygiene — each test gets a fresh memoisation table.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_voice_caches() -> None:
    voice_anchor._clear_caches()


# ---------------------------------------------------------------------------
# Fake-corpus builder
# ---------------------------------------------------------------------------


def _build_corpus(
    tmp_path: Path,
    *,
    voice_md: str | None = "VOICE_RULES_BODY",
    summaries: dict[str, str] | None = None,
) -> Path:
    """Build ``tmp_path/career-transition-2026/tutorials/...`` with the
    requested ``_voice.md`` and per-strand ``_SUMMARY-exam-cram.md`` files.
    Returns the corpus root (the parent of ``tutorials``).
    """
    root = tmp_path / "career-transition-2026"
    tutorials = root / "tutorials"
    tutorials.mkdir(parents=True)
    if voice_md is not None:
        (tutorials / voice_anchor.VOICE_GUIDE_FILENAME).write_text(voice_md, encoding="utf-8")
    for strand, body in (summaries or {}).items():
        strand_dir = tutorials / strand
        strand_dir.mkdir()
        (strand_dir / voice_anchor.SUMMARY_FILENAME).write_text(body, encoding="utf-8")
    return root


def _retrieval_with_slug(slug: str, *, query_class: QueryClass = QueryClass.CONCEPT) -> RetrievalResult:
    return RetrievalResult(
        query_class=query_class,
        chunks=[RetrievedChunk(slug=slug, snippet="snip", score=0.85)],
        citations=[],
        top_reranker_score=0.85,
    )


# ---------------------------------------------------------------------------
# Slug → strand mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug,expected",
    [
        ("algebra-1-revision-of-jc-factorising", "LCHL_Algebra"),
        ("algebra-22-abstract-inequalities", "LCHL_Algebra"),
        ("number-theory-3-proof-root-2-irrational", "LCHL_Number_Theory"),
        ("statistics-17-confidence-intervals", "LCHL_Statistics"),
        ("trigonometry-1-1-pythagoras-theorem", "LCHL_Trigonometry_1"),
        ("trigonometry-2-3-radians-and-the-unit-circle", "LCHL_Trigonometry_2"),
        ("trigonometry-4-0-miscellaneous", "LCHL_Trigonometry_4"),
        ("avm-1-3-trapezoidal-rule", "LCHL_AVM_1"),
        ("geometry-1-1-axioms-theorems-corollaries", "LCHL_Geometry_1"),
        ("sequences-series-1-arithmetic-sequences-1", "LCHL_Sequences_and_Series"),
        ("the-line-1-jc-revision", "LCHL_The_Line"),
        ("the-circle-1-introduction", "LCHL_The_Circle"),
        ("indices-logs-1-jc-revision", "LCHL_Indices_and_Logs"),
        ("complex-numbers-1-introduction", "LCHL_Complex_Numbers"),
        ("financial-maths-1-simple-interest", "LCHL_Financial_Maths"),
        ("functions-graphs-1-jc-revision", "LCHL_Functions_and_Graphs"),
        ("induction-1-introduction", "LCHL_Induction"),
        ("integration-1-algebra", "LCHL_Integration"),
        ("probability-1-jc-revision", "LCHL_Probability"),
        ("differentiation-1-introduction", "LCHL_Differentiation"),
    ],
)
def test_infer_strand_from_slug_hits(slug: str, expected: str) -> None:
    assert voice_anchor.infer_strand_from_slug(slug) == expected


@pytest.mark.parametrize(
    "slug",
    [
        "",
        "2023_P1_solutions",          # solution-side: no strand prefix
        "AGENT_PROMPT_p2_solutions",  # author-only artefact
        "totally-made-up",
        "some-other-strand-99",
    ],
)
def test_infer_strand_from_slug_misses(slug: str) -> None:
    assert voice_anchor.infer_strand_from_slug(slug) is None


# ---------------------------------------------------------------------------
# 4 brief-mandated build_voice_anchor cases
# ---------------------------------------------------------------------------


def test_anchor_present_when_strand_has_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Top-1 hit lands in a strand with a summary; anchor present."""
    root = _build_corpus(
        tmp_path,
        voice_md="ALWAYS-END-WITH-THEREFORE",
        summaries={"LCHL_Algebra": "FACTORISE-FIRST"},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    retrieval = _retrieval_with_slug("algebra-1-revision-of-jc-factorising")
    anchor = voice_anchor.build_voice_anchor(retrieval)

    assert anchor is not None
    # Strand context block AND voice rules block are both injected.
    assert "STRAND CONTEXT" in anchor
    assert "LCHL_Algebra" in anchor
    assert "FACTORISE-FIRST" in anchor
    assert "VOICE RULES" in anchor
    assert "ALWAYS-END-WITH-THEREFORE" in anchor


def test_anchor_voice_only_when_strand_summary_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Top-1 hit lands in a strand that has no summary file; voice rules
    still inject, but the strand block is skipped silently."""
    root = _build_corpus(
        tmp_path,
        voice_md="ALWAYS-END-WITH-THEREFORE",
        summaries={},  # no per-strand summaries
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    retrieval = _retrieval_with_slug("algebra-1-revision-of-jc-factorising")
    anchor = voice_anchor.build_voice_anchor(retrieval)

    assert anchor is not None
    assert "STRAND CONTEXT" not in anchor
    assert "VOICE RULES" in anchor
    assert "ALWAYS-END-WITH-THEREFORE" in anchor


def test_anchor_none_when_voice_guide_missing_and_no_strand(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No ``_voice.md`` AND retrieval doesn't map to any strand → no anchor."""
    root = _build_corpus(tmp_path, voice_md=None, summaries={})
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    # Solution-side slug has no strand prefix.
    retrieval = _retrieval_with_slug("2023_P1_solutions")
    anchor = voice_anchor.build_voice_anchor(retrieval)
    assert anchor is None


def test_anchor_none_when_corpus_root_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-existent CORPUS_ROOT must not crash; returns ``None`` cleanly."""
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(tmp_path / "does-not-exist"))

    retrieval = _retrieval_with_slug("algebra-1-revision-of-jc-factorising")
    anchor = voice_anchor.build_voice_anchor(retrieval)
    assert anchor is None


# ---------------------------------------------------------------------------
# build_voice_anchor edge cases
# ---------------------------------------------------------------------------


def test_anchor_none_for_empty_retrieval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No retrieved chunks → no anchor (even if voice + summaries exist)."""
    root = _build_corpus(
        tmp_path,
        voice_md="VOICE",
        summaries={"LCHL_Algebra": "SUMMARY"},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    retrieval = RetrievalResult(
        query_class=QueryClass.CONCEPT,
        chunks=[],
        citations=[],
        top_reranker_score=0.0,
    )
    # With no chunks, infer_strand_from_retrieval is None; but voice rules
    # still apply. The current contract treats "no chunks" as guardrail,
    # but build_voice_anchor is purer than that — it returns the voice
    # block alone.
    anchor = voice_anchor.build_voice_anchor(retrieval)
    assert anchor is not None
    assert "VOICE RULES" in anchor
    assert "STRAND CONTEXT" not in anchor


def test_summary_truncation_respects_max_chars(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A huge summary file is truncated; the prefix stays within budget."""
    huge_summary = "\n\n".join(
        f"## Section {i}\n\n" + ("x " * 500) for i in range(40)
    )
    root = _build_corpus(
        tmp_path,
        voice_md="V",
        summaries={"LCHL_Algebra": huge_summary},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    retrieval = _retrieval_with_slug("algebra-1-revision-of-jc-factorising")
    anchor = voice_anchor.build_voice_anchor(retrieval, max_chars=4_000)
    assert anchor is not None
    # Two thirds of 4_000 = 2666 chars for the summary block; the markdown
    # framing adds ~400 chars. Generous ceiling here just to confirm we
    # didn't paste the whole 200KB summary.
    assert len(anchor) < 6_000
    assert "[...truncated for prompt-length budget]" in anchor


def test_memoisation_avoids_repeated_filesystem_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second call for the same strand uses the cache (no second read)."""
    root = _build_corpus(
        tmp_path,
        voice_md="V",
        summaries={"LCHL_Algebra": "S"},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    a1 = voice_anchor.load_strand_summary("LCHL_Algebra")
    # Wipe the file from disk; cache should still serve the value.
    (root / "tutorials" / "LCHL_Algebra" / voice_anchor.SUMMARY_FILENAME).unlink()
    a2 = voice_anchor.load_strand_summary("LCHL_Algebra")
    assert a1 == a2 == "S"


def test_infer_strand_from_retrieval_uses_top_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the top-1 chunk's slug drives the strand decision."""
    retrieval = RetrievalResult(
        query_class=QueryClass.CONCEPT,
        chunks=[
            RetrievedChunk(slug="statistics-17-confidence-intervals", snippet="a", score=0.9),
            RetrievedChunk(slug="algebra-1-revision-of-jc-factorising", snippet="b", score=0.8),
        ],
        citations=[],
        top_reranker_score=0.9,
    )
    assert voice_anchor.infer_strand_from_retrieval(retrieval) == "LCHL_Statistics"


# ---------------------------------------------------------------------------
# Synthesiser integration — the anchor reaches the LLM prompt
# ---------------------------------------------------------------------------


def test_synth_anthropic_path_receives_voice_anchored_system_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Anthropic path's system prompt = SYSTEM_PROMPT + anchor."""
    root = _build_corpus(
        tmp_path,
        voice_md="VOICE_RULES_BODY_FROM_VOICE_MD",
        summaries={"LCHL_Algebra": "STRAND_BODY_FOR_ALGEBRA"},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    captured: list[tuple[str, str]] = []

    def fake_anthropic(system_prompt: str, user_prompt: str) -> str:
        captured.append((system_prompt, user_prompt))
        return "factorise then verify."

    synthesizer.set_anthropic_caller(fake_anthropic)
    try:
        retrieval = RetrievalResult(
            query_class=QueryClass.SOLUTION_LOOKUP,  # routes to Anthropic
            chunks=[
                RetrievedChunk(
                    slug="algebra-1-revision-of-jc-factorising",
                    snippet="dots",
                    score=0.85,
                )
            ],
            citations=[],
            top_reranker_score=0.85,
        )
        synthesizer.synthesize("how do I factorise", retrieval)
    finally:
        synthesizer.set_anthropic_caller(None)

    assert captured, "fake anthropic was never called"
    system_prompt, _ = captured[0]
    # Base rules preserved.
    assert "GKTuition's AI maths tutor" in system_prompt
    # Voice anchor injected.
    assert "STRAND_BODY_FOR_ALGEBRA" in system_prompt
    assert "VOICE_RULES_BODY_FROM_VOICE_MD" in system_prompt


def test_synth_cortex_path_receives_voice_anchored_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Cortex (soft) path's inlined prompt also carries the anchor."""
    root = _build_corpus(
        tmp_path,
        voice_md="VOICE_BODY",
        summaries={"LCHL_Statistics": "STATS_STRAND_BODY"},
    )
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(root))

    captured: list[tuple[str, str]] = []

    def fake_cortex(model: str, prompt: str) -> str:
        captured.append((model, prompt))
        return "see statistics-17."

    synthesizer.set_cortex_caller(fake_cortex)
    try:
        retrieval = RetrievalResult(
            query_class=QueryClass.CONCEPT,  # routes to cheap path
            chunks=[
                RetrievedChunk(
                    slug="statistics-17-confidence-intervals",
                    snippet="margin",
                    score=0.85,
                )
            ],
            citations=[],
            top_reranker_score=0.85,
        )
        synthesizer.synthesize("what is a CI", retrieval)
    finally:
        synthesizer.set_cortex_caller(None)

    assert captured, "fake cortex was never called"
    _, prompt = captured[0]
    assert "STATS_STRAND_BODY" in prompt
    assert "VOICE_BODY" in prompt


def test_synth_falls_back_cleanly_when_corpus_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing corpus → synth still runs; bare SYSTEM_PROMPT used."""
    monkeypatch.setenv(voice_anchor.CORPUS_ROOT_ENV, str(tmp_path / "nope"))

    captured: list[tuple[str, str]] = []

    def fake_anthropic(system_prompt: str, user_prompt: str) -> str:
        captured.append((system_prompt, user_prompt))
        return "answer."

    synthesizer.set_anthropic_caller(fake_anthropic)
    try:
        retrieval = RetrievalResult(
            query_class=QueryClass.SOLUTION_LOOKUP,
            chunks=[
                RetrievedChunk(
                    slug="algebra-1-revision-of-jc-factorising",
                    snippet="x",
                    score=0.85,
                )
            ],
            citations=[],
            top_reranker_score=0.85,
        )
        res = synthesizer.synthesize("q", retrieval)
    finally:
        synthesizer.set_anthropic_caller(None)

    assert res.model_used == synthesizer.ANTHROPIC_MODEL
    system_prompt, _ = captured[0]
    # No anchor → system prompt is the bare SYSTEM_PROMPT, no anchor markers.
    assert "STRAND CONTEXT" not in system_prompt
    assert "VOICE RULES" not in system_prompt
    # But base rules still present.
    assert "GKTuition's AI maths tutor" in system_prompt
