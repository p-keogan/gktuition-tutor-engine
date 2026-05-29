#!/usr/bin/env python3
"""Backend-agnostic retrieval parity harness — Snowflake-exit Phase 0a.

The *measurement instrument* for the Snowflake exit. It scores **any**
retrieval backend against the golden eval set and frames the result as a
pass/fail against the locked Cortex baseline of **P@1 >= 0.911**, so the
migration decision is a number, not a hunch.

A retrieval backend is any callable matching the shared contract
(``SNOWFLAKE_EXIT_DISPATCH.md``)::

    def retrieve(query: str, top_k: int = 5) -> list[tuple[str, float]]:
        '''Return up to top_k (slug, score) pairs, ranked best-first.
        `score` is calibrated to [0, 1] and directly comparable to
        RETRIEVAL_FLOOR (0.30).'''

The harness never knows or cares whether the backend is Cortex, LanceDB,
or a stub — it only sees that callable. Two reference backends ship with
the harness so it is runnable today with zero deps beyond stdlib + pandas
and zero network egress / spend:

* ``stub`` — returns the expected slug at rank 1 for half the rows and a
  wrong slug for the other half. A deterministic fixture that proves the
  harness math (should report P@1 ~= 0.50). This is the harness's own
  unit-test backend.
* ``cortex-csv-replay`` — replays a saved ``eval/scoring_rows_*.csv``
  (per-row Cortex outputs) as a backend, reproducing the locked baseline
  number offline, with no Snowflake call. Validates the harness against a
  known-good run and gives AGENT_30 an offline baseline to diff against.

The real ``local`` backend (LanceDB + reranker) is supplied later by
AGENT_29/30; the harness accepts it via the ``register_backend(name, fn)``
hook rather than hard-coding it.

Scoring semantics are kept comparable to the production retriever and to
``score_against_cortex_search.py`` (the nightly scorer, which this module
does NOT modify): ``TOP_K = 5``, ``RETRIEVAL_FLOOR = 0.30``, and the
cross-ref "best rank over an exam-part's referenced tutorials" rule. The
``_load_rows_from_csv`` / ``_rank_in_slugs`` / ``_best_rank_over_slugs``
logic is duplicated here (not imported) so this harness never mutates the
file that backs the nightly workflow.

Usage (all offline)
-------------------
::

    # Prove the harness math with the stub backend on the golden subset:
    python eval/parity_harness.py --backend stub --subset

    # Reproduce the locked Cortex baseline offline, no Snowflake:
    python eval/parity_harness.py --backend cortex-csv-replay \\
        --rows eval/scoring_rows_20260526_1307.csv

    # Optional per-strand baselines to flag regressions:
    python eval/parity_harness.py --backend cortex-csv-replay \\
        --rows eval/scoring_rows_20260526_1307.csv \\
        --baseline-strands eval/strand_baselines.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# ───────────────────────────────────────────────────────────────────────────
# Constants — mirror api/orchestrator/retriever.py so the numbers are directly
# comparable. Defined locally (not imported) to keep the harness offline and
# free of the `api` transitive dependency chain (snowflake.connector, etc.).
# ───────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
TOP_K = 5
RETRIEVAL_FLOOR = 0.30
# The locked baseline this gate is measured against (full-set Cortex run,
# scoring_report_20260526_1307.md → P@1 = 0.911).
LOCKED_BASELINE_P_AT_1 = 0.911
# Default margin: a strand whose P@1 drops more than this below its baseline
# is flagged as a regression.
DEFAULT_STRAND_MARGIN = 0.05

DEFAULT_GOLDEN_CSV = HERE / "eval_golden_set.csv"

# ───────────────────────────────────────────────────────────────────────────
# The shared backend contract.
# ───────────────────────────────────────────────────────────────────────────
RetrieveFn = Callable[[str, int], list[tuple[str, float]]]


# ───────────────────────────────────────────────────────────────────────────
# Golden-set row model + loader (logic duplicated from
# score_against_cortex_search.py — intentionally NOT imported so we never
# mutate the file backing the nightly workflow).
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class EvalInput:
    eval_id: str
    question_text: str
    expected_slug: str
    source: str
    difficulty: str
    is_in_golden_subset: bool
    source_metadata: dict[str, Any]

    @property
    def strand(self) -> str:
        """Coarse strand label inferred from the expected_slug prefix.

        Mirrors ``select_golden_subset._strand_of``: the strand is every
        leading slug segment before the first purely-numeric segment, e.g.
        ``the-line-4-area-of-triangle`` → ``the-line``,
        ``algebra-2-factorising-quadratics`` → ``algebra``.
        """
        parts = self.expected_slug.split("-")
        strand_parts: list[str] = []
        for p in parts:
            if p.isdigit():
                break
            strand_parts.append(p)
        return "-".join(strand_parts) or self.expected_slug


def _load_all_rows(csv_path: Path) -> list[EvalInput]:
    """Load every eval row from the golden CSV (no subset filtering).

    The row-parsing logic is duplicated from
    ``score_against_cortex_search._load_rows_from_csv`` so the harness has no
    import-time dependency on that module (and cannot accidentally mutate it).
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    rows: list[EvalInput] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            in_golden = (r.get("is_in_golden_subset") or "FALSE").upper() == "TRUE"
            md_raw = r.get("source_metadata") or "{}"
            try:
                md = json.loads(md_raw)
            except json.JSONDecodeError:
                md = {}
            rows.append(
                EvalInput(
                    eval_id=r["eval_id"],
                    question_text=r["question_text"],
                    expected_slug=r["expected_slug"],
                    source=r["source"],
                    difficulty=r.get("difficulty", ""),
                    is_in_golden_subset=in_golden,
                    source_metadata=md,
                )
            )
    return rows


