# Snowflake-Exit Phase-0 Decision Report — Local Retriever vs Cortex P@1

**Verdict: NO-GO** (do not execute the Snowflake exit on the current local stack).
**Agent:** AGENT_30 · **Branch:** `snowflake-exit/agent-30` · **Date:** 2026-05-29
**Status:** Phase-0 only — offline, no deploys, exam-week freeze observed.

---

## 1. Headline verdict & rationale

A local, offline, free retrieval stack (AGENT_29's LanceDB + `bge-small-en-v1.5`
embeddings, with an added local cross-encoder reranker) **does not come close to
matching Cortex's locked baseline of P@1 ≥ 0.911**, and — critically — **cannot
be made to** by reranking alone.

On the full golden set the raw cosine stack scores **P@1 = 0.408** and the
reranked stack **P@1 ≈ 0.31–0.36**; both are roughly half the Cortex baseline.
More decisively, the **candidate-recall ceiling** — the fraction of rows where
the correct tutorial appears anywhere in the cosine top-20 pool, which is the
absolute upper bound on what *any* reranker over that pool can achieve — is only
**0.775 on the golden subset and 0.833 on a full-set sample**. Both are below
0.911. So even a *perfect* reranker cannot reach parity: in ~17–22% of cases the
right answer is never retrieved into the pool to be reranked.

The bottleneck is **embedding recall**, not reranking. The local cross-encoder
reranker, far from "recovering parity" as the migration plan hoped, **slightly
degrades P@1** (it helps the cryptic cross-ref rows a little but hurts the
phrasings rows where cosine already nails the title match). The reranker's only
clear win is **score calibration** (its score separates right from wrong far
better than cosine does), which is useful for the confidence floor but does not
move the ranking metric the gate is defined on.

This is the cheap test the plan called for, and it came back negative. The
recommendation is to **keep the exit plan as a documented artifact and not
execute it** until the embedding-recall problem is solved (a Phase-3
embedding-model question), then re-run this exact gate.

---

## 2. The numbers (offline, via AGENT_28's `eval/parity_harness.py`)

All rows scored through the identical harness, identical scoring rules
(`TOP_K=5`, cross-ref "best rank over the part's referenced tutorials"), identical
golden set. Cortex baseline reproduced offline from the saved
`scoring_rows_20260526_1307.csv` (`cortex-csv-replay`) — no Snowflake call.

### Overall

| Backend | Scope | n | P@1 | P@3 | MRR | mean top-1 | % ≥ floor 0.30 |
|---|---|---:|---:|---:|---:|---:|---:|
| **cortex** (baseline) | full | 3193 | **0.911** | 0.973 | 0.942 | 0.950 | 100% |
| local-cosine | subset | 200 | 0.330 | 0.475 | 0.411 | 0.745 | 100% |
| local-cosine | full | 3430 | **0.408** | 0.576 | 0.499 | 0.740 | 100% |
| local-reranked | subset | 200 | 0.305 | 0.470 | 0.397 | 0.351 | 41.5% |
| local-reranked | full *(partial, N=460)* | 460 | 0.363 | 0.550 | 0.463 | 0.389 | 45.4% |

> The full local-reranked pass was scored on a 460-row sample (the complete
> 200-row stratified golden subset plus 260 further rows). A full 3.4k-row
> cross-encoder pass was not completed within the offline CPU spike budget; it is
> not needed for the verdict, which is bounded by the candidate-recall ceiling
> (§4). The subset is the designed-representative sample and is the headline.

### By source (the structural story)

| Source | Cortex | local-cosine (full) | local-reranked (full, partial) |
|---|---:|---:|---:|
| phrasings | 0.822 | 0.587 | 0.534 |
| solution_cross_ref | 0.990 | 0.268 | 0.203 |

Cortex's strength is overwhelmingly on **`solution_cross_ref`** (0.990) — mapping
an exam question to the tutorial(s) it references. That is exactly where the
local stack collapses (0.27 cosine), because `bge-small` struggles to align a
terse exam prompt (e.g. *"Show that `d = 0`"*, *"`ωⁿ = 1`, `ω ≠ 1` …"*) to a
tutorial title/body. Phrasings rows (a student paraphrase → its tutorial) are the
local stack's *relative* strength but still well short (0.59 vs 0.82).

