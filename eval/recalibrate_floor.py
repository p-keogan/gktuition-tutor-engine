#!/usr/bin/env python3
"""Floor / blended-weight recalibration analysis — Snowflake-exit Phase-0b.

ANALYSIS ONLY. Recommends a ``RETRIEVAL_FLOOR`` (and, where useful, blended
weights) for the *local* score distribution, which differs from the Cortex
reranker distribution the live floor (0.30) was tuned to. Emits recommendations
for Phase 2b — it does NOT touch live code.

Method
------
The live floor exists to reject answers too weak to ground a response. Cortex's
floor 0.30 sits far below its score mass (mean top-1 ≈ 0.95), so it admits
~100% of true positives and only trims the genuine "I don't know" tail. To
preserve that *same precision/recall trade-off* on a new backend we put the
floor at the score threshold that admits the same fraction of true positives —
operationalised as a low percentile (default 5th) of the correct-row top-1
score distribution — and report the precision/recall the threshold yields.

Reads the checkpoints written by ``run_local_parity.py`` (no model needed) and
re-derives per-row correctness with the harness's own ``score_row`` so the
numbers match the parity reports exactly.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import parity_harness as ph  # noqa: E402

CKPT_DIR = Path(os.environ.get("LOCAL_PARITY_CKPT_DIR", str(HERE / "_local_parity_ckpt")))
CORTEX_FLOOR = 0.30
ADMIT_TP_PCTL = 5  # admit ~95% of true positives → floor at 5th pctl of TP scores


def _load_ckpt(backend: str) -> dict[str, list[tuple[str, float]]]:
    path = CKPT_DIR / f"{backend}.jsonl"
    out: dict[str, list[tuple[str, float]]] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            out[rec["eval_id"]] = [(s, float(sc)) for s, sc in rec["hits"]]
    return out


def _percentile(xs: list[float], pctl: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * (pctl / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def analyse(backend: str) -> dict:
    all_rows = ph._load_all_rows(ph.DEFAULT_GOLDEN_CSV)
    refs = ph._build_part_id_to_referenced_slugs(all_rows)
    ckpt = _load_ckpt(backend)
    rows = [r for r in all_rows if r.eval_id in ckpt]

    tp_scores: list[float] = []   # top-1 score on rows where rank-1 is correct
    fp_scores: list[float] = []   # top-1 score on rows where rank-1 is wrong
    for r in rows:
        hits = ckpt[r.eval_id]
        rr = ph.score_row(lambda q, k, _h=hits: _h, r, refs, top_k=5)
        top1 = hits[0][1] if hits else 0.0
        (tp_scores if rr.p_at_1 else fp_scores).append(top1)

    floor = _percentile(tp_scores, ADMIT_TP_PCTL)

    def admit_rate(scores, thr):
        return sum(1 for s in scores if s >= thr) / len(scores) if scores else 0.0

    # Precision among admitted at the recommended floor.
    adm_tp = sum(1 for s in tp_scores if s >= floor)
    adm_fp = sum(1 for s in fp_scores if s >= floor)
    prec = adm_tp / (adm_tp + adm_fp) if (adm_tp + adm_fp) else 0.0

    curve = []
    for thr in (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70):
        a_tp = sum(1 for s in tp_scores if s >= thr)
        a_fp = sum(1 for s in fp_scores if s >= thr)
        curve.append({
            "threshold": thr,
            "tp_admit_rate": round(admit_rate(tp_scores, thr), 3),
            "fp_admit_rate": round(admit_rate(fp_scores, thr), 3),
            "precision_admitted": round(a_tp / (a_tp + a_fp), 3) if (a_tp + a_fp) else None,
        })

    return {
        "backend": backend,
        "n_rows": len(rows),
        "n_true_pos": len(tp_scores),
        "n_false_pos": len(fp_scores),
        "mean_top1_correct": round(sum(tp_scores) / len(tp_scores), 4) if tp_scores else None,
        "mean_top1_wrong": round(sum(fp_scores) / len(fp_scores), 4) if fp_scores else None,
        "cortex_floor": CORTEX_FLOOR,
        "recommended_floor": round(floor, 4),
        "recommended_floor_basis": f"{ADMIT_TP_PCTL}th pctl of correct top-1 scores",
        "precision_at_recommended_floor": round(prec, 4),
        "tp_admit_at_cortex_floor": round(admit_rate(tp_scores, CORTEX_FLOOR), 3),
        "fp_admit_at_cortex_floor": round(admit_rate(fp_scores, CORTEX_FLOOR), 3),
        "threshold_curve": curve,
    }


if __name__ == "__main__":
    out = {b: analyse(b) for b in ("local-cosine", "local-reranked")}
    print(json.dumps(out, indent=2))
    (HERE / "floor_recalibration_local.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )
