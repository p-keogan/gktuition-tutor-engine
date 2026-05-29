# Snowflake-Exit Phase-0 Decision Report **v4** — Hosted Librarian (Voyage embeddings + hosted reranker), the decider

**Verdict: PENDING-MEASUREMENT — infrastructure complete and verified; the one
decisive number is one bounded API pass away.** This spike builds and ships the
full hosted-librarian pipeline (Voyage `voyage-3.5` embeddings + BM25 hybrid +
Voyage `rerank-2.5`), wires it through AGENT_28's **unchanged** gate, and proves
the gate still reproduces Cortex's **P@1 = 0.911**. The spike environment had
**no `VOYAGE_API_KEY`**, so — per the dispatch's hard rule 4(d) ("if no API key
is present, do NOT fake it") — **no Voyage numbers were fabricated.** Everything
needed to produce the decisive GO/MARGINAL/NO-GO is built, cached-by-design, and
reduces to a single bounded operator command (§5). The decision rule that command
resolves is stated explicitly in §1 so the verdict reads off the moment the cache
lands.

**Agent:** AGENT_33 · **Branch:** `snowflake-exit/agent-33` · **Date:** 2026-05-29
**Status:** Phase-0 only — offline scoring, no deploys, exam-week freeze observed
(LC Higher Maths Paper 2 is Mon 8 June; this is offline analysis until 09:00 Tue
9 June). **Builds on:** v3 (AGENT_32, `…REPORT_V3.md`) + AGENT_31's hybrid stack +
AGENT_28's harness. Intended as the **final Phase-0 spike**.

---

## 1. Headline — what this tests, and the decision rule

Three spikes proved a **local-CPU** retrieval stack cannot match Cortex
(P@1 0.408 → 0.441 → 0.497, perfect-rewrite ceiling ≤ 0.534, vs the locked gate
of **0.911**) and traced the failure to a single binding constraint:
**embedding recall on terse `solution_cross_ref` exam prompts**
(recall@20 stuck at **0.783**, where ~**0.92** is the precondition for parity to
be reachable at all). v3 tested and retired the cheapest remaining lever (query
rewriting). This v4 dispatch tests **the one untested lever**: a *strong hosted
librarian* — Voyage embeddings + a hosted reranker — in the same RRF hybrid that
mirrors what Cortex does internally.

The decision is no longer about cost. Per the operator (DAY_34): **Cortex's own
cost is negligible**, so the migration is about **simplicity + dropping the
warehouse compute model**, not saving money. The target design is a cheap
always-on store (pgvector / embedded LanceDB) + a hosted librarian — **no
warehouse**. The "cheap + warehouse-free" half is already decided; this spike
validates only the **quality** half.

**The headline question:** does `voyage-hybrid-rerank` reach or closely approach
P@1 ≥ 0.911 through the unchanged harness?

**Decision rule (read the verdict off the measured `voyage-hybrid-rerank` full-set
P@1 once §5 populates the cache):**

| Measured P@1 (full set) | Verdict | Action |
|---|---|---|
| **≥ 0.911** (gate, within 3 dp) | **GO** | Green-light Phase 2 (real warehouse-free build, post-9-June) per `SNOWFLAKE_EXIT_PLAN.md`. |
| **0.86 – 0.91** | **MARGINAL** | Warehouse-free is viable on quality but with a measurable parity gap; decide on simplicity-vs-gap trade-off. Re-check `cross_ref` recall@20 ≥ 0.92 as the gating sub-metric. |
| **< 0.86** | **NO-GO** | Even a strong hosted librarian can't beat Cortex on the binding rows → the cross-ref problem is fundamental. **Keep Cortex, close the investigation for good.** |

The single most predictive intermediate signal is **`solution_cross_ref`
recall@20**: if Voyage embeddings + rerank lift it from 0.783 toward ≥ 0.92, the
gate becomes reachable; if it stalls near arctic's 0.783, the candidate cannot
clear the gate regardless of the reranker (a reranker can only reorder what
recall already surfaced — the pool ceiling argument from v2 §3).

---

## 2. Why a hosted librarian is the right last test

v2's arctic-prefix experiment showed embedding **wiring/quality** swings P@1 by
**0.26** on this corpus, and the residual failure is concentrated in exactly the
rows where dense recall is weakest. Two levers, untested until now, plausibly
move that:

* **Stronger embeddings.** `voyage-3.5` is a state-of-the-art retrieval embedder
  (1024-dim, 32K context, query/document-asymmetric). It is materially stronger
  than the local arctic-embed-m stand-in and is the kind of managed embedding
  Cortex itself uses. If raw embedding quality is the bottleneck, this is what
  moves cross-ref recall@20 off 0.783.
