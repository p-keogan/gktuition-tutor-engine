# Snowflake-Exit Phase-0 Decision Report **v3** — Hybrid + Query-Rewrite (the production-representative gate)

**Verdict: NO-GO — and now decisively so.** Adding the live query-rewrite layer
in front of AGENT_31's hybrid retriever **cannot** close the gap to Cortex. The
rewrite fires on only **8.4% of the golden set** and, by an exact ceiling
argument, lifts overall P@1 from 0.497 to **at most 0.534** (full set) — still
**0.377 below** the locked Cortex gate of P@1 ≥ 0.911. This is the spike that was
meant to test the cheapest remaining lever; it closes the investigation.

**Agent:** AGENT_32 · **Branch:** `snowflake-exit/agent-32` · **Date:** 2026-05-29
**Status:** Phase-0 only — offline scoring, no deploys, exam-week freeze observed.
**Supersedes for the architecture question:** v2
(`SNOWFLAKE_EXIT_PHASE0_REPORT_V2.md`, AGENT_31). v2's NO-GO stands; v3 adds the
one lever v2 flagged as untested and the *production-representative* number.

---

## 1. Headline verdict & rationale

v2 (AGENT_31) NO-GO'd the hybrid stack at **P@1 = 0.497** and named query
rewriting as "the cheapest untested lever … the *live* system already applies it
(AGENT_21/24) but this offline gate does not," warning that the offline number
therefore *understates* production. This dispatch is that test: run the **same
query-rewrite layer production uses** (`api/orchestrator/query_rewrite.py`,
imported read-only) in front of the hybrid retriever, scored through AGENT_28's
**unchanged** gate.

The production-representative result is unambiguous and, importantly,
**independent of the LLM rewrite quality**:

* Replicating production's two firing mechanisms exactly, the rewrite fires on
  **287 of 3,430 rows (8.4%)** — 104 via AGENT_21's pre-retrieval conceptual
  path (`iter-1`) and 183 via AGENT_24's sub-floor fallback.
* Of those 287, only **126 are currently scored wrong** (the rest are already
  rank-1). So even if **every** fired-and-wrong row were rewritten into a perfect
  rank-1 hit, overall P@1 could reach **0.534** (full) / **0.500** (subset) — a
  hard ceiling.
* **0.534 < 0.911.** The gate fails by **0.377**. No achievable rewrite changes
  this, so the verdict does not depend on spending a single Anthropic call.

The reason rewriting can't help is structural and was hiding in plain sight in
the rewrite gate itself: **the binding-constraint rows exclude themselves from
rewriting.** The cryptic `solution_cross_ref` exam prompts — the rows v1 and v2
both identified as the failure locus — carry domain-language glyphs (`=`, `²`,
`³`, `√`) and operators (`prove`, `derive`), which the production pre-check
treats as "already in domain language" and **skips**. Only **46 of 1,920**
cross-ref rows fire any rewrite at all, and only **42** of those are currently
wrong. The lever and the failing rows barely intersect.

The recommendation from v1 and v2 therefore holds, now on a much firmer basis:
**keep `SNOWFLAKE_EXIT_PLAN.md` as a documented artifact and do not execute the
exit on a local-CPU stack.** v2 framed the gap as "closing and the next lever is
identifiable." v3's contribution is to **test that lever and retire it**: query
rewriting is not the bridge to parity. The only remaining raw-recall lever is
**hosted embeddings** (§6), which is a different cost/vendor decision entirely.

---

## 2. What "production-representative" means here, and how it was measured

The live `/query` path runs two rewrite mechanisms, both reused verbatim:

* **iter-1 — `maybe_rewrite`** (AGENT_21): fires *before* retrieval when the
  query is a short conceptual framing — `query_class == CONCEPT`, a conceptual
  prefix (`explain`, `what is`, `how does`, …), ≤ 4 content tokens, and **no**
  domain-language signal.
* **fallback — `maybe_rewrite_fallback`** (AGENT_24): fires *after* a first
  retrieve comes back **sub-floor** (top score < `RETRIEVAL_FLOOR = 0.30`), with
  a looser pre-check (no prefix gate; ≤ 6 content tokens; same domain-signal
  exclusion).

Two fidelity decisions, both documented so the number is honest:

1. **Sub-floor signal.** The hybrid RRF score is normalised so its top hit is
   always 1.0 (v2 §5) and is therefore useless as a floor. We measure sub-floor
   on the **dense (arctic) top-1 cosine** — a genuine [0, 1] confidence directly
   comparable to `RETRIEVAL_FLOOR`, and the offline analogue of production's
   reranker/cosine floor. 452 rows are sub-floor on this signal; 183 of them also
   pass the looser fallback pre-check.
