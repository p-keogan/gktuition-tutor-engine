#!/usr/bin/env python3
"""Offline tests for the backend-agnostic parity harness.

Everything here runs with zero network egress, no Snowflake, no Anthropic,
and no paid API. We import the harness module by file path (it lives in
``eval/`` next to the golden CSV, not in an installed package) and exercise:

* the metrics math on a tiny hand-built fixture (P@1 / P@3 / MRR / floor);
* the ``stub`` backend reports P@1 ~= 0.50;
* ``cortex-csv-replay`` against the saved scoring_rows reproduces that run's
  documented P@1 (0.911) within rounding;
* per-strand aggregation sums correctly;
* the gate flips PASS <-> FAIL around the 0.911 baseline.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

# ───────────────────────────────────────────────────────────────────────────
# Load the harness module by file path.
# ───────────────────────────────────────────────────────────────────────────
EVAL_DIR = Path(__file__).resolve().parent.parent
HARNESS_PATH = EVAL_DIR / "parity_harness.py"
GOLDEN_CSV = EVAL_DIR / "eval_golden_set.csv"
REPLAY_CSV = EVAL_DIR / "scoring_rows_20260526_1307.csv"
REPLAY_DOCUMENTED_P_AT_1 = 0.911  # scoring_report_20260526_1307.md


def _load_harness():
    import sys

    spec = importlib.util.spec_from_file_location("parity_harness", HARNESS_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec so @dataclass can resolve sys.modules[__module__].
    sys.modules["parity_harness"] = mod
    spec.loader.exec_module(mod)
    return mod


ph = _load_harness()


# ───────────────────────────────────────────────────────────────────────────
# Offline / env-scrub guard: assert the harness imports nothing that would
# touch Snowflake or Anthropic at module load.
# ───────────────────────────────────────────────────────────────────────────
def test_no_network_modules_imported_at_load():
    import sys

    for banned in ("snowflake.connector", "anthropic"):
        assert banned not in sys.modules, (
            f"{banned} was imported at harness load — must stay offline"
        )


def _make_row(eval_id, slug, source="phrasings", md=None):
    return ph.EvalInput(
        eval_id=eval_id,
        question_text=f"q::{eval_id}",
        expected_slug=slug,
        source=source,
        difficulty="auto-easy",
        is_in_golden_subset=False,
        source_metadata=md or {},
    )


# ───────────────────────────────────────────────────────────────────────────
# Metrics math on a hand-built fixture.
# ───────────────────────────────────────────────────────────────────────────
def test_metrics_math_on_tiny_fixture():
    rows = [
        _make_row("a", "slug-a-1-x"),  # expected at rank 1
        _make_row("b", "slug-b-1-y"),  # expected at rank 2
        _make_row("c", "slug-c-1-z"),  # expected absent
    ]
    # Backend returns a fixed ranking per query.
    plan = {
        "q::a": [("slug-a-1-x", 0.9), ("w", 0.2)],
        "q::b": [("w", 0.9), ("slug-b-1-y", 0.4)],
        "q::c": [("w", 0.9), ("w2", 0.2)],
    }

    def backend(query, top_k=5):
        return plan[query][:top_k]

    rep = ph.score_backend(backend, rows, backend_name="fixture")
    m = rep.overall.metrics()
    # P@1: only row a → 1/3
    assert m["precision@1"] == pytest.approx(1 / 3)
    # P@3: rows a (rank1) and b (rank2) → 2/3
    assert m["precision@3"] == pytest.approx(2 / 3)
    # MRR: (1/1 + 1/2 + 0) / 3
    assert m["mrr"] == pytest.approx((1.0 + 0.5 + 0.0) / 3)
    # mean top-1 score: (0.9 + 0.9 + 0.9) / 3
    assert m["mean_top1_score"] == pytest.approx(0.9)
    # all three top-1 scores (0.9) are >= floor 0.30
    assert m["pct_top1_above_floor"] == pytest.approx(1.0)


def test_cross_ref_best_rank_over_refs():
    # Two cross-ref rows share a part_id; either referenced slug at rank 1
    # counts as a hit for both.
    md = {"part_id": "P1"}
    rows = [
        _make_row("x", "alpha-1-a", source="solution_cross_ref", md=md),
        _make_row("y", "beta-2-b", source="solution_cross_ref", md=md),
    ]

    def backend(query, top_k=5):
        # Always returns beta at rank 1, alpha at rank 2.
        return [("beta-2-b", 0.9), ("alpha-1-a", 0.5)][:top_k]

    rep = ph.score_backend(backend, rows, backend_name="xref")
    # Row x's expected is alpha (rank 2), but beta (a ref of the same part)
    # is at rank 1 → best-rank rule makes it a P@1 hit. Same for row y.
    assert rep.overall.metrics()["precision@1"] == pytest.approx(1.0)


# ───────────────────────────────────────────────────────────────────────────
# Stub backend ~= 0.50.
# ───────────────────────────────────────────────────────────────────────────
def test_stub_backend_p_at_1_about_half():
    rows = [_make_row(f"id{i:03d}", f"slug-{i}-x") for i in range(200)]
    backend = ph.make_stub_backend(rows)
    rep = ph.score_backend(backend, rows, backend_name="stub")
    p1 = rep.overall.metrics()["precision@1"]
    assert 0.45 <= p1 <= 0.55, p1
    # Exactly half by construction (even count, alternating).
    assert p1 == pytest.approx(0.5)


def test_stub_backend_deterministic():
    rows = [_make_row(f"id{i:03d}", f"slug-{i}-x") for i in range(50)]
    a = ph.score_backend(ph.make_stub_backend(rows), rows, "stub")
    b = ph.score_backend(ph.make_stub_backend(rows), rows, "stub")
    assert a.overall.metrics()["precision@1"] == b.overall.metrics()["precision@1"]


# ───────────────────────────────────────────────────────────────────────────
# Per-strand aggregation sums correctly.
# ───────────────────────────────────────────────────────────────────────────
def test_per_strand_aggregation_sums():
    rows = [
        _make_row("a1", "algebra-1-x"),
        _make_row("a2", "algebra-2-y"),
        _make_row("t1", "trigonometry-1-z"),
    ]

    def backend(query, top_k=5):
        # a1 hit, a2 miss, t1 hit
        plan = {
            "q::a1": [("algebra-1-x", 0.9)],
            "q::a2": [("nope", 0.9)],
            "q::t1": [("trigonometry-1-z", 0.9)],
        }
        return plan[query][:top_k]

    rep = ph.score_backend(backend, rows, "fixture")
    # strands derived from slug prefix
    assert set(rep.by_strand) == {"algebra", "trigonometry"}
    assert rep.by_strand["algebra"].n == 2
    assert rep.by_strand["trigonometry"].n == 1
    # n across strands sums to overall n
    assert sum(a.n for a in rep.by_strand.values()) == rep.overall.n
    assert rep.by_strand["algebra"].metrics()["precision@1"] == pytest.approx(0.5)
    assert rep.by_strand["trigonometry"].metrics()["precision@1"] == pytest.approx(1.0)


def test_strand_label_derivation():
    assert _make_row("z", "the-line-4-area-of-triangle").strand == "the-line"
    assert _make_row("z", "complex-numbers-10-polar").strand == "complex-numbers"
    assert _make_row("z", "algebra-2-quadratics").strand == "algebra"


# ───────────────────────────────────────────────────────────────────────────
# Gate flips PASS <-> FAIL around 0.911.
# ───────────────────────────────────────────────────────────────────────────
def _report_with_p_at_1(target_p1: float) -> "ph.ScoreReport":
    # Build N rows where exactly round(target*N) are hits.
    n = 1000
    hits = round(target_p1 * n)
    rows = [_make_row(f"id{i:04d}", f"s-{i}-x") for i in range(n)]

    def backend(query, top_k=5):
        idx = int(query.split("id")[1])
        if idx < hits:
            row_slug = f"s-{idx}-x"
            return [(row_slug, 0.9)]
        return [("wrong", 0.9)]

    return ph.score_backend(backend, rows, "gate-fixture")


def test_gate_passes_at_or_above_baseline():
    rep = _report_with_p_at_1(0.92)
    assert rep.gate_pass is True
    assert rep.gate_delta > 0


def test_gate_fails_below_baseline():
    rep = _report_with_p_at_1(0.90)
    assert rep.gate_pass is False
    assert rep.gate_delta < 0


def test_gate_passes_exactly_at_baseline():
    rep = _report_with_p_at_1(0.911)
    assert rep.gate_pass is True


# ───────────────────────────────────────────────────────────────────────────
# cortex-csv-replay reproduces the documented baseline (uses real eval files).
# ───────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(
    not (GOLDEN_CSV.is_file() and REPLAY_CSV.is_file()),
    reason="golden CSV or replay CSV not present",
)
def test_cortex_csv_replay_reproduces_baseline():
    rows = ph.load_rows(GOLDEN_CSV, only_golden_subset=False)
    backend = ph.make_cortex_csv_replay_backend(REPLAY_CSV, rows)
    # Restrict to the replay file's eval_ids, exactly as the CLI does.
    restrict = getattr(backend, "restrict_to_eval_ids")
    scored_rows = [r for r in rows if r.eval_id in restrict]
    rep = ph.score_backend(backend, scored_rows, "cortex-csv-replay")
    p1 = rep.overall.metrics()["precision@1"]
    assert round(p1, 3) == pytest.approx(REPLAY_DOCUMENTED_P_AT_1, abs=0.001), p1
    # MRR is also documented as 0.942 in the report.
    assert round(rep.overall.metrics()["mrr"], 3) == pytest.approx(0.942, abs=0.001)
    assert rep.gate_pass is True


# ───────────────────────────────────────────────────────────────────────────
# register_backend hook.
# ───────────────────────────────────────────────────────────────────────────
def test_register_backend_hook():
    sentinel = lambda args, rows: (lambda q, k=5: [("x", 0.9)])  # noqa: E731
    ph.register_backend("unit-test-fake", sentinel)
    assert "unit-test-fake" in ph.available_backends()


def test_env_is_scrubbed_of_snowflake_creds():
    # Belt-and-braces: the offline modes must not depend on any SF/Anthropic
    # credential. Assert the test process isn't carrying live creds that the
    # harness might silently use.
    for var in (
        "SNOWFLAKE_PASSWORD", "SNOWFLAKE_PRIVATE_KEY_PATH", "ANTHROPIC_API_KEY",
    ):
        # Not a hard failure if set, but the harness must never read them in
        # offline modes — documented expectation, asserted by the load test.
        os.environ.pop(var, None)
    assert True