### How much did the reranker buy?

**It cost, it didn't buy.** Reranking moved overall P@1 by **−0.025 on the
subset** (0.330 → 0.305) and **≈ −0.045 on the partial full set** (0.408 → 0.363).
Per source the picture is split: on `solution_cross_ref` the reranker *helped*
modestly (subset 0.157 → 0.213) but on `phrasings` it *hurt* (subset 0.630 →
0.466), and phrasings are the easier, higher-volume win the local stack was
relying on. Even "it didn't help" is the finding the dispatch asked for, and it
is unambiguous: **a local cross-encoder does not recover parity here.**

---

## 3. Build & spike facts

- **Index:** 237 tutorial chunks (corpus walk: 280 files, 237 parsed, 20
  `_SUMMARY` + 2 README + 21 out-of-schema skipped), embedded on both
  `title_plus_phrasings` and `body` with `bge-small-en-v1.5` (384-dim, L2-norm),
  written to a LanceDB table. Index size ≈ 3.4 MB.
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (local, CPU, ~80 MB, no
  API key). Candidate pool = cosine top-20 → rerank → top-5; score = sigmoid of
  the cross-encoder logit, mirroring `retriever._sigmoid_normalize`.
- **Everything offline & free:** no API keys, no Anthropic, no Snowflake. The
  one-time model downloads are the only network use.

---

## 4. The decisive analysis — candidate-recall ceiling

A reranker can only **reorder** the candidate pool it is given; it can never
surface a document the embedding stage failed to retrieve. So the recall of the
correct answer within the cosine **top-20** pool is a hard upper bound on
reranked P@1:

| Scope | recall@1 | recall@5 | **recall@20 (= reranked P@1 ceiling)** |
|---|---:|---:|---:|
| golden subset (N=200, exact) | 0.385 | 0.635 | **0.775** |
| full-set stratified sample (N=245) | 0.437 | 0.673 | **0.833** |

Full-set sample, by source: **phrasings recall@20 = 0.935**, **cross_ref
recall@20 = 0.752**. The cross-ref pool is where parity dies — one in four
correct tutorials never makes the top-20.

**Both ceilings (0.775, 0.833) are below the 0.911 gate.** No amount of reranking
— at any text length, with any local cross-encoder — can clear the gate on this
candidate pool. This is why the verdict is robust and not an artifact of reranker
tuning: the constraint is upstream of the reranker.

---

## 5. Recommended `RETRIEVAL_FLOOR` and blended weights (Phase-2b — recommendations only)

> Live code is **unchanged**. `RETRIEVAL_FLOOR = 0.30` and the blended weights
> (`w_r=0.6, w_c=0.3, w_t=0.1`) in `api/orchestrator/retriever.py` are untouched.
> These are recommendations for *if* Phase 2 ever proceeds.

The Cortex floor (0.30) was tuned to Cortex's reranker score mass (mean top-1
≈ 0.95). The local score distributions are different, so it does not transfer:

| Backend | mean top-1 (correct) | mean top-1 (wrong) | separation? | floor recommendation |
|---|---:|---:|---|---|
| local-cosine | 0.765 | 0.723 | **none** | cosine score is **unusable** as a confidence gate — precision-of-admitted is flat (~0.41) from threshold 0.10 to 0.60. Do **not** gate on cosine. |
| local-reranked | 0.624 | 0.245 | **good** | reranker score is a usable gate; **floor ≈ 0.40** (admits 68% of true positives, rejects 73% of false positives, precision-of-admitted ≈ 0.61). |

So the *only* recalibration that makes sense is to keep the reranker (for its
**confidence** value) and set `RETRIEVAL_FLOOR ≈ 0.40` against the reranked score
— but this matters only *after* the ranking problem is solved, since gating a
backend that ranks at P@1 0.36 just turns wrong answers into "I don't know"s.

**Blended weights:** the live emphasis (`w_r=0.6` reranker-dominant) does **not**
transfer. On this corpus the local cross-encoder is a *weaker ranking signal*
than the bge cosine, so a local blend would need to invert the emphasis toward
cosine — a weight sweep on a (phrasings-heavy) sample ranked **cosine-dominant**
best and **reranker-only** worst. But since cosine-only is still 0.408, no blend
of these two signals reaches parity. **Recommendation: do not port the
Cortex-tuned blend weights; and do not treat blending as a path to parity.**

