"""Regression: feed the first 50 rows of the eval set through the classifier.

The eval set's first 50 rows (deterministic order) are all ``source =
phrasings`` rows — they were generated from tutorial ``common_student_phrasings``.
Per the contract, those phrasings should classify as ``concept`` since
they're first-exposure conceptual questions. The verification target is
"≥40 land in their expected query_class" — i.e. ≥80% on the phrasings sample.

The test is intentionally tolerant of the exact threshold: the eval set
includes some genuinely-ambiguous phrasings (e.g. "tonight" inside a
phrasing) that legitimately route to summary_request. We assert >= 40/50.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from api.orchestrator.classifier import classify
from api.orchestrator.contract import QueryClass

EVAL_CSV = (
    Path(__file__).resolve().parent.parent.parent
    / "eval"
    / "eval_golden_set.csv"
)


def _first_n_phrasing_rows(n: int) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    with EVAL_CSV.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["source"] != "phrasings":
                continue
            rows.append((r["question_text"], r["expected_slug"]))
            if len(rows) >= n:
                break
    return rows


@pytest.mark.skipif(not EVAL_CSV.exists(), reason="eval_golden_set.csv not present")
def test_eval_regression_first_50_phrasings_classify_as_concept() -> None:
    rows = _first_n_phrasing_rows(50)
    assert len(rows) == 50, f"expected 50 phrasings rows, got {len(rows)}"

    # Most phrasings are conceptual; a handful (e.g. those with "tonight",
    # "revision", or year + "Q") might legitimately match summary_request /
    # solution_lookup. The contract sets the floor at >= 40/50 (80%).
    correct = 0
    misses: list[tuple[str, str]] = []
    for q, _slug in rows:
        cls = classify(q).query_class
        if cls == QueryClass.CONCEPT:
            correct += 1
        else:
            misses.append((q, cls.value))

    if correct < 40:
        print("Eval regression misses (first 50 phrasings):")
        for q, cls in misses:
            print(f"  [{cls}] {q!r}")
    assert correct >= 40, (
        f"Only {correct}/50 phrasings classified as concept (target: >= 40)."
    )