2. **Query class.** The golden set carries no `query_class`, and the production
   classifier isn't importable offline (Snowflake deps). We treat **every row as
   `CONCEPT`** — the *maximally generous* assumption. In real production the
   cryptic cross-ref exam prompts classify as `solution_lookup` (routed to
   SOLUTIONS_SEARCH, which never touches the CONCEPT-gated rewriter), so
   production fires on a **strict subset** of the 287 counted here. **0.534 is an
   upper bound on an upper bound.**

The `local-hybrid-rewrite` backend (`local_retrieval/rewrite_backend.py`) wraps
AGENT_31's `retrieve_hybrid`: `iter-1` rows retrieve with the rewritten query;
`fallback` rows re-retrieve only when genuinely sub-floor and keep the
better-scoring result; cache misses and un-rewritten rows pass straight through
to hybrid. Scored through AGENT_28's harness, registered as a first-class
backend; the gate math is unchanged.

---

## 3. The v1 → v2 → v3 progression (full golden set, n = 3,430)

| Backend | P@1 | recall@20 | phrasings r@20 | **cross_ref r@20** | vs gate (0.911) |
|---|---:|---:|---:|---:|---:|
| **cortex** (locked baseline) | **0.911** | — | — | — | — |
| `bge-small` (v1, AGENT_30) | 0.408 | 0.812 | 0.942 | 0.710 | −0.503 |
| `arctic` (model lever) | 0.441 | 0.848 | 0.942 | 0.775 | −0.470 |
| `bm25` (lexical lever) | 0.437 | 0.827 | 0.991 | 0.698 | −0.474 |
| **`hybrid`** (v2, AGENT_31) | 0.497 | 0.872 | 0.984 | 0.783 | −0.414 |
| **`hybrid + rewrite`** (v3, measured) | 0.497 | 0.872 | 0.984 | 0.783 | −0.414 |
| **`hybrid + rewrite`** (v3, *perfect-rewrite ceiling*) | **≤ 0.534** | 0.872† | — | — | **≥ −0.377** |

† Rewriting changes *which query* is embedded for ≤ 287 rows; it cannot raise the
recall@20 of the rows it doesn't fire on (94% of cross-ref). The pool ceiling that
bounds any reranker (v2 §3) is unmoved on the binding constraint.

**Golden subset (n = 200):** hybrid P@1 = 0.420 (measured, reproduces v2);
perfect-rewrite ceiling = **0.500**; gate failed by ≥ 0.411. Only **9** subset
rows fire (2 currently wrong).

The measured `hybrid + rewrite` row equals `hybrid` exactly because this
environment has no Anthropic key, so the rewrite cache holds firing *decisions*
but no rewrite *text* — and a cache miss is a no-op (verified: P@1 0.497, MRR
0.592, recall@20 0.872, all identical to v2). The decision-relevant number is the
**ceiling**, which is key-independent.

---

## 4. Quantifying the lever — fire-rate and on-fired lift

**Fire-rate (the deterministic, free part):**

| Mechanism | phrasings | solution_cross_ref | total |
|---|---:|---:|---:|
| iter-1 (pre-retrieval) | 103 | 1 | 104 |
| fallback (sub-floor) | 137 | 46 | 183 |
| **total fired** | **240** | **47** | **287** (8.4%) |

**On-fired-rows lift (the headline honesty check):** of the 287 fired rows, 161
are already rank-1; **126 are currently wrong** and could in principle be fixed.
The maximum achievable overall P@1 is therefore
`(1704 + 126) / 3430 = 0.534`. Per source, only **42** of the fixable rows are
`solution_cross_ref` — so even a perfect rewriter moves the binding-constraint
strand by at most 42/1920 ≈ **2 points** of cross-ref P@1.

**Did cross_ref recall@20 move toward the ~0.92 precondition?** No. Rewriting
fires on 47/1920 cross-ref rows; the other 1,873 are retrieved identically to v2,
so cross-ref recall@20 stays at **0.783**, ~14 points short of the ~0.92 bar v1
set as the parity precondition. The recall ceiling that bounds any downstream
reranker below the gate (v2 §3) is untouched.

**Why so little fires on the rows that matter:** the rewrite pre-check excludes
any query carrying a domain-language signal — the glyphs `= ² ³ √`, LaTeX `$…$`,
or operators like `prove` / `derive`. The cryptic exam prompts that sink the gate
(`"Show that d = 0"`, `"ωⁿ = 1, ω ≠ 1"`, `"prove that …"`) are *built* from
exactly those signals, so they are deliberately skipped — the rewriter was
designed to translate *conceptual* student framings ("explain pensions"), not to
de-crypt terse symbolic exam prompts. This is a correct design for its purpose
and a dead end for ours.

