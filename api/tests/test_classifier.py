"""Classifier ground-truth test.

Verification 2: classifier accuracy >= 90% on the 30-case ground-truth set.

The cases cover all six classes:

* concept           — drawn from common_student_phrasings of canonical tutorials.
* solution_lookup   — exam-year-and-question regex patterns the contract pins.
* summary_request   — cram / revision phrasings.
* analytical        — from canonical_queries.md and routing_contract.md.
* image_extracted   — only triggered programmatically by the route layer.
* ambiguous         — analytical keyword + conceptual signal in one query.
"""
from __future__ import annotations

import pytest

from api.orchestrator.classifier import classify, classify_image_extracted
from api.orchestrator.contract import QueryClass

# fmt: off
GROUND_TRUTH: list[tuple[str, QueryClass]] = [
    # ---- concept (10) ----
    ("how do I factorise difference of squares",                              QueryClass.CONCEPT),
    ("what is the common factor of 3x² and 12x",                              QueryClass.CONCEPT),
    ("what's the formula for arithmetic sequence",                            QueryClass.CONCEPT),
    ("how do I find the area of a triangle given the vertices",               QueryClass.CONCEPT),
    ("I got two answers for a, which one is right",                           QueryClass.CONCEPT),
    ("what does the modulus sign mean here",                                  QueryClass.CONCEPT),
    ("how do I simplify a fraction with surds",                               QueryClass.CONCEPT),
    ("what is the chain rule",                                                QueryClass.CONCEPT),
    ("can you walk me through completing the square",                         QueryClass.CONCEPT),
    ("what is integration by parts",                                          QueryClass.CONCEPT),

    # ---- solution_lookup (6) ----
    ("How was 2024 P2 Q5 solved?",                                            QueryClass.SOLUTION_LOOKUP),
    ("2019 paper 1 question 5b",                                              QueryClass.SOLUTION_LOOKUP),
    ("walk me through Q5b from 2023",                                         QueryClass.SOLUTION_LOOKUP),
    ("show me 2022 P2 Q3",                                                    QueryClass.SOLUTION_LOOKUP),
    ("solution to Q4 from 2025",                                              QueryClass.SOLUTION_LOOKUP),
    ("2018 P1 Q7",                                                            QueryClass.SOLUTION_LOOKUP),

    # ---- summary_request (4) ----
    ("I'm cramming The Line tonight — what do I need to know",                QueryClass.SUMMARY_REQUEST),
    ("give me a summary of complex numbers",                                  QueryClass.SUMMARY_REQUEST),
    ("I need a quick revision of statistics",                                 QueryClass.SUMMARY_REQUEST),
    ("tldr probability",                                                      QueryClass.SUMMARY_REQUEST),

    # ---- analytical (8) — canonical_queries.md + routing_contract.md ----
    ("How often has integration by parts appeared on Paper 1 in the last five years?", QueryClass.ANALYTICAL),
    ("Which strands have grown on P2 since 2020?",                            QueryClass.ANALYTICAL),
    ("how many discriminant questions appear on Paper 1 each year",           QueryClass.ANALYTICAL),
    ("what's the average mark allocation for a nature of roots question",     QueryClass.ANALYTICAL),
    ("which P1 tutorial is most cited across all years",                      QueryClass.ANALYTICAL),
    ("what percentage of P2 questions cover trigonometry",                    QueryClass.ANALYTICAL),
    ("compared to integration, how often does differentiation come up on P1", QueryClass.ANALYTICAL),
    ("trend of probability questions on P2",                                  QueryClass.ANALYTICAL),

    # ---- ambiguous (3) — analytical keyword + conceptual keyword ----
    ("Why has differentiation grown so much since 2020?",                     QueryClass.AMBIGUOUS),
    ("explain why integration by parts comes up so often",                    QueryClass.AMBIGUOUS),
    ("how do I prove the trend of declining algebra questions",               QueryClass.AMBIGUOUS),
]
# fmt: on


def test_ground_truth_accuracy_above_90_percent() -> None:
    """The headline verification check: >= 90% on the 30-case ground truth."""
    n = len(GROUND_TRUTH)
    correct = sum(
        1 for q, expected in GROUND_TRUTH if classify(q).query_class == expected
    )
    accuracy = correct / n
    assert n >= 30, "ground truth must have at least 30 rows"
    # Print the misses so a debugging eyeball pass is one test run away.
    if correct < n:
        misses = [
            (q, expected.value, classify(q).query_class.value)
            for q, expected in GROUND_TRUTH
            if classify(q).query_class != expected
        ]
        print("Classifier misses:")
        for q, exp, got in misses:
            print(f"  - {q!r}  expected={exp}  got={got}")
    assert accuracy >= 0.90, (
        f"classifier accuracy {accuracy:.2%} < 90% target on the 30-case ground truth"
    )


def test_ambiguous_requires_both_analytical_and_conceptual() -> None:
    # Lone "why" is NOT ambiguous — it's concept.
    assert classify("why does the chain rule work").query_class == QueryClass.CONCEPT
    # Analytical keyword alone is analytical, not ambiguous.
    assert classify("how often does integration appear on P1").query_class == QueryClass.ANALYTICAL
    # Both signals → ambiguous.
    assert classify("why has integration come up so often since 2020").query_class == QueryClass.AMBIGUOUS


def test_solution_lookup_does_not_swallow_concept_with_year() -> None:
    """"in 2025" inside a concept question shouldn't promote to solution_lookup
    unless there's a paper/question shape next to it."""
    res = classify("what is the chain rule? I'm doing exam prep in 2025")
    assert res.query_class == QueryClass.CONCEPT


def test_classify_image_extracted_always_tags_image_extracted() -> None:
    """Image-extracted queries are tagged image_extracted regardless of the
    underlying text's natural class — that's the route's contract."""
    res = classify_image_extracted("how do I factorise difference of squares")
    assert res.query_class == QueryClass.IMAGE_EXTRACTED


def test_empty_query_falls_through_to_concept() -> None:
    assert classify("").query_class == QueryClass.CONCEPT
    assert classify("   ").query_class == QueryClass.CONCEPT


def test_matched_phrases_returned_when_asked() -> None:
    res = classify("how often does integration appear on P1", return_matches=True)
    assert "how often" in res.matched_phrases


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("how many roots does this cubic have", QueryClass.CONCEPT),  # "how many" but not "questions/parts"
        ("how many integration questions on P1", QueryClass.ANALYTICAL),
        ("how many parts on P2 last year", QueryClass.ANALYTICAL),
    ],
)
def test_how_many_disambiguation(query: str, expected: QueryClass) -> None:
    """The routing_contract.md disambiguation: bare 'how many' shouldn't
    false-positive into analytical."""
    assert classify(query).query_class == expected