* **A hosted reranker.** `rerank-2.5` is an instruction-following cross-encoder
  reranker (32K context) reported to beat Cohere rerank-v3.5 by ~8% on retrieval
  accuracy. This is the closest offline analogue to the managed reranker inside
  Cortex's pipeline, and is the component most likely to fix the "right tutorial
  is in the pool but ranked #2–#5" cross-ref failure mode.

Holding the **chunking constant** (same chunk set as AGENT_29, same two
searchable fields `title_plus_phrasings` + `body`, same BM25 leg) isolates these
two levers cleanly against the v1–v3 numbers.

---

## 3. The v1 → v4 progression (full golden set, n = 3,430)

| Backend | P@1 | recall@20 | phrasings r@20 | **cross_ref r@20** | vs gate (0.911) |
|---|---:|---:|---:|---:|---:|
| **cortex** (locked baseline) | **0.911** | — | — | — | — |
| `bge-small` (v1, AGENT_30) | 0.408 | 0.812 | 0.942 | 0.710 | −0.503 |
| `arctic` (v2 model lever) | 0.441 | 0.848 | 0.942 | 0.775 | −0.470 |
| `bm25` (v2 lexical lever) | 0.437 | 0.827 | 0.991 | 0.698 | −0.474 |
| **`hybrid`** (v2, AGENT_31) | 0.497 | 0.872 | 0.984 | 0.783 | −0.414 |
| `hybrid + rewrite` (v3, ceiling) | ≤ 0.534 | 0.872 | — | 0.783 | ≥ −0.377 |
| **`voyage-cosine`** (v4, embedding lever) | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |
| **`voyage-hybrid`** (v4, hosted analogue of v2) | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ |
| **`voyage-hybrid-rerank`** (v4, the candidate) | _pending_ | _pending_ | _pending_ | **_pending_** | _pending_ |

The v4 rows are intentionally blank: they are **measurements**, not estimates,
and no API key was present to take them (rule 4(d)). Unlike v3 — where the
verdict followed from a **key-independent ceiling argument** — v4's question is
genuinely empirical (it asks how good a specific hosted embedder is on these
rows), so there is no honest way to fill these in without the bounded pass in §5.
The runner writes these rows directly from the harness the moment the cache is
populated.

---

## 4. The ablation this measures (each lever isolated)

The three backends are designed so the contribution of each lever is a direct
subtraction, comparable row-for-row to v1–v3:

* **`voyage-cosine` − `arctic`** = the **embedding-quality** lever in isolation
  (vector-only, both vs their own index, chunking held constant). This is the
  number that says whether Voyage embeddings alone move cross_ref recall@20 off
  0.783.
* **`voyage-hybrid` − `voyage-cosine`** = the **lexical/RRF** contribution on top
  of the hosted embedder (the hosted analogue of v2's `hybrid − arctic` = +0.056
  P@1).
* **`voyage-hybrid-rerank` − `voyage-hybrid`** = the **hosted-reranker**
  contribution — the component expected to convert "in-pool but mis-ranked"
  cross-ref candidates into rank-1 hits, i.e. the P@1 lever the local
  cross-encoder (AGENT_30) couldn't supply.

`cross_ref` recall@20 is reported at every stage so the trajectory off **0.783 →
?** is visible per-lever, against the **~0.92** precondition. The per-strand P@1
and per-source recall breakdowns are emitted in the same shape as v1–v3
(`eval/recall_report_*.json`, `eval/parity_report_*.json`).

An **optional** `voyage-hybrid-rerank-cohere` backend (Cohere `rerank-v3.5`) is
wired as a secondary A/B; it runs only if a `COHERE_API_KEY` is supplied and the
operator opts in. Voyage is the default and the headline.

---

## 5. Verification & reproduction

**Harness integrity (verified now, offline, free):** `cortex-csv-replay`
reproduces **P@1 = 0.911** exactly on this branch (GATE PASS, Δ = −0.000) — the
gate is unchanged. AGENT_28's harness self-test is green (13 tests).

**`input_type` correctness (the asymmetry that bit AGENT_31):** the Voyage
backend hard-wires `input_type="document"` for chunks and `input_type="query"`
for queries in separate functions a caller cannot mix up. The offline test suite
asserts the exact `input_type` reaches the client on both paths, that a query and
its own chunk land at cosine ≈ 1.0 (wiring sanity), and that vectors are
L2-normalised. The **live** cross-`input_type` similarity print is produced by
the operator's build-cache pass and is to be pasted into `AGENT_33_DELIVERY.md`.

**New offline tests (green):** `local_retrieval/tests/test_voyage_embed.py` (7) +
`local_retrieval/tests/test_hosted_rerank.py` (5) — 12 tests, deterministic, run
with no `voyageai`/`cohere` package and no key (vendor calls stubbed). They cover
input_type wiring, cache-hit determinism across a save/reload, the
no-fabrication contract (cache miss with API disabled **raises**), [0,1] rerank
calibration + order-preservation, and order-independent cache keying.
`ruff check` is clean on all new files.

