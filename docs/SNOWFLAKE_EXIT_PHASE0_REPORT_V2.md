# Snowflake-Exit Phase-0 Decision Report **v2** — Hybrid (BM25 + arctic-embed) vs Cortex P@1

**Verdict: NO-GO** — the gap to Cortex narrowed materially, but the local stack
still does not reach parity, and the binding constraint (candidate recall on
cryptic exam cross-reference rows) is not yet solved.
**Agent:** AGENT_31 · **Branch:** `snowflake-exit/agent-31` · **Date:** 2026-05-29
**Status:** Phase-0 only — offline, no deploys, exam-week freeze observed.
**Supersedes for the architecture question:** v1 (`SNOWFLAKE_EXIT_PHASE0_REPORT.md`,
AGENT_30). v1's verdict stands; v2 tests a *better* architecture and re-runs the
identical gate.

---

## 1. Headline verdict & rationale

AGENT_30 (v1) NO-GO'd on the weakest possible local stack — vector-only search
with `bge-small` — and diagnosed the bottleneck precisely: **embedding recall**,
not reranking, with the collapse concentrated in cryptic `solution_cross_ref`
rows (recall@20 = 0.752 on a sample) while natural-language phrasings recalled
fine (0.935).

v2 tests the architecture Cortex actually uses — **hybrid lexical + dense
retrieval**, with a stronger, query/document-asymmetric dense model
(`snowflake/snowflake-arctic-embed-m`, 768-dim) fused with BM25 via Reciprocal
Rank Fusion. Run as an **ablation** (each lever measured alone) through AGENT_28's
unchanged parity harness, on the **full 3,430-row golden set**.

The result: **hybrid is the best local configuration by a clear margin
(P@1 = 0.497, recall@20 = 0.872), but it is still far short of the locked Cortex
gate of P@1 ≥ 0.911**, and recall@20 did **not** clear the ~0.92 bar the v1
report set as the precondition for parity. Because the correct tutorial is still
absent from the top-20 pool in ~13% of cases overall (and ~22% of cross-ref
rows), **no reranker layered on this pool can reach the gate** — the same
ceiling argument that bound v1 still binds v2, just less tightly.

Two ablation findings sharpen the diagnosis and redirect the next dispatch:

1. **The lexical lever did *not* fix the cross-ref rows** — the hypothesis this
   dispatch was built to test. BM25 alone recalls *phrasings* almost perfectly
   (recall@20 = 0.991) but is the **worst** backend on `solution_cross_ref`
   (recall@20 = 0.698, below even `bge-small`). Terse exam prompts like
   *"Show that d = 0"* or *"ωⁿ = 1, ω ≠ 1 …"* share too few literal tokens with
   tutorial concept text for lexical matching to help.
2. **The model lever helped, and the way it's wired matters enormously.**
   `arctic-embed-m` lifts cross-ref recall@20 from 0.710 (bge) to 0.775 — but
   **only once the query is given arctic's asymmetric retrieval prefix.** Without
   it (fastembed 0.3.6 does not apply it automatically), arctic *collapsed* to
   P@1 = 0.184 — worse than bge. This is a load-bearing production caveat.

Hybrid wins on **ranking** (P@1 +0.056 over the best single lever) because the
dense and lexical signals agree on true positives and that agreement sharpens
rank-1; it wins only modestly on **recall** (+0.024 over arctic alone), because
the rows both signals miss are the same hard cross-ref rows.

The recommendation stands with v1: **keep `SNOWFLAKE_EXIT_PLAN.md` as a
documented artifact and do not execute the exit.** But v2 changes the strategic
read from "the cheap stack fails by a structural margin" to "**the gap is
closing and the next lever is identifiable**" — see §6. The single most
promising untested lever is **query rewriting on the cross-ref prompts**, which
the *live* system already applies (AGENT_21/24) but this offline gate does not.

---

## 2. The ablation table (offline, via AGENT_28's `eval/parity_harness.py`)

