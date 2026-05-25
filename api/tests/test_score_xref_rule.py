"""Regression tests for the eval scorer's cross-ref recall@1-over-refs rule.

A cross-ref eval row whose exam-part references multiple tutorials is a
hit if **any** of those tutorials lands at rank 1 in the flattened
SOLUTIONS_SEARCH result — not just the arbitrarily-pinned
``expected_slug``. See AGENT_20 delivery + eval/README.md for the
rationale (the eval set builder emits one row per ``(part_id, slug)``
pair, picking one slug as expected is artificial when the other
``tutorials_referenced`` entries are equally legitimate cross-refs).

These tests pin the behaviour of the helpers added to
``eval/score_against_cortex_search.py`` so future refactors can't
silently revert to the legacy "exact expected_slug at rank 1" rule.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

# ``eval/`` is not a package — load the scorer module by file path. This
# mirrors the pattern used by other ``api/tests/test_eval_*`` files that
# cross the eval-layer boundary.
_SCORER_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "eval"
    / "score_against_cortex_search.py"
)
_SCORER_MOD_NAME = "_score_against_cortex_search_under_test"


def _load_scorer():
    # Cache on sys.modules so dataclass ``__module__`` lookups in the loaded
    # module resolve cleanly — without this CPython 3.10's dataclasses helper
    # tries to introspect ``sys.modules.get(cls.__module__).__dict__`` and
    # crashes with AttributeError.
    if _SCORER_MOD_NAME in sys.modules:
        return sys.modules[_SCORER_MOD_NAME]
    spec = importlib.util.spec_from_file_location(
        _SCORER_MOD_NAME, _SCORER_PATH,
    )
    assert spec is not None and spec.loader is not None, (
        f"Failed to load scorer from {_SCORER_PATH}"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_SCORER_MOD_NAME] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# _best_rank_over_slugs — the core new helper
# ---------------------------------------------------------------------------


def test_best_rank_over_slugs_returns_lowest_rank_of_any_valid_slug() -> None:
    """If a row's ``tutorials_referenced`` set is {A, B} and B is at rank 1
    in the flattened SOLUTIONS_SEARCH results, the row is a hit at rank 1.
    """
    mod = _load_scorer()
    ranked = ["B", "C", "A"]
    valid = {"A", "B"}
    assert mod._best_rank_over_slugs(valid, ranked) == 1


def test_best_rank_over_slugs_handles_only_one_slug_present() -> None:
    mod = _load_scorer()
    ranked = ["X", "Y", "A"]
    valid = {"A", "B"}
    # A is at rank 3, B is absent — best rank is 3.
    assert mod._best_rank_over_slugs(valid, ranked) == 3


def test_best_rank_over_slugs_returns_none_when_no_valid_slug_present() -> None:
    mod = _load_scorer()
    ranked = ["X", "Y", "Z"]
    valid = {"A", "B"}
    assert mod._best_rank_over_slugs(valid, ranked) is None


def test_best_rank_over_slugs_returns_none_for_empty_valid_set() -> None:
    mod = _load_scorer()
    assert mod._best_rank_over_slugs(set(), ["A", "B"]) is None


# ---------------------------------------------------------------------------
# _build_part_id_to_referenced_slugs — the grouping helper that feeds the
# new rule from the loaded eval rows
# ---------------------------------------------------------------------------


def test_build_part_id_to_referenced_slugs_groups_xref_rows() -> None:
    mod = _load_scorer()
    rows = [
        mod.EvalInput(
            eval_id="xref_part_A_slug_X",
            question_text="q1", expected_slug="slug_X",
            source="solution_cross_ref", difficulty="auto-medium",
            is_in_golden_subset=True,
            source_metadata={"part_id": "part_A"},
        ),
        mod.EvalInput(
            eval_id="xref_part_A_slug_Y",
            question_text="q1", expected_slug="slug_Y",
            source="solution_cross_ref", difficulty="auto-medium",
            is_in_golden_subset=True,
            source_metadata={"part_id": "part_A"},
        ),
        mod.EvalInput(
            eval_id="xref_part_B_slug_Z",
            question_text="q2", expected_slug="slug_Z",
            source="solution_cross_ref", difficulty="auto-easy",
            is_in_golden_subset=True,
            source_metadata={"part_id": "part_B"},
        ),
        # phrasings rows are skipped by the grouper:
        mod.EvalInput(
            eval_id="phr_slug_X_001",
            question_text="phrasing", expected_slug="slug_X",
            source="phrasings", difficulty="auto-easy",
            is_in_golden_subset=False,
            source_metadata={"topic": "algebra"},
        ),
    ]
    grouped = mod._build_part_id_to_referenced_slugs(rows)
    assert grouped["part_A"] == {"slug_X", "slug_Y"}
    assert grouped["part_B"] == {"slug_Z"}
    assert "phrasings" not in grouped  # never indexed by source
    # No spurious entries for phrasing-only sources:
    assert set(grouped.keys()) == {"part_A", "part_B"}


# ---------------------------------------------------------------------------
# _score_solutions_search — end-to-end pin with a fake cursor
# ---------------------------------------------------------------------------


class _FakeCursor:
    """Captures the last query and returns a canned SOLUTIONS_SEARCH response."""

    def __init__(self, hits: list[dict[str, Any]]) -> None:
        self._hits = hits
        self._last_returned: list[dict[str, Any]] | None = None

    def execute(self, _sql: str, _params: tuple[Any, ...]) -> None:
        # The scorer wraps the hits in a single-row tuple under PARSE_JSON.
        self._last_returned = self._hits

    def fetchone(self) -> tuple[Any]:
        import json as _json
        return (_json.dumps(self._last_returned),)


def test_score_solutions_search_hits_at_rank_1_when_any_valid_slug_wins() -> None:
    """Pins the dispatch's prediction: an Algebra cross-ref row whose
    ``tutorials_referenced`` = ["A", "B"] is a hit at rank 1 when "B"
    (a sibling, not the arbitrarily-pinned expected_slug) lands first.
    Without the new rule the row would be scored as rank 2 (the position
    of "A" in the flattened ranking).
    """
    mod = _load_scorer()
    # Two-tutorials-per-part setup: the eval row picks "A" as expected; the
    # exam-part's `tutorials_referenced` includes both "A" and "B".
    hits = [
        {
            "part_id": "p1", "topic": "algebra",
            "tutorials_referenced": ["B", "A"],
        },
    ]
    cursor = _FakeCursor(hits)
    row = mod.EvalInput(
        eval_id="xref_p1_A",
        question_text="some exam question",
        expected_slug="A",
        source="solution_cross_ref", difficulty="auto-medium",
        is_in_golden_subset=True,
        source_metadata={"part_id": "p1"},
    )
    valid_for_row = {"A", "B"}
    result = mod._score_solutions_search(
        cursor, row, also_try_tutor=False,
        valid_slugs_for_row=valid_for_row,
    )
    assert result.rank == 1, (
        "With the new rule, returning sibling B at rank 1 counts as a hit "
        "for an eval row whose expected_slug=A but whose part references both."
    )
    assert result.p_at_1 == 1
    assert result.r_at_5 == 1
    assert pytest.approx(result.mrr, abs=1e-6) == 1.0


def test_score_solutions_search_falls_back_to_legacy_rule_when_no_valid_set() -> None:
    """When ``valid_slugs_for_row`` is None or empty, fall back to the
    legacy single-expected-slug rule — preserves backward compatibility
    for any caller that wires the scorer without grouping eval rows."""
    mod = _load_scorer()
    hits = [
        {
            "part_id": "p1", "topic": "algebra",
            "tutorials_referenced": ["B", "A"],
        },
    ]
    cursor = _FakeCursor(hits)
    row = mod.EvalInput(
        eval_id="xref_p1_A",
        question_text="q",
        expected_slug="A",
        source="solution_cross_ref", difficulty="auto-medium",
        is_in_golden_subset=True,
        source_metadata={"part_id": "p1"},
    )
    # No valid_slugs_for_row → legacy rule → A is at rank 2.
    result = mod._score_solutions_search(
        cursor, row, also_try_tutor=False, valid_slugs_for_row=None,
    )
    assert result.rank == 2
    assert result.p_at_1 == 0
    assert result.r_at_5 == 1
