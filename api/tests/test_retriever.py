"""Retriever tests — uses a fake Snowflake cursor + fake analyst caller."""
from __future__ import annotations

import json
from typing import Any

import pytest

from api.orchestrator import retriever
from api.orchestrator.contract import QueryClass

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_search_results(service: str, query: str) -> list[dict[str, Any]]:
    """Tiny in-memory fixture — three slugs per service with monotonically
    decreasing reranker scores.

    Response shape matches the live Cortex Search Preview output verified
    against TUTOR_SEARCH on 2026-05-25 (see ``scripts/sniff_cortex.py``):
    scores live under ``@scores``, not at the top level. The previous
    fixture put a flat ``score`` field at the top level, which masked a
    production bug — the parser read ``hit.get('score')`` and got None,
    so every chunk landed at score=0.0 in prod and tripped the
    synthesis confidence gate.
    """
    if "TUTOR_SEARCH" in service:
        return [
            {"slug": "algebra-1-revision-of-jc-factorising", "title": "Algebra 1",
             "body": "factorising prose...", "topic": "algebra",
             "@scores": {"reranker_score": 2.45, "cosine_similarity": 0.63,
                         "text_match": 0.44}},
            {"slug": "algebra-2-factorising-quadratics", "title": "Algebra 2",
             "body": "...", "topic": "algebra",
             "@scores": {"reranker_score": 1.05, "cosine_similarity": 0.51,
                         "text_match": 0.31}},
        ]
    if "SOLUTIONS_SEARCH" in service:
        return [
            {"part_id": "2024_main_P2_Q5a", "topic": "vectors",
             "question_text": "Find the coordinates of B and C.",
             "solution_text": "...",
             "tutorials_referenced": ["the-line-4-area-of-triangle"],
             "@scores": {"reranker_score": 1.99, "cosine_similarity": 0.58,
                         "text_match": 0.42}},
        ]
    if "SUMMARY_SEARCH" in service:
        return [
            {"summary_id": "summary-the-line", "strand_name": "The Line",
             "body": "Cram sheet body.",
             "@scores": {"reranker_score": 1.46, "cosine_similarity": 0.55,
                         "text_match": 0.38}},
        ]
    return []


class _FakeCursor:
    def __init__(self) -> None:
        self._last: list[Any] = []
        self.description: list[tuple[str, ...]] | None = None

    def execute(self, sql: str, params: Any = None) -> None:
        if "SEARCH_PREVIEW" in sql:
            service, payload_json = params
            payload = json.loads(payload_json)
            hits = _fake_search_results(service, payload["query"])
            # The retriever expects PARSE_JSON → ARRAY → list[dict].
            self._last = [(hits,)]
        else:
            # SQL execution branch (Analyst flow). Pretend the warehouse
            # returned a single row.
            self._last = [("integration_by_parts", 5)]
            self.description = [("topic_raw",), ("parts_count",)]

    def fetchone(self) -> Any:
        return self._last[0] if self._last else None

    def fetchall(self) -> list[Any]:
        return list(self._last)

    def close(self) -> None:
        pass