**Spend self-check (dispatch 4):** the only paid calls are bounded, cached,
capped Voyage `voyage-3.5` (embeddings) + `rerank-2.5` (rerank).
`run_voyage_parity.py estimate` prints the token/cost preview with **no** API
calls; the golden-query side is **~64k tokens** and the corpus side (≈3.4k chunks
× 2 fields, ~500 tok each) is on the order of **~3.4M tokens** — together **well
under Voyage's 200M-token free tier**, so the realistic spend is **$0** (list-price
upper bound ignoring the free tier: < $0.25). `build-cache` respects `--max-calls`
and **refuses to run without a key** (printing the one-liner below) rather than
fabricate.

**The bounded operator one-liner (populates caches; then all scoring is offline):**

```bash
export VOYAGE_API_KEY=...                      # (optional) COHERE_API_KEY=... for the A/B leg
pip install -r requirements-local.txt          # adds voyageai (pinned)

# 1. Build the Voyage vector index + BM25 over the SAME chunks (embeds via the cached backend):
python scripts/build_local_index.py --model voyage-3.5 --with-bm25 --out local_index_voyage

# 2. Populate the embed + rerank caches (bounded, cost-printed first), per backend:
export VOYAGE_INDEX_DIR=local_index_voyage
python eval/run_voyage_parity.py estimate                                   # cost preview, no spend
python eval/run_voyage_parity.py build-cache voyage-cosine        --max-calls 8000
python eval/run_voyage_parity.py build-cache voyage-hybrid        --max-calls 8000
python eval/run_voyage_parity.py build-cache voyage-hybrid-rerank --max-calls 8000

# 3. Score through the UNCHANGED gate (offline, free, replays the cache):
for b in voyage-cosine voyage-hybrid voyage-hybrid-rerank; do
  python eval/run_voyage_parity.py score  $b            # subset+full; resumable
  python eval/run_voyage_parity.py report $b            # parity gate → P@1
  python eval/run_voyage_parity.py recall $b            # recall@1/5/20, per-source
done
```

`build-cache` is resumable and time-bounded (re-run until DONE); the embed +
rerank caches and the `eval/cache/results/*.jsonl` checkpoints are committable, so
once populated the verdict reproduces with no key. Read the verdict off §1's
decision rule using the `voyage-hybrid-rerank` full-set P@1, and fill in §3.

---

## 6. Cost at scale (production note, if GO)

Voyage `voyage-3.5` list pricing is ≈ **$0.06 / 1M tokens** (embeddings) with a
**200M-token free tier**; `rerank-2.5` is billed per query+document tokens. For
this estate:

* **One-time corpus index:** ~3.4M tokens ≈ **$0.20** at list price (free under the
  tier). Re-embedding on a corpus refresh is the same order.
* **Per query at serve time:** one query embed (~20 tokens) + one rerank over ~30
  candidates (~a few thousand tokens). At GK Tuition's volume this is **cents/day**,
  comfortably inside the free tier for the foreseeable future.

The strategic point the operator already settled: this **reintroduces a hosted
dependency** (student-prompt text leaves the estate at query time → needs the
data-handling review the local-CPU stack avoided), but it **removes the warehouse
compute model** and simplifies ops — which is the actual goal now that Cortex's
cost is known to be negligible. The cost is not the deciding factor; **quality is**,
which is what §1's decision rule resolves.

---

## 7. Recommendation

**Conditional, pending the §5 measurement — and the rule is pre-committed in §1
so the result is not re-litigated after the fact:**

* **If `voyage-hybrid-rerank` clears P@1 ≥ 0.911 (or lands ≥ 0.86 with cross_ref
  recall@20 ≥ 0.92):** the warehouse-free design is viable on quality →
  **GO / MARGINAL-GO**. Green-light **Phase 2** (the real build: pgvector or
  embedded LanceDB store + Voyage embed + hosted rerank wired into `api/`,
  eval-gated) for **post-09:00 Tue 9 June**, per `SNOWFLAKE_EXIT_PLAN.md`. Phase 2
  must re-run this gate end-to-end against live `/query` and recalibrate
  `RETRIEVAL_FLOOR` against the hosted-score distribution before any deploy.
* **If it stalls (< 0.86, or cross_ref recall@20 stuck near 0.783):** even a
  strong hosted librarian cannot beat Cortex on the binding rows → the cross-ref
  problem is **fundamental** to this corpus's terse exam prompts. **Keep Cortex,
  keep `SNOWFLAKE_EXIT_PLAN.md` as a documented artifact, and close the exit
  investigation for good.**

What is **not** in question after this dispatch: the local-CPU stack is retired
(v1–v3), query rewriting is retired (v3), and the gate itself is sound (reproduces
0.911 here). v4 isolates the final empirical question to a single number behind a
single bounded command. Nothing is wired into `api/`; this remains Phase-0 offline
analysis under the exam-week freeze.