Identical harness, identical scoring rules (`TOP_K = 5`, cross-ref "best rank
over the part's referenced tutorials"), identical golden set. Cortex baseline
reproduced offline from `scoring_rows_20260526_1307.csv` via `cortex-csv-replay`
(**reproduces P@1 = 0.911 exactly** — the harness is unchanged). The v1
`bge-small` baseline was **re-measured in this harness on the full set** and
reproduces v1's documented numbers exactly (P@1 = 0.408; subset P@1 = 0.330;
subset recall@20 = 0.775) — confirming the v1↔v2 comparison is apples-to-apples.

### Full golden set (n = 3,430)

| Backend | P@1 | P@3 | MRR | recall@1 | recall@5 | **recall@20** | phrasings r@20 | cross_ref r@20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **cortex** (baseline) | **0.911** | 0.973 | 0.942 | — | — | — | — | — |
| `bge-small`-cosine (v1 model) | 0.408 | 0.576 | 0.499 | 0.408 | 0.647 | 0.812 | 0.942 | 0.710 |
| `arctic`-cosine (model lever) | 0.441 | 0.633 | 0.541 | 0.441 | 0.699 | 0.848 | 0.942 | 0.775 |
| `bm25` (lexical lever) | 0.437 | 0.628 | 0.534 | 0.437 | 0.681 | 0.827 | **0.991** | 0.698 |
| **`hybrid`** (arctic ⊕ bm25, RRF) | **0.497** | **0.679** | **0.592** | 0.497 | 0.745 | **0.872** | 0.984 | **0.783** |
| `hybrid-reranked` | *not run — see §3* | | | | | | | |

### Golden subset (n = 200, the designed-representative sample)

| Backend | P@1 | P@3 | MRR | recall@1 | recall@5 | recall@20 | phrasings r@20 | cross_ref r@20 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `bge-small`-cosine (v1) | 0.330 | 0.475 | 0.412 | 0.385 | 0.635 | 0.775 | 0.932 | 0.685 |
| `arctic`-cosine | 0.390 | 0.540 | 0.467 | 0.435 | 0.665 | 0.840 | 0.918 | 0.795 |
| `bm25` | 0.370 | 0.555 | 0.462 | 0.410 | 0.655 | 0.790 | 0.986 | 0.677 |
| **`hybrid`** | **0.420** | 0.580 | 0.505 | 0.490 | 0.705 | **0.860** | 0.973 | 0.795 |

Every backend **FAILS** the gate. Hybrid is closest (full-set Δ = −0.414 on P@1).

---

## 3. Did the optional reranker run? No — and why that's the right call

`hybrid-reranked` was **not** scored. The headline question this dispatch posed
is *whether hybrid fixes recall* — and a reranker **cannot** fix recall: it only
reorders the candidate pool it is handed. With hybrid recall@20 = 0.872 (full)
the reranked-P@1 ceiling is **0.872 < 0.911**, so a reranker cannot clear the
gate regardless of quality. v1 already established that a local cross-encoder
*degrades* P@1 at low recall (it slightly hurt the phrasings rows). Layering it
here would consume the offline CPU budget (torch + a cross-encoder pass over
3,430 × 20 pairs) to produce a number that is provably below the gate. It is
deferred to Phase-2, where it matters only **after** the recall pool is parity-
capable, and primarily for **score calibration** (the confidence floor), not
ranking.

---

## 4. Ablation diagnosis — which lever moved what

**Model lever (bge → arctic, vector-only):** recall@20 **+0.036** full
(0.812 → 0.848); the gain is concentrated where v1 said it was needed —
`cross_ref` recall@20 **+0.065** (0.710 → 0.775). P@1 **+0.033** (0.408 → 0.441).
A real but modest lift. **Caveat (load-bearing):** arctic is asymmetric; queries
require the prefix `"Represent this sentence for searching relevant passages: "`.
fastembed 0.3.6 does **not** apply it, and without it arctic scored **P@1 = 0.184
/ recall@20 = 0.640** — *worse than bge*. The +0.26 P@1 swing from a one-line
prefix is a warning that a production embedding integration must get the
query/document asymmetry exactly right.