---

## 6. Weakest strands & regressions

Against the Cortex per-strand baseline, **every strand regresses far beyond the
0.05 margin** — this is a uniform, structural shortfall, not a few bad strands.
The weakest local strands (reranked, partial-full) include complex-numbers
(0.125), differentiation (0.152), trigonometry (0.174), indices-logs and
sequences-series (0.200). The least-bad are financial-maths (0.77) and the-circle
(0.41). Even the strongest local strand sits below Cortex's *weakest*. There is
no strand at or near parity.

---

## 7. Honest caveats

- **Eval set is golden-only.** No real-traffic shadow has been run; production
  query mix may differ from the golden distribution.
- **Reranker is a local-model spike.** `ms-marco-MiniLM-L-6-v2` is a small,
  general MS-MARCO cross-encoder, not domain-tuned for LCHL maths; a stronger or
  hosted reranker could rank the pool better — but cannot beat the recall ceiling
  (§4), which is the binding constraint.
- **Rerank text was capped** (~256 chars, title-led) to keep the CPU pass
  tractable. This was validated as *not* the cause of the shortfall: the ceiling
  analysis bounds the reranker independently of its text window.
- **Full reranked pass is a 460-row sample**, not all 3.4k rows (offline CPU
  budget). The subset is stratified-representative and the ceiling is computed on
  a full-set sample; the verdict does not depend on the missing rows.
- **Scope is concept retrieval only** (`TUTOR_SEARCH`). Summaries
  (`SUMMARY_SEARCH`), solutions (`SOLUTIONS_SEARCH`), and Cortex-Analyst paths are
  **not** covered here — they are Phase-2 follow-ups and would each need their own
  parity gate.
- **Embedding model is the spike model** (`bge-small`). The production embedding
  choice is a separate Phase-3 decision and is the most promising lever (§8).

---

## 8. To proceed to Phase 2, ALL of these must hold

1. **Candidate recall is fixed first.** A stronger embedding model (or hybrid
   lexical+dense retrieval) must lift cosine **recall@5 ≥ ~0.95 and recall@20
   ≥ ~0.97** on the full golden set, *especially on `solution_cross_ref`* (today
   0.752 @20). Without this, no reranker can reach the gate.
2. **The full gate passes.** With that pool, a reranker (local or hosted) must
   lift **overall P@1 ≥ 0.911 on the full golden set**, with **no strand
   regressing more than 0.05** below its Cortex baseline.
3. **Floor recalibrated** to the new score distribution (≈ 0.40 against a
   reranker score, per §5) and re-validated.
4. **Real-traffic shadow eval** run alongside the golden gate before any cutover.
5. **The other surfaces** (summaries, solutions, Analyst) each clear their own
   parity gate.

Until (1) and (2) hold together, the exit is not safe to execute.

---

## 9. Strategic read for the operator

The data supports **not executing the Snowflake exit now**, and keeping
`SNOWFLAKE_EXIT_PLAN.md` as a documented, ready-to-revisit artifact rather than a
plan to action after 9 June.

The reasoning the plan itself set out: Cortex is the scarcest, hardest-to-rebuild
CV signal, so it should only be retired if the cheap offline test proves the
replacement holds. **The cheap test was run, and it did not hold** — by a wide,
structural margin (P@1 0.41 vs 0.91), with a hard ceiling (≤ 0.83) that reranking
cannot break. Executing now would trade a 0.91-P@1 system for a ~0.4-P@1 one.

The single most valuable next experiment is **not** more reranker work — it is an
**embedding-model recall** spike (Phase-3): re-run *this same harness and ceiling
analysis* with a stronger/hosted embedding model and see whether recall@20 on
`solution_cross_ref` clears ~0.95. **A hosted reranker is worth A/B-ing later**,
but only after the candidate pool is parity-capable; reranking a weak pool, as
this spike shows, is wasted motion. If a future embedding spike lifts the ceiling
above 0.911, re-open this gate; until then, Cortex stays.