class _FakeConn:
    def cursor(self) -> _FakeCursor:
        return _FakeCursor()

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _wire_fakes():
    retriever.set_snowflake_connection(_FakeConn())
    yield
    retriever.set_snowflake_connection(None)
    retriever.set_analyst_caller(None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_concept_hits_tutor_search_only() -> None:
    res = await retriever.retrieve(
        "how do I factorise difference of squares", QueryClass.CONCEPT
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert retriever.SOLUTIONS_SEARCH not in res.services_called
    assert res.chunks[0].slug == "algebra-1-revision-of-jc-factorising"
    # Top hit's raw reranker_score = 2.45 → sigmoid ≈ 0.9205. Well above
    # RETRIEVAL_FLOOR=0.30, so the synthesizer takes the grounded path
    # rather than the "I'm not sure" fallback — which was the production
    # regression this test exists to pin.
    assert res.top_reranker_score == pytest.approx(0.9205, abs=2e-3)
    assert res.top_reranker_score > retriever.RETRIEVAL_FLOOR


@pytest.mark.asyncio
async def test_solution_lookup_hits_solutions_search_only() -> None:
    res = await retriever.retrieve("2024 P2 Q5", QueryClass.SOLUTION_LOOKUP)
    assert retriever.SOLUTIONS_SEARCH in res.services_called
    assert "2024_main_P2_Q5a" in [c.slug for c in res.chunks]


@pytest.mark.asyncio
async def test_summary_request_hits_summary_search_only() -> None:
    res = await retriever.retrieve("cramming the line", QueryClass.SUMMARY_REQUEST)
    assert retriever.SUMMARY_SEARCH in res.services_called
    assert res.citations[0].title == "The Line"


@pytest.mark.asyncio
async def test_analytical_calls_analyst_only_no_search_services() -> None:
    called: list[str] = []

    def fake_analyst(q: str) -> retriever.AnalystResponse:
        called.append(q)
        return retriever.AnalystResponse(
            sql="SELECT 1", rows=[{"topic_raw": "integration", "parts_count": 5}]
        )

    retriever.set_analyst_caller(fake_analyst)
    res = await retriever.retrieve(
        "how often does integration appear on P1", QueryClass.ANALYTICAL,
    )
    assert called == ["how often does integration appear on P1"]
    assert "cortex.analyst" in res.services_called
    assert retriever.TUTOR_SEARCH not in res.services_called
    assert res.analyst_rows[0]["parts_count"] == 5
    assert res.analyst_sql == "SELECT 1"


@pytest.mark.asyncio
async def test_ambiguous_fans_out_to_all_services() -> None:
    retriever.set_analyst_caller(
        lambda q: retriever.AnalystResponse(sql="SELECT 1", rows=[])
    )
    res = await retriever.retrieve(
        "why has integration grown since 2020", QueryClass.AMBIGUOUS,
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert retriever.SOLUTIONS_SEARCH in res.services_called
    assert retriever.SUMMARY_SEARCH in res.services_called
    assert "cortex.analyst" in res.services_called
    # chunks should be deduped by slug and sorted by score.
    slugs = [c.slug for c in res.chunks]
    assert len(slugs) == len(set(slugs))


@pytest.mark.asyncio
async def test_image_extracted_acts_like_concept() -> None:
    res = await retriever.retrieve(
        "how do I factorise difference of squares", QueryClass.IMAGE_EXTRACTED,
    )
    assert retriever.TUTOR_SEARCH in res.services_called
    assert res.chunks


def test_extract_reranker_score_handles_real_response_shape() -> None:
    """Regression test pinned against the live Cortex response shape.

    This is the exact dict shape returned by SEARCH_PREVIEW (verified
    2026-05-25 via scripts/sniff_cortex.py). Friday's parser read
    ``hit.get('score')`` and returned None → 0.0 → tripped the synthesis
    confidence gate on every concept query. This test would have caught
    that.
    """
    real_hit = {
        "slug": "algebra-1-revision-of-jc-factorising",
        "title": "Algebra 1 — Revision Of Junior Cert Factorising",
        "@scores": {
            "reranker_score": 2.4509184,
            "cosine_similarity": 0.6312332,
            "text_match": 0.43972465,
        },
    }
    assert retriever._extract_reranker_score(real_hit) == pytest.approx(
        2.4509184, abs=1e-6
    )

    # Falls back to cosine_similarity if reranker_score is missing.
    no_reranker = {"@scores": {"cosine_similarity": 0.42}}
    assert retriever._extract_reranker_score(no_reranker) == pytest.approx(
        0.42, abs=1e-6
    )

    # Falls back to flat ``score`` (test-fixture compatibility path).
    flat = {"score": 0.5}
    assert retriever._extract_reranker_score(flat) == pytest.approx(0.5, abs=1e-6)

    # Defensive: missing / None / non-numeric all return 0.
    assert retriever._extract_reranker_score({}) == 0.0
    assert retriever._extract_reranker_score({"@scores": None}) == 0.0
    assert retriever._extract_reranker_score({"score": None}) == 0.0
    assert retriever._extract_reranker_score({"score": "not-a-number"}) == 0.0


def test_sigmoid_normalize_calibration() -> None:
    """Pin the sigmoid calibration so future score-related tuning is
    visible at review time. RETRIEVAL_FLOOR is 0.30 — calibration must
    keep neutral-or-better reranker scores above it."""
    assert retriever._sigmoid_normalize(0.0) == pytest.approx(0.5, abs=1e-6)
    assert retriever._sigmoid_normalize(2.0) == pytest.approx(0.8808, abs=1e-3)
    assert retriever._sigmoid_normalize(-2.0) == pytest.approx(0.1192, abs=1e-3)
    # Neutral score should land above RETRIEVAL_FLOOR (synthesise, not fallback)
    assert retriever._sigmoid_normalize(0.0) > retriever.RETRIEVAL_FLOOR
    # Strongly-negative reranker should land below RETRIEVAL_FLOOR (fallback)
    assert retriever._sigmoid_normalize(-2.0) < retriever.RETRIEVAL_FLOOR
    # NaN guard
    assert retriever._sigmoid_normalize(float("nan")) == 0.0
    # Overflow guards
    assert retriever._sigmoid_normalize(1000.0) == 1.0
    assert retriever._sigmoid_normalize(-1000.0) == 0.0


def test_blended_score_arithmetic_pins_default_weights() -> None:
    """Pin the default ``(w_r=0.6, w_c=0.3, w_t=0.1)`` blend against known
    inputs so a future weight change is visible at review time.

    Picks the same canonical Algebra 1 hit that exercises the reranker-fix
    regression test (raw reranker = 2.4509184). Walking through the
    arithmetic for documentation:

        sigmoid(2.4509184) ≈ 0.9205
        cosine             = 0.6312332
        text_match         = 0.43972465
        blended = 0.6*0.9205 + 0.3*0.6312332 + 0.1*0.43972465
                ≈ 0.5523 + 0.1894 + 0.0440
                ≈ 0.7857
    """
    hit = {
        "slug": "algebra-1-revision-of-jc-factorising",
        "@scores": {
            "reranker_score": 2.4509184,
            "cosine_similarity": 0.6312332,
            "text_match": 0.43972465,
        },
    }
    assert retriever._blended_score(hit) == pytest.approx(0.7857, abs=2e-3)

    # At reranker=0 (sigmoid=0.5), the reranker leg alone contributes
    # 0.6 * 0.5 = 0.3 — i.e. lands exactly at RETRIEVAL_FLOOR. Any positive
    # cosine or text-match nudges it above the floor.
    only_reranker_zero = {
        "@scores": {"reranker_score": 0.0, "cosine_similarity": 0.0,
                    "text_match": 0.0}
    }
    assert retriever._blended_score(only_reranker_zero) == pytest.approx(
        0.6 * 0.5, abs=1e-6,
    )

    # Strongly-negative reranker (sigmoid ≈ 0.12), no cosine/text_match
    # support → blended ≈ 0.07, well below RETRIEVAL_FLOOR. Confirms the
    # blend can still demote a low-confidence hit.
    weak = {
        "@scores": {"reranker_score": -2.0, "cosine_similarity": 0.0,
                    "text_match": 0.0}
    }
    assert retriever._blended_score(weak) == pytest.approx(
        0.6 * 0.1192, abs=2e-3,
    )

    # Defensive: missing @scores block → defaults to sigmoid(0)*w_r only.
    # Cosine + text_match both fall to 0 silently rather than crashing.
    assert retriever._blended_score({}) == pytest.approx(
        0.6 * 0.5,  # sigmoid(0) = 0.5
        abs=1e-6,
    )


def test_blended_scoring_disabled_by_default(monkeypatch) -> None:
    """The feature flag is off unless explicitly enabled. ``_normalise_score``
    must produce the same value as the pre-blended sigmoid path until the
    flag is flipped — this guards against an accidental default flip.
    """
    monkeypatch.delenv("BLENDED_SCORING_ENABLED", raising=False)
    assert retriever._blended_scoring_enabled() is False
    hit = {
        "@scores": {
            "reranker_score": 2.4509184,
            "cosine_similarity": 0.6312332,
            "text_match": 0.43972465,
        },
    }
    # Sigmoid path returns ≈0.9205; blended returns ≈0.7857. They must differ.
    flag_off = retriever._normalise_score(hit)
    monkeypatch.setenv("BLENDED_SCORING_ENABLED", "true")
    assert retriever._blended_scoring_enabled() is True
    flag_on = retriever._normalise_score(hit)
    assert flag_off == pytest.approx(0.9205, abs=2e-3)
    assert flag_on == pytest.approx(0.7857, abs=2e-3)
    assert flag_off != flag_on


def test_blended_scoring_flag_parses_common_truthy_values(monkeypatch) -> None:
    """The flag accepts any of {true, 1, yes, on}, case-insensitive — matches
    the convention used elsewhere in the firewall config.
    """
    for v in ("true", "TRUE", "True", "1", "yes", "YES", "on"):
        monkeypatch.setenv("BLENDED_SCORING_ENABLED", v)
        assert retriever._blended_scoring_enabled() is True, f"failed for {v!r}"
    for v in ("false", "0", "no", "off", ""):
        monkeypatch.setenv("BLENDED_SCORING_ENABLED", v)
        assert retriever._blended_scoring_enabled() is False, f"failed for {v!r}"


def test_extract_cosine_and_text_match_defensive() -> None:
    """``_extract_cosine_similarity`` and ``_extract_text_match`` must both
    handle missing / malformed ``@scores`` blocks gracefully — they're used
    inside the blended score and a single NaN would silently poison a row's
    rank.
    """
    assert retriever._extract_cosine_similarity({}) == 0.0
    assert retriever._extract_cosine_similarity({"@scores": None}) == 0.0
    assert retriever._extract_cosine_similarity(
        {"@scores": {"cosine_similarity": "not-a-number"}}
    ) == 0.0
    assert retriever._extract_cosine_similarity(
        {"@scores": {"cosine_similarity": float("nan")}}
    ) == 0.0
    assert retriever._extract_cosine_similarity(
        {"@scores": {"cosine_similarity": 0.42}}
    ) == pytest.approx(0.42, abs=1e-6)

    assert retriever._extract_text_match({}) == 0.0
    assert retriever._extract_text_match({"@scores": None}) == 0.0
    assert retriever._extract_text_match(
        {"@scores": {"text_match": "boom"}}
    ) == 0.0
    assert retriever._extract_text_match(
        {"@scores": {"text_match": 0.31}}
    ) == pytest.approx(0.31, abs=1e-6)