**Lexical lever (BM25 alone):** recall@20 = 0.827, and on *phrasings* it is the
single best backend (recall@20 = **0.991**) — literal token overlap nails student
paraphrases. **But on `cross_ref` it is the worst (0.698), below bge.** This
**refutes the dispatch's central hypothesis** that lexical retrieval would
recover the cryptic cross-ref rows: those prompts (`"Show that d = 0"`) are too
terse and symbol-heavy to share tokens with prose tutorial bodies.

**Hybrid (arctic ⊕ bm25, RRF k = 60):** recall@20 = **0.872** (best overall), and
P@1 = **0.497** — **+0.056 over the best single lever** (arctic 0.441). Fusion's
value is mostly on **ranking**: when dense and lexical independently surface the
same tutorial, RRF promotes it to rank-1, lifting P@1 more than recall. On the
binding constraint, hybrid cross_ref recall@20 = 0.783 is only **+0.008** over
arctic alone — the rows both signals miss overlap heavily, so fusion cannot
manufacture recall neither retriever has.

**Did hybrid clear recall@20 > ~0.92?** **No.** 0.872 (full) / 0.860 (subset),
short by ~0.05. **Did it push P@1 toward 0.911?** It moved from 0.408 (v1) to
0.497 — **+0.089, +22% relative** — real progress, but less than half-way.

### v1 → v2 recall@20 delta (the headline number)

| Scope | v1 `bge` recall@20 | v2 `hybrid` recall@20 | Δ |
|---|---:|---:|---:|
| full set | 0.812 (re-measured) | **0.872** | **+0.060** |
| golden subset | 0.775 | **0.860** | **+0.085** |
| cross_ref (full) | 0.710 | **0.783** | **+0.073** |

The architecture change recovers 6–8.5 recall points — meaningful, and on the
right rows — but leaves a ~5-point gap to the ~0.92 precondition and a ~22%
cross-ref miss rate that bounds any downstream reranker below the gate.

---

## 5. Recommended `RETRIEVAL_FLOOR` (analysis only — live code unchanged)

