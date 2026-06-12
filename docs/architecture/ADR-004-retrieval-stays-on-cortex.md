# ADR-004 — Retrieval stays on Snowflake Cortex; the exit investigation is closed

**Status:** Accepted · 2026-06-12
**Decision owner:** Paul Keogan (operator) · measured verdict per the pre-committed rule in `docs/SNOWFLAKE_EXIT_PHASE0_REPORT_V4.md` §1.

## Context

The DAY_34 cost incident (~€18/day idle warehouse) prompted a deliberate,
eval-gated investigation into removing Snowflake entirely
(`docs/SNOWFLAKE_EXIT_PLAN.md`). The governing rule: no traffic moves off
Cortex unless a replacement matches the locked golden-set baseline
**P@1 = 0.911** — measured, never assumed. Four Phase-0 spikes ran offline
through one unchanged parity harness (AGENT_28), each isolating one lever:

| Spike | Backend | Full-set P@1 | Verdict |
|---|---|---:|---|
| v1 (AGENT_30) | bge-small local cosine (+ local cross-encoder) | 0.408 | NO-GO |
| v2 (AGENT_31) | BM25 + arctic-embed hybrid | 0.497 | NO-GO |
| v3 (AGENT_32) | hybrid + query-rewrite (perfect-rewrite ceiling) | ≤ 0.534 | NO-GO (key-independent) |
| v4 (AGENT_33) | Voyage 3.5 + BM25 hybrid + Voyage rerank-2.5 | **0.645** | **NO-GO** (measured 2026-06-12) |

## Decision

Retrieval remains on **Snowflake Cortex Search** (3 services) with **Cortex
Analyst** for the analytical leg. The Snowflake-exit plan is **closed** and
retained as a methodology artifact. No further exit spikes without new
evidence (e.g. a corpus restructuring that removes the cross-ref constraint,
or a step-change in embedding models).

## Why

1. **The gap is large and structural, not incremental.** The best hosted
   stack — Voyage embeddings + the strongest reranker lever found in the whole
   investigation (+0.130 P@1) — still lands 0.266 below gate. Monotonic
   improvement across four spikes (0.408 → 0.645) never came close.
2. **The binding constraint is `solution_cross_ref`** (r@1 0.452 / r@20 0.834
   at best vs ~0.92 precondition): terse exam-style prompts that Cortex's
   query understanding resolves and generic embedders do not. This is a
   property of the corpus and its students' phrasing, not of any one vendor.
3. **The original motive evaporated.** The €18/day was idle warehouse cost,
   fixed by auto-suspend + the dev-mode cutback; serve-time Cortex cost is
   negligible. Simplification alone does not justify a measured quality
   regression of this size on a revenue product.

## Consequences

- ADR-001 (vector store: Cortex) is reaffirmed.
- The parity harness, local/hosted retrieval packages, and Voyage caches stay
  in-repo: they are the reusable gate for any future retrieval change, and the
  caches make the v4 verdict reproducible offline with no API key.
- Phase 2/3 work proceeds on Cortex unchanged: warm-worker re-enable,
  widget embed on gktuition.ie (~July), public demo.
- Re-opening this question requires beating the same gate, same golden set,
  same pre-committed rule — written down *before* the numbers are taken.