def _derive_subset_ids(rows: list[EvalInput], seed: int = 20260521) -> set[str]:
    """Reuse ``select_golden_subset``'s stratified selection to pick the
    ~200-row golden subset on the fly.

    The shipped golden CSV may have ``is_in_golden_subset`` unset on every
    row (the flag is normally written by ``select_golden_subset`` against
    Snowflake), so we recompute the same deterministic selection here. The
    module is imported lazily and is offline-safe — its only Snowflake use
    is lazily imported inside writer/loader functions we never call.
    """
    import importlib.util

    sg_path = HERE / "select_golden_subset.py"
    spec = importlib.util.spec_from_file_location("select_golden_subset", sg_path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {sg_path}")
    sg = importlib.util.module_from_spec(spec)
    # Register before exec so the @dataclass decorator can resolve
    # sys.modules[cls.__module__] while the module body runs.
    sys.modules.setdefault("select_golden_subset", sg)
    spec.loader.exec_module(sg)

    min_rows = [
        sg.EvalRowMin(
            eval_id=r.eval_id, expected_slug=r.expected_slug, source=r.source,
            difficulty=r.difficulty, source_metadata=r.source_metadata,
            is_in_golden_subset=r.is_in_golden_subset,
        )
        for r in rows
    ]
    chosen = sg.select_subset(min_rows, seed=seed)
    return {r.eval_id for r in chosen}


def load_rows(
    csv_path: Path, only_golden_subset: bool, seed: int = 20260521,
) -> list[EvalInput]:
    """Load golden rows, optionally restricted to the ~200-row golden subset.

    If ``only_golden_subset`` is set and the CSV already flags rows via
    ``is_in_golden_subset``, those are used. Otherwise the subset is derived
    deterministically with ``select_golden_subset``'s selection.
    """
    rows = _load_all_rows(csv_path)
    if not only_golden_subset:
        return rows
    flagged = [r for r in rows if r.is_in_golden_subset]
    if flagged:
        return flagged
    subset_ids = _derive_subset_ids(rows, seed=seed)
    return [r for r in rows if r.eval_id in subset_ids]


def _build_part_id_to_referenced_slugs(
    rows: list[EvalInput],
) -> dict[str, set[str]]:
    """Group ``solution_cross_ref`` rows by ``part_id`` to recover the full
    ``tutorials_referenced`` set for each exam-part.

    Duplicated from ``score_against_cortex_search`` — used by the cross-ref
    "best rank over refs" rule so any referenced tutorial at rank 1 counts
    as a hit, not just the arbitrarily-pinned ``expected_slug``.
    """
    mapping: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.source != "solution_cross_ref":
            continue
        part_id = row.source_metadata.get("part_id")
        if not part_id:
            continue
        mapping[part_id].add(row.expected_slug)
    return mapping


# ───────────────────────────────────────────────────────────────────────────
# Ranking primitives (duplicated from score_against_cortex_search).
# ───────────────────────────────────────────────────────────────────────────
def _rank_in_slugs(expected: str, slugs: list[str]) -> int | None:
    """1-indexed rank of ``expected`` in ``slugs``; None if absent."""
    for i, s in enumerate(slugs, 1):
        if s == expected:
            return i
    return None


def _best_rank_over_slugs(
    valid_slugs: set[str], ranked: list[str],
) -> int | None:
    """Best (lowest) 1-indexed rank of any slug in ``valid_slugs`` within
    ``ranked``; None if none appear."""
    best: int | None = None
    for slug in valid_slugs:
        rank = _rank_in_slugs(slug, ranked)
        if rank is not None and (best is None or rank < best):
            best = rank
    return best


# ───────────────────────────────────────────────────────────────────────────
# Per-row result + aggregation.
# ───────────────────────────────────────────────────────────────────────────
@dataclass
class RowResult:
    eval_id: str
    source: str
    strand: str
    expected_slug: str
    rank: int | None  # 1-indexed; None if expected not in top-K
    top1_score: float
    p_at_1: int
    p_at_3: int
    mrr: float
    top_k_slugs: list[str]
    error: str | None = None


@dataclass
class Aggregate:
    n: int = 0
    p_at_1_sum: int = 0
    p_at_3_sum: int = 0
    mrr_sum: float = 0.0
    top1_score_sum: float = 0.0
    above_floor_sum: int = 0
    errors: int = 0

    def add(self, r: RowResult) -> None:
        self.n += 1
        if r.error:
            self.errors += 1
            return
        self.p_at_1_sum += r.p_at_1
        self.p_at_3_sum += r.p_at_3
        self.mrr_sum += r.mrr
        self.top1_score_sum += r.top1_score
        self.above_floor_sum += 1 if r.top1_score >= RETRIEVAL_FLOOR else 0

    @property
    def scored(self) -> int:
        return max(self.n - self.errors, 1)

    def metrics(self) -> dict[str, float]:
        s = self.scored
        return {
            "precision@1": self.p_at_1_sum / s,
            "precision@3": self.p_at_3_sum / s,
            "mrr": self.mrr_sum / s,
            "mean_top1_score": self.top1_score_sum / s,
            "pct_top1_above_floor": self.above_floor_sum / s,
        }


# ───────────────────────────────────────────────────────────────────────────
# Core scoring — backend-agnostic.
# ───────────────────────────────────────────────────────────────────────────
def score_row(
    retrieve: RetrieveFn,
    row: EvalInput,
    part_id_to_refs: dict[str, set[str]],
    top_k: int = TOP_K,
) -> RowResult:
    """Score a single golden row against a backend callable."""
    try:
        hits = retrieve(row.question_text, top_k)
    except Exception as exc:  # noqa: BLE001 — a backend error must not abort the run
        return RowResult(
            eval_id=row.eval_id, source=row.source, strand=row.strand,
            expected_slug=row.expected_slug, rank=None, top1_score=0.0,
            p_at_1=0, p_at_3=0, mrr=0.0, top_k_slugs=[], error=str(exc),
        )

    slugs = [slug for slug, _score in hits][:top_k]
    top1_score = hits[0][1] if hits else 0.0

    # Cross-ref rows: any tutorial referenced by the exam-part counts as a
    # hit (best rank over the part's full referenced set). Everything else
    # uses the single expected_slug rank.
    valid_for_row: set[str] | None = None
    if row.source == "solution_cross_ref":
        part_id = row.source_metadata.get("part_id")
        if part_id:
            valid_for_row = part_id_to_refs.get(part_id)
    if valid_for_row:
        rank = _best_rank_over_slugs(valid_for_row, slugs)
    else:
        rank = _rank_in_slugs(row.expected_slug, slugs)

    p_at_1 = 1 if rank == 1 else 0
    p_at_3 = 1 if (rank is not None and rank <= 3) else 0
    mrr = (1.0 / rank) if rank is not None else 0.0
    return RowResult(
        eval_id=row.eval_id, source=row.source, strand=row.strand,
        expected_slug=row.expected_slug, rank=rank, top1_score=top1_score,
        p_at_1=p_at_1, p_at_3=p_at_3, mrr=mrr, top_k_slugs=slugs,
    )


@dataclass
class ScoreReport:
    backend: str
    overall: Aggregate
    by_strand: dict[str, Aggregate]
    by_source: dict[str, Aggregate]
    results: list[RowResult] = field(default_factory=list)
    strand_regressions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def gate_pass(self) -> bool:
        # Compare at the precision the baseline is documented to (3 dp), so a
        # run that reproduces the baseline within rounding (e.g. 0.9107 vs the
        # quoted 0.911) passes rather than failing on a sub-thousandth margin.
        return round(self.overall.metrics()["precision@1"], 3) >= round(
            LOCKED_BASELINE_P_AT_1, 3
        )

    @property
    def gate_delta(self) -> float:
        return self.overall.metrics()["precision@1"] - LOCKED_BASELINE_P_AT_1


def score_backend(
    retrieve: RetrieveFn,
    rows: list[EvalInput],
    backend_name: str,
    top_k: int = TOP_K,
    baseline_strands: dict[str, float] | None = None,
    strand_margin: float = DEFAULT_STRAND_MARGIN,
) -> ScoreReport:
    """Score ``retrieve`` over ``rows`` and assemble the full report."""
    part_id_to_refs = _build_part_id_to_referenced_slugs(rows)

    overall = Aggregate()
    by_strand: dict[str, Aggregate] = defaultdict(Aggregate)
    by_source: dict[str, Aggregate] = defaultdict(Aggregate)
    results: list[RowResult] = []
    for row in rows:
        rr = score_row(retrieve, row, part_id_to_refs, top_k=top_k)
        results.append(rr)
        overall.add(rr)
        by_strand[rr.strand].add(rr)
        by_source[rr.source].add(rr)

    # Per-strand regression flags (only if baselines supplied).
    strand_regressions: list[dict[str, Any]] = []
    if baseline_strands:
        for strand, base_p1 in sorted(baseline_strands.items()):
            agg = by_strand.get(strand)
            if not agg:
                continue
            now_p1 = agg.metrics()["precision@1"]
            drop = base_p1 - now_p1
            if drop > strand_margin:
                strand_regressions.append({
                    "strand": strand,
                    "baseline_p_at_1": base_p1,
                    "p_at_1": now_p1,
                    "delta": -drop,
                    "n": agg.n,
                })

    return ScoreReport(
        backend=backend_name, overall=overall, by_strand=dict(by_strand),
        by_source=dict(by_source), results=results,
        strand_regressions=strand_regressions,
    )


# ───────────────────────────────────────────────────────────────────────────
# Backend registry + the register_backend hook (so AGENT_29/30 can plug in
# the real `local` backend without editing this module).
# ───────────────────────────────────────────────────────────────────────────
# A backend factory takes the parsed argv namespace + the loaded golden rows
# and returns a RetrieveFn. (The replay backend needs the rows to map
# query-text → saved slug list; the stub needs the rows to know the expected
# slug per query.)
BackendFactory = Callable[[argparse.Namespace, list[EvalInput]], RetrieveFn]
_BACKENDS: dict[str, BackendFactory] = {}


def register_backend(name: str, factory: BackendFactory) -> None:
    """Register a backend factory under ``name``.

    The factory is ``(args, rows) -> RetrieveFn``. AGENT_29/30 register the
    real ``local`` backend through this hook; nothing about the local stack
    is hard-coded here.
    """
    _BACKENDS[name] = factory


def available_backends() -> list[str]:
    return sorted(_BACKENDS)


# ───────────────────────────────────────────────────────────────────────────
# Reference backend: stub.
# ───────────────────────────────────────────────────────────────────────────
def make_stub_backend(
    rows: list[EvalInput], wrong_slug: str = "__WRONG__",
) -> RetrieveFn:
    """Deterministic fixture backend: returns the expected slug at rank 1 for
    every other row (sorted by eval_id), a wrong slug for the rest.

    Used as the harness's own unit test — over a reasonable row set it should
    report P@1 ~= 0.50, proving the scoring math end to end. Determinism
    comes from sorting eval_ids and alternating; it does not depend on dict
    ordering or an RNG.
    """
    ordered_ids = sorted(r.eval_id for r in rows)
    correct_at_rank1 = {
        eid: (i % 2 == 0) for i, eid in enumerate(ordered_ids)
    }
    # Map query-text → expected_slug for lookup at call time. For the rare
    # duplicate question_text, the stub's correctness is keyed on whichever
    # row's eval_id we resolve; it only needs to be internally consistent.
    q_to_row: dict[str, EvalInput] = {}
    for r in rows:
        q_to_row.setdefault(r.question_text, r)

    def retrieve(query: str, top_k: int = TOP_K) -> list[tuple[str, float]]:
        row = q_to_row.get(query)
        if row is None:
            return [(wrong_slug, 0.10)]
        if correct_at_rank1.get(row.eval_id, False):
            # Expected slug at rank 1, above the floor.
            return [(row.expected_slug, 0.95), (wrong_slug, 0.20)]
        # Expected slug absent / below; a wrong slug on top.
        return [(wrong_slug, 0.95), (row.expected_slug, 0.20)][:top_k]

    return retrieve


def _stub_factory(
    args: argparse.Namespace, rows: list[EvalInput],
) -> RetrieveFn:
    return make_stub_backend(rows)


# ───────────────────────────────────────────────────────────────────────────
# Reference backend: cortex-csv-replay.
# ───────────────────────────────────────────────────────────────────────────
def make_cortex_csv_replay_backend(
    replay_csv: Path, golden_rows: list[EvalInput],
) -> RetrieveFn:
    """Replay a saved ``scoring_rows_*.csv`` as a backend.

    The saved per-row CSV is keyed by ``eval_id`` and stores the ranked
    ``top_k_slugs`` Cortex returned. The backend contract is query-keyed, so
    we join the replay rows to the golden set (eval_id → question_text) to
    build a ``question_text → ranked slug list`` map. Scores are not stored
    in the replay CSV, so we synthesise a descending [0,1] score per rank
    position (rank 1 well above RETRIEVAL_FLOOR); this preserves ordering
    (the only thing P@1/P@3/MRR depend on) without inventing a distribution.
    """
    if not replay_csv.is_file():
        raise FileNotFoundError(f"replay CSV not found: {replay_csv}")
    id_to_query = {r.eval_id: r.question_text for r in golden_rows}

    q_to_slugs: dict[str, list[str]] = {}
    replay_eval_ids: set[str] = set()
    with replay_csv.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            eid = r["eval_id"]
            query = id_to_query.get(eid)
            if query is None:
                # Replay row whose eval_id is not in the loaded golden set
                # (e.g. a stale/extra row) — skip; it cannot be scored.
                continue
            slugs = [s for s in (r.get("top_k_slugs") or "").split(",") if s]
            q_to_slugs[query] = slugs
            replay_eval_ids.add(eid)

    def _scores_for(slugs: list[str]) -> list[tuple[str, float]]:
        # Descending synthetic scores: 0.95, 0.85, ... clamped at >= floor
        # for the top hit so the "above floor" metric is meaningful.
        out: list[tuple[str, float]] = []
        for i, slug in enumerate(slugs):
            out.append((slug, max(0.95 - 0.1 * i, 0.05)))
        return out

    def retrieve(query: str, top_k: int = TOP_K) -> list[tuple[str, float]]:
        slugs = q_to_slugs.get(query, [])
        return _scores_for(slugs[:top_k])

    # Replay only covers the eval_ids saved in the CSV. Restrict scoring to
    # those rows so the harness reproduces *that run's* documented P@1 rather
    # than counting golden rows the replay never saw as misses. A real
    # backend (e.g. AGENT_29's `local`) sets no such attribute and is scored
    # over the full row set.
    retrieve.restrict_to_eval_ids = replay_eval_ids  # type: ignore[attr-defined]
    return retrieve


def _cortex_csv_replay_factory(
    args: argparse.Namespace, rows: list[EvalInput],
) -> RetrieveFn:
    replay_csv = args.rows
    if replay_csv is None:
        raise SystemExit(
            "--rows <scoring_rows_*.csv> is required for the "
            "cortex-csv-replay backend."
        )
    return make_cortex_csv_replay_backend(Path(replay_csv).resolve(), rows)


register_backend("stub", _stub_factory)
register_backend("cortex-csv-replay", _cortex_csv_replay_factory)


# ───────────────────────────────────────────────────────────────────────────
# Baseline-strands loader (optional --baseline-strands CSV).
# ───────────────────────────────────────────────────────────────────────────
def load_baseline_strands(path: Path) -> dict[str, float]:
    """Load per-strand baseline P@1 from a CSV with columns ``strand`` and
    ``precision@1`` (or ``p_at_1``)."""
    if not path.is_file():
        raise FileNotFoundError(f"baseline-strands CSV not found: {path}")
    out: dict[str, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            strand = (r.get("strand") or "").strip()
            if not strand:
                continue
            raw = r.get("precision@1") or r.get("p_at_1") or ""
            try:
                out[strand] = float(raw)
            except ValueError:
                continue
    return out


# ───────────────────────────────────────────────────────────────────────────
# Reporting — console table + machine-readable JSON.
# ───────────────────────────────────────────────────────────────────────────
def render_console(report: ScoreReport, *, subset: bool, n_rows: int) -> str:
    m = report.overall.metrics()
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"PARITY HARNESS — backend: {report.backend}")
    lines.append(
        f"rows scored: {report.overall.n}  "
        f"(errors: {report.overall.errors})  ·  "
        f"{'golden subset' if subset else 'full eval set'}  ·  "
        f"top-K = {TOP_K}"
    )
    lines.append("=" * 70)
    lines.append("OVERALL")
    lines.append(f"  precision@1          : {m['precision@1']:.3f}")
    lines.append(f"  precision@3          : {m['precision@3']:.3f}")
    lines.append(f"  MRR                  : {m['mrr']:.3f}")
    lines.append(f"  mean top-1 score     : {m['mean_top1_score']:.3f}")
    lines.append(
        f"  % top-1 >= floor({RETRIEVAL_FLOOR:.2f}) : "
        f"{m['pct_top1_above_floor'] * 100:.1f}%"
    )
    lines.append("")
    lines.append("PER-STRAND precision@1 (weakest first)")
    lines.append(f"  {'strand':<34} {'n':>5} {'P@1':>7} {'P@3':>7} {'MRR':>7}")
    lines.append("  " + "-" * 62)
    strand_items = sorted(
        report.by_strand.items(),
        key=lambda kv: kv[1].metrics()["precision@1"],
    )
    for strand, agg in strand_items:
        sm = agg.metrics()
        lines.append(
            f"  {strand[:34]:<34} {agg.n:>5} "
            f"{sm['precision@1']:>7.3f} {sm['precision@3']:>7.3f} "
            f"{sm['mrr']:>7.3f}"
        )
    lines.append("")
    if report.strand_regressions:
        lines.append("STRAND REGRESSIONS (P@1 drop beyond margin vs baseline)")
        for reg in report.strand_regressions:
            lines.append(
                f"  ! {reg['strand']:<30} "
                f"baseline={reg['baseline_p_at_1']:.3f} "
                f"now={reg['p_at_1']:.3f}  Δ={reg['delta']:+.3f}"
            )
        lines.append("")
    # The gate line — prominent.
    if report.gate_pass:
        gate = (
            f"GATE vs locked baseline P@1={LOCKED_BASELINE_P_AT_1:.3f}: "
            f"PASS (Δ={report.gate_delta:+.3f})"
        )
    else:
        gate = (
            f"GATE vs locked baseline P@1={LOCKED_BASELINE_P_AT_1:.3f}: "
            f"FAIL (Δ={report.gate_delta:+.3f})"
        )
    lines.append("#" * 70)
    lines.append(f"  {gate}")
    lines.append("#" * 70)
    return "\n".join(lines)


def build_json_report(
    report: ScoreReport, *, subset: bool,
) -> dict[str, Any]:
    return {
        "backend": report.backend,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "subset": subset,
        "top_k": TOP_K,
        "retrieval_floor": RETRIEVAL_FLOOR,
        "locked_baseline_p_at_1": LOCKED_BASELINE_P_AT_1,
        "rows_scored": report.overall.n,
        "errors": report.overall.errors,
        "overall": report.overall.metrics(),
        "gate": {
            "baseline_p_at_1": LOCKED_BASELINE_P_AT_1,
            "p_at_1": report.overall.metrics()["precision@1"],
            "delta": report.gate_delta,
            "pass": report.gate_pass,
        },
        "by_strand": {
            strand: {**agg.metrics(), "n": agg.n, "errors": agg.errors}
            for strand, agg in sorted(report.by_strand.items())
        },
        "by_source": {
            src: {**agg.metrics(), "n": agg.n, "errors": agg.errors}
            for src, agg in sorted(report.by_source.items())
        },
        "strand_regressions": report.strand_regressions,
    }


# ───────────────────────────────────────────────────────────────────────────
# CLI.
# ───────────────────────────────────────────────────────────────────────────
def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Backend-agnostic retrieval parity harness vs the locked "
                    "P@1 baseline. Fully offline.",
    )
    ap.add_argument(
        "--backend", required=True,
        help=f"Backend to score. Registered: {', '.join(available_backends())}.",
    )
    ap.add_argument(
        "--golden-csv", type=Path, default=DEFAULT_GOLDEN_CSV,
        help="Golden eval set CSV. Default: eval/eval_golden_set.csv.",
    )
    ap.add_argument(
        "--subset", action="store_true",
        help="Score only the ~200-row golden subset "
             "(is_in_golden_subset = TRUE).",
    )
    ap.add_argument(
        "--rows", type=Path, default=None,
        help="For cortex-csv-replay: the saved scoring_rows_*.csv to replay.",
    )
    ap.add_argument(
        "--baseline-strands", type=Path, default=None,
        help="Optional CSV of per-strand baseline P@1 (columns: strand, "
             "precision@1). If given, strands dropping more than --strand-margin "
             "below baseline are flagged.",
    )
    ap.add_argument(
        "--strand-margin", type=float, default=DEFAULT_STRAND_MARGIN,
        help=f"Per-strand regression margin (default {DEFAULT_STRAND_MARGIN}).",
    )
    ap.add_argument(
        "--out-dir", type=Path, default=HERE,
        help="Where to write the JSON report. Default: eval/.",
    )
    ap.add_argument(
        "--no-report", action="store_true",
        help="Skip writing the JSON report file (console only).",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    if args.backend not in _BACKENDS:
        print(
            f"Unknown backend '{args.backend}'. "
            f"Registered: {', '.join(available_backends())}.",
            file=sys.stderr,
        )
        return 2

    rows = load_rows(args.golden_csv.resolve(), args.subset)
    if not rows:
        print("No rows loaded — check --golden-csv / --subset.", file=sys.stderr)
        return 2

    retrieve = _BACKENDS[args.backend](args, rows)

    # A backend may restrict scoring to a subset of eval_ids (the replay
    # backend only covers the rows saved in its CSV).
    restrict = getattr(retrieve, "restrict_to_eval_ids", None)
    if restrict is not None:
        rows = [r for r in rows if r.eval_id in restrict]

    baseline_strands = (
        load_baseline_strands(args.baseline_strands.resolve())
        if args.baseline_strands else None
    )

    report = score_backend(
        retrieve, rows, backend_name=args.backend,
        baseline_strands=baseline_strands, strand_margin=args.strand_margin,
    )

    print(render_console(report, subset=args.subset, n_rows=len(rows)))

    if not args.no_report:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_backend = args.backend.replace("/", "_")
        out_path = args.out_dir / f"parity_report_{safe_backend}_{stamp}.json"
        out_path.write_text(
            json.dumps(build_json_report(report, subset=args.subset), indent=2)
            + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {out_path}")

    # Exit non-zero on gate FAIL so CI / callers can branch on it.
    return 0 if report.gate_pass else 1


if __name__ == "__main__":
    sys.exit(main())