> Live code is **unchanged**. `RETRIEVAL_FLOOR = 0.30` and the blended weights in
> `api/orchestrator/retriever.py` are untouched. The hybrid/bm25 `[0,1]` scores
> here are **analysis-only** calibrations (RRF score min-max'd; top hit → 1.0),
> emitted so the harness's floor metric renders — **not** a tuned confidence gate.

The hybrid score is **not usable as a confidence floor**: by construction the top
hit is always 1.0 (mean top-1 = 1.000), so it carries no separation between right
and wrong — the same defect v1 found in raw cosine. A real floor needs a
**calibrated reranker score** (v1 showed the local cross-encoder *does* separate
right from wrong, mean top-1 ≈ 0.62 correct vs 0.25 wrong). **Recommendation:
defer floor recalibration to Phase-2, set it against a reranker score (≈ 0.40 per
v1 §5), and do not gate on the RRF/cosine score.** Gating a P@1-0.50 backend just
converts wrong answers into "I don't know"s.

---

## 6. If still short of parity — the next cheapest lever

The binding constraint is unchanged from v1: **`cross_ref` candidate recall**
(now 0.783 @20). Ranked by expected impact / cost:

1. **Query rewriting on the cross-ref prompts (cheapest, likely highest impact).**
   This gate feeds **raw** exam prompts to retrieval, but the **live** system
   already runs AGENT_21/24 query rewriting *before* retrieval — so this offline
   number *understates* production. Re-run the gate with rewritten cross-ref
   queries (expand `"Show that d = 0"` into a topic-bearing query) before
   touching the model. No new dependency, directly targets the failing rows.
2. **Hosted embeddings A/B (Voyage `voyage-3` / OpenAI `text-embedding-3-large`).**
   The arctic-prefix experiment shows model/wiring choice swings P@1 by 0.26;
   Cortex's managed embeddings are stronger than any local CPU model. This is the
   most promising raw-recall lever and was deliberately kept out of this key-free
   dispatch (it is its own future dispatch).
3. **Chunking redesign (held constant here to isolate model+hybrid).** Cross-ref
   answers may live in tutorial sub-sections that whole-tutorial chunks dilute;
   finer chunks could raise cross_ref recall. Flag as a follow-up lever.

The migration is **not** dead: v2 shows a clear, monotone path
(bge → arctic → hybrid → +query-rewrite/hosted-embeddings) toward the pool the
gate needs.

---

## 7. Honest caveats

- **Golden-only.** No real-traffic shadow has been run; the production query mix
  (and the live query-rewriting layer, see §6.1) is not reflected here, and the
  offline raw-prompt setup is a *lower bound* on the production retrieval the
  cross-ref rows would actually receive.
- **Local CPU spike models.** `arctic-embed-m` (local ONNX) and `bm25s` are spike
  stand-ins; hosted embeddings/rerankers (Cortex's actual quality tier) are a
  separate dispatch and likely stronger.
- **arctic asymmetry wiring** is the single biggest correctness risk uncovered
  (§4); a production port must apply the query prefix.
- **Reranker not layered** (§3) — justified by the recall ceiling, but it means
  no calibrated confidence score was measured for the hybrid pool.
- **Chunking held constant** — flagged as a lever, not exercised.
- **Scope is concept retrieval only** (`TUTOR_SEARCH`). Summaries
  (`SUMMARY_SEARCH`), solutions (`SOLUTIONS_SEARCH`) and Cortex-Analyst are **not**
  covered — each needs its own Phase-2 parity gate.

---

## 8. To proceed to Phase 2, ALL of these must hold

1. **Candidate recall is fixed first** — `recall@5 ≥ ~0.95` and `recall@20 ≥ ~0.97`
   on the full golden set, **especially on `solution_cross_ref`** (today 0.783
   @20). The cheapest route is query-rewrite + hosted-embedding A/B (§6).
2. **The full gate passes** — with that pool, a reranker lifts **overall
   P@1 ≥ 0.911** on the full golden set, with **no strand regressing > 0.05** below
   its Cortex baseline. (Today the strongest local strand, `induction`, is 0.737 —
   still below Cortex's overall; there is no near-parity strand yet.)
3. **Floor recalibrated** to a reranker score (≈ 0.40, per §5) and re-validated.
4. **Real-traffic shadow eval** run alongside the golden gate before any cutover.
5. **The other surfaces** (summaries, solutions, Analyst) each clear their own gate.

Until (1) and (2) hold together, the exit is not safe to execute. v2's
contribution is to show **(1) is now within reach of identifiable, cheap levers**
rather than blocked by a structural ceiling.

---

## 9. Reproduction (all offline, free, branch `snowflake-exit/agent-31`)

```
# Build the two indexes (arctic 768-dim + BM25; bge 384-dim):
python scripts/build_local_index.py --model snowflake/snowflake-arctic-embed-m --with-bm25 --out local_index_arctic
python scripts/build_local_index.py --model BAAI/bge-small-en-v1.5 --out local_index

# Score + recall through AGENT_28's harness (checkpointed, resumable):
export ARCTIC_INDEX_DIR=local_index_arctic BGE_INDEX_DIR=local_index
for b in local-bge-cosine local-arctic-cosine local-bm25 local-hybrid; do
  python eval/run_hybrid_parity.py score  "$b"          # full, resumable
  python eval/run_hybrid_parity.py report "$b"          # parity gate
  python eval/run_hybrid_parity.py recall "$b"          # recall@K ablation
done

# Sanity: the Cortex anchor still reproduces 0.911 (harness unchanged):
python eval/parity_harness.py --backend cortex-csv-replay --rows eval/scoring_rows_20260526_1307.csv
```

Machine-readable metrics for every backend are saved as
`eval/parity_report_local-*.json` and `eval/recall_report_local-*.json`.