---

## 5. Verification & reproduction

* **Harness integrity:** `cortex-csv-replay` reproduces **P@1 = 0.911** exactly
  (GATE PASS, Δ = −0.000) on this branch — the gate is unchanged.
* **Cache determinism:** `eval/build_rewrite_cache.py` is idempotent; re-runs
  skip cached rows. Firing decisions are a pure function of the query text + the
  arctic checkpoint, so the 287-row fire set is reproducible offline.
* **Backend correctness:** `eval/tests/test_rewrite_backend.py` (8 tests, green)
  asserts iter-1 substitutes pre-retrieval; fallback substitutes only when
  sub-floor; above-floor and cache-miss are no-ops; a worse rewrite never
  degrades a row. `ruff check` clean on all new files.
* **Freeze posture:** `git diff api/` empty; `grep -rn "local_retrieval|parity|
  rewrite_cache" api/` prints CLEAN. New files only under `local_retrieval/`,
  `eval/`, `docs/`. `query_rewrite.py` imported read-only, never modified.

```
# Harness anchor (offline, free):
python eval/parity_harness.py --backend cortex-csv-replay \
    --rows eval/scoring_rows_20260526_1307.csv            # → P@1 = 0.911

# Firing analysis + perfect-rewrite ceiling (offline, free, key-independent):
python eval/build_rewrite_cache.py --dry-run              # 287 fired; est ~$0.12
python eval/run_rewrite_parity.py bound  local-hybrid-rewrite          # ≤ 0.534
python eval/run_rewrite_parity.py report local-hybrid-rewrite          # gate
python eval/run_rewrite_parity.py recall local-hybrid-rewrite          # recall@K

# To populate the exact LLM rewrites (operator, with key — bounded + cost-printed):
ANTHROPIC_API_KEY=sk-... python eval/build_rewrite_cache.py --max-rewrites 1500
python eval/run_rewrite_parity.py score  local-hybrid-rewrite   # re-retrieve fired rows
python eval/run_rewrite_parity.py report local-hybrid-rewrite   # final number ∈ [0.497, 0.534]
```

The committed `eval/rewrite_cache.csv` holds the 287 firing decisions; the
`rewritten_query` column is empty pending the operator's bounded LLM pass. The
verdict is final **without** that pass because the ceiling is key-independent;
running it only locates the production number within the proven `[0.497, 0.534]`
band, which is below the gate at both ends.

---

## 6. The one remaining lever — hosted embeddings (cost/vendor trade-off)

With query rewriting now tested and retired, exactly one untested raw-recall
lever remains: **hosted embeddings** (Voyage `voyage-3`, OpenAI
`text-embedding-3-large`, or Cortex's own managed tier). v2's arctic-prefix
experiment showed model/wiring choice swings P@1 by **0.26**, so a materially
stronger embedder is the only thing that could plausibly lift cross-ref
recall@20 from 0.783 toward the ~0.92 precondition. The trade-offs:

* **Cost:** a per-call/per-token vendor bill and an embedding-refresh pipeline —
  this *reintroduces* the recurring external dependency the Snowflake exit was
  meant to remove, just pointed at a different vendor.
* **Vendor lock / egress:** student-prompt text leaves the estate at query time;
  needs a data-handling review the local-CPU stack avoided entirely.
* **Uncertain ceiling:** even a perfect embedder must clear recall@20 ≥ ~0.97 on
  cross-ref *and* survive the reranker/floor recalibration (v2 §8) — unproven.

This is a distinct dispatch with its own GO/NO-GO, not a continuation of the
local-CPU spike. It should be opened **only if** the business case for leaving
Cortex is strong enough to justify swapping one managed dependency for another.

---

## 7. Final recommendation

**Do not execute the Snowflake exit.** Across three spikes the local stack has
moved 0.408 → 0.441 → 0.497 on P@1, and this dispatch proves the
production-representative number is capped at **0.534** against a **0.911** gate.
The cheap lever (query rewriting) is now tested and does not bridge the gap; the
only remaining lever (hosted embeddings) trades the Snowflake dependency for
another vendor and is unproven. **Keep `SNOWFLAKE_EXIT_PLAN.md` as a documented
artifact, stay on Cortex, and close the local-CPU exit investigation.** Re-open
only as a deliberate hosted-embeddings A/B if the commercial case warrants it.

This concludes Phase 0. No code is wired into `api/`; production already runs the
rewrite layer live — this dispatch only measured it offline and bounded it.
