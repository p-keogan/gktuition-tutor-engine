# Snowflake Exit Plan — migrating gktuition retrieval off Snowflake

**Status:** CLOSED — NO-GO, 2026-06-12. Retained as a methodology artifact; see SNOWFLAKE_EXIT_PHASE0_REPORT_V4.md §8 and ADR-004. Not for execution.
**Goal:** Eliminate Snowflake from the gktuition-tutor-engine entirely, replacing it with an embedded vector store + a small local SQL/state store, with **no degradation in student experience**, proven by the existing eval harness before cutover.

---

## 0. Why, and the one rule that governs this plan

The DAY_34 cost incident (~€18/day, ~€88 MTD) was **idle warehouse cost**, not the cost of serving students — and it's already fixed and capped. So this migration is **not an emergency**: it's a deliberate simplification to (a) remove the warehouse cost model permanently, (b) drop a heavyweight enterprise dependency we're barely using, and (c) remove vendor lock-in. Our retrieval workload is semantic search over a *bounded* corpus (the LCHL Maths curriculum) — a textbook fit for an embedded store.

**The governing rule: this is eval-gated, not faith-based.** We do not cut any traffic over to the new backend until it matches the locked baseline **P@1 ≥ 0.911** on the golden eval set. The eval harness is ported *first*, before any production change, so "is it as good?" is always a measured pass/fail, never a hope.

A second rule: **everything ships behind a feature flag and is reversible** until the final decommission step. Snowflake credentials stay live (and cheap, now the warehouse suspends) throughout, so rollback is a single flag flip.

---

## 1. Current state — what Snowflake actually does for us

Audited from the engine repo on DAY_34. Snowflake performs **five distinct jobs**, three of which already have injectable swap-seams in our own code:

| # | Job | Where it lives today | Swap seam already exists? |
|---|-----|----------------------|---------------------------|
| 1 | **Semantic search** — 3 Cortex Search services: `TUTOR_SEARCH` (concept), `SOLUTIONS_SEARCH` (solution lookup), `SUMMARY_SEARCH` (strand summaries) | `api/orchestrator/retriever.py` via `SNOWFLAKE.CORTEX.SEARCH_PREVIEW` | Partially — `_search_preview()` is the single chokepoint |
| 2 | **Structured analytics** — Cortex Analyst text-to-SQL over exam-parts tables (`ANALYTICAL` query class: "how often did topic X appear on Paper 2", etc.) | `retriever.py::_default_analyst_caller` + `snowflake/cortex_analyst/` | No — distinct workstream |
| 3 | **L3 semantic cache** — response cache, 30-day TTL | `api/firewall/L3_semantic_cache.py`, table `GKTUITION_TUTOR.CORTEX.QUERY_CACHE` | **Yes** — injectable `set_store()` storage seam |
| 4 | **Spend-cap state** — per-tier daily Anthropic spend ledger (the L5 kill switch) | `api/firewall/L5_kill_switch.py`, table `GKTUITION_TUTOR.RAW.DAILY_SPEND` | **Yes** — injectable `set_storage(reader, incrementer)`, in-memory default already shipped |
| 5 | **Query log sink** — per-query observability/accounting | `api/observability/snowflake_log_sink.py`, table `GKTUITION_TUTOR.RAW.QUERY_LOG` | Yes — sink is already an abstraction |

Supporting machinery that also touches Snowflake: the connection/auth layer (`retriever.py::_get_or_open_snowflake`, dual `SNOWFLAKE_*`/`SF_*` env reads), the loaders (`snowflake/load_*.py`), the index DDL (`snowflake/*.sql`), the `RM_DAILY_BUDGET` resource monitor, the `scheduled_eval.yml` + `smoke_canonical_queries.yml` workflows, and the `fly.toml` warehouse/secret config.

**The retrieval scoring contract is the crown jewel to preserve.** `retriever.py` consumes a Cortex hit's `@scores` block: `reranker_score` (unbounded, sigmoid-normalised), `cosine_similarity`, and `text_match`. `RETRIEVAL_FLOOR = 0.30`, the optional blended score (`w_r=0.6, w_c=0.3, w_t=0.1`), and AGENT_21/24's query-rewrite gating were **all tuned against this signal**. Any replacement must produce a comparable, calibrated `[0,1]` score — which means a **reranker is not optional**, it's load-bearing.

**Source of truth is git, not Snowflake.** The corpus (`tutorials/LCHL_*/*.md`, `_SUMMARY-*.md`, exam parts) lives in the `career-transition-2026` repo. Snowflake tables and embeddings are *derived*. This means the new store is always rebuildable from the repo, and we are not "extracting" trapped data — a major de-risker.

---

## 2. Target architecture

Replace the single Snowflake platform with four small, cheap, local pieces, all running on (or beside) the existing Fly app:

1. **Embedded vector store** — `LanceDB` (recommended) or `sqlite-vec`. Holds the tutorial / solution / summary chunks + their embeddings. Lives on a Fly volume; rebuildable from the corpus. For a corpus this size (tens of thousands of chunks at most), search is sub-millisecond and in-process — **no cold start, no warehouse, no per-query resume.**
2. **Embedding model** — computed once at index time and once per query. Options: a hosted API (Voyage `voyage-3`, OpenAI `text-embedding-3-small` ~$0.02/1M tokens) or a local model (`bge-small`, `arctic-embed`). API is simpler/no-RAM-cost; local is zero-marginal-cost but needs the model resident.
3. **Reranker** — to reproduce the load-bearing `reranker_score`. Options: a hosted rerank API (Cohere Rerank, Voyage Rerank — small per-query cost, one network hop) or a local cross-encoder (`bge-reranker-base`, needs CPU/RAM). **This is the single most important quality decision** (see §5).
4. **Local SQL / state store** — `SQLite` (or `DuckDB` for the analytics path). Hosts the L3 cache, the spend-cap ledger, and optionally the query log. DuckDB additionally replaces Cortex Analyst's SQL execution.

Snowflake-shaped jobs map cleanly onto these:

| Snowflake job | Replacement |
|---|---|
| Cortex Search (×3) | LanceDB similarity search + reranker, behind the existing `_search_preview` seam |
| Cortex Analyst (text-to-SQL) | DuckDB over the exam-parts tables + Claude generating SQL (or templated queries — see §5) |
| L3 cache (`QUERY_CACHE`) | SQLite table, swapped in via `L3_semantic_cache.set_store()` |
| Spend ledger (`DAILY_SPEND`) | SQLite table, swapped in via `L5_kill_switch.set_storage()` |
| Query log (`QUERY_LOG`) | SQLite table or Langfuse (already wired) |
| `RM_DAILY_BUDGET` resource monitor | Not needed — no warehouse. The app-level L5 spend cap remains the real cost guard for Anthropic. |

**What does NOT change:** the synthesiser, voice anchoring (AGENT_15), query rewriting (AGENT_21/24), the firewall layers L1/L2/L4/L6, the `/query` contract, and the entire student-facing answer. Retrieval is a backend swap beneath all of that.

---

## 3. Decisions to lock before building (§ for review)

These are the choices that shape effort and quality. Recommended defaults in **bold**; revisit with Paul.

- **Vector store:** **LanceDB** (embedded, handles metadata filtering + millions of vectors, simple Python API). Alternative: `sqlite-vec` if you want one SQLite file for *everything* (vectors + cache + ledger + logs).
- **Embedding model:** **Voyage `voyage-3` or OpenAI `text-embedding-3-small`** (hosted, no RAM cost, cheap). Pick local `bge-small` only if you want zero embedding-API dependency and accept ~400MB resident.
- **Reranker:** **Cohere Rerank or Voyage Rerank (hosted)** to start — fastest path to parity, small per-query cost, no RAM. Move to a local cross-encoder later if the per-query rerank cost or the extra vendor bothers you. *Do not skip the reranker* — cosine-only will likely regress P@1 on the within-strand and single-word cases.
- **Analytics path:** **DuckDB + Claude text-to-SQL** for the `ANALYTICAL` class, OR — safer and cheaper — **templated parameterised queries** for the handful of canonical analytical questions (see `snowflake/cortex_analyst/canonical_queries.md`). Free-form LLM SQL is more flexible but needs guardrails.
- **Query log home:** **SQLite** (simplest) or **Langfuse** (already integrated, off-box, no volume growth concern).
- **Persistence:** Fly **volume** for the LanceDB + SQLite files, plus a CI step that can rebuild the index from the corpus on demand (belt-and-suspenders; the corpus in git is the real backup).

---

## 4. Phased plan (eval-gated, reversible)

Each phase is independently shippable. Phases 1, 3 can run in parallel; Phase 2 is the critical path.

### Phase 0 — Spike + lock the parity gate *(0.5 dispatch)*
- Port `eval/score_against_cortex_search.py` into a backend-agnostic scorer that can score **either** Cortex **or** the local stack against the golden subset and the full 3,194-row set.
- Record the current locked baseline number from a clean Cortex run (P@1, plus per-strand breakdown) as the **gate to beat**.
- Offline spike: embed ~200 golden chunks with the chosen embedding model + reranker, measure P@1. Decide go/no-go on the embedding+rerank stack *before* writing production code.

### Phase 1 — Build the indexer *(1 dispatch)*
- New script `scripts/build_local_index.py`: walk the corpus markdown (same source the loaders read), chunk identically to the current `RAW.TUTORIALS` / `RAW.SUMMARIES` / exam-parts shape, compute embeddings, write to LanceDB. Idempotent, rerunnable, deterministic.
- This is purely additive — no app behaviour changes yet.

### Phase 2 — Local retriever behind a flag *(2 dispatches — the hard part)*
- Implement `_search_preview_local()` (and per-service variants) that query LanceDB + rerank and return hits in the **exact `@scores` shape** the existing parsers expect (`reranker_score`, `cosine_similarity`, `text_match`).
- Add `RETRIEVAL_BACKEND = cortex | local` flag (default `cortex`). Route `_from_tutor_search` / `_from_solutions_search` / `_from_summary_search` through the flag.
- **Gate:** run the Phase-0 scorer against `local`. Recalibrate `RETRIEVAL_FLOOR` and the blended-score weights for the new score distribution. **Must reach P@1 ≥ 0.911** (and no strand regressing badly) before this phase is "done". Shadow-run in prod (log both backends' top-K, serve `cortex`) for a few days to compare on real traffic.

### Phase 3 — Swap cache / spend-ledger / log to SQLite *(1 dispatch, parallelisable)*
- Implement SQLite-backed `store`/`lookup` for L3 (`set_store`), and `reader`/`incrementer` for L5 (`set_storage`). These seams **already exist** — this is mostly writing the SQLite impls + wiring them in `firewall/wire.py`.
- Point the query-log sink at SQLite or Langfuse.
- Low risk; independent of retrieval.

### Phase 4 — Replace Cortex Analyst *(1–2 dispatches)*
- Load exam-parts into DuckDB at index time (from the same source as `snowflake/load_exam_parts.py`).
- Implement the `ANALYTICAL` path: either Claude-generated SQL against the DuckDB schema (with a read-only, allowlisted-tables guard) or templated queries for the canonical questions. Behind a `ANALYTICS_BACKEND` flag.
- Lowest-traffic query class — fine to ship last.

### Phase 5 — Cutover *(operator + 0.5 dispatch)*
- Flip `RETRIEVAL_BACKEND=local` (and `ANALYTICS_BACKEND=local`) in prod once Phase 2/4 gates are green.
- Keep `min_machines_running = 1` for the app (warm FastAPI + embedding/rerank, cheap on Fly) so there's no cold start.
- Monitor the smoke test + a fresh eval run for 3–7 days with Snowflake still connected for instant rollback (`RETRIEVAL_BACKEND=cortex`).

### Phase 6 — Decommission Snowflake *(operator + 0.5 dispatch)*
Only after a clean monitoring window. Checklist in §6.

**Rough total effort:** ~6–8 focused agent dispatches over a few part-time weeks. Phase 2 (retriever + parity) is ~half the work and the only place real risk lives.

---

## 5. Risks & mitigations

- **Retrieval-quality regression (the main risk).** Mitigated by: eval-first gate, reranker mandatory, shadow comparison on real traffic, RETRIEVAL_FLOOR + blended-weight recalibration, per-strand eval breakdown so a single strand can't silently rot.
- **Reranker cost/latency vs RAM.** Hosted rerank adds ~1 network hop + a fraction of a cent per query; local cross-encoder adds CPU/RAM (likely a 512MB→1GB Fly bump). Decide in §3; start hosted for speed, optimise later.
- **Persistence/durability of the Fly volume.** Mitigated because the corpus in git is the source of truth — `build_local_index.py` rebuilds everything. Add a CI artifact of the built index as a convenience.
- **Embedding/rerank model warm-up (if local).** Keep the app machine warm (`min_machines_running=1`, ~$2/mo) — far cheaper than the old warehouse warming.
- **Analyst text-to-SQL correctness.** Prefer templated queries for canonical analytical questions; gate free-form LLM SQL behind read-only + table allowlist.
- **Hidden Snowflake reads.** Audited the obvious ones (retriever, L3, L5, log sink, analyst); during Phase 2/3 grep for any stray `_cursor()` / `snowflake.connector` use before decommission.

---

## 6. Decommission checklist (Phase 6 — do not run until cutover is proven)

- [ ] Confirm `RETRIEVAL_BACKEND=local` + `ANALYTICS_BACKEND=local` have run clean in prod for ≥1 week, eval green.
- [ ] Remove Snowflake from `firewall/wire.py` startup wiring (cache/spend now SQLite).
- [ ] Delete/retire `_get_or_open_snowflake`, `_cursor`, `_search_preview`, `_default_analyst_caller`, and the `snowflake.connector` dependency from `api/`.
- [ ] Remove `snowflake_log_sink.py` (or repoint) and the `RAW.*` table assumptions.
- [ ] Update `scheduled_eval.yml` + `smoke_canonical_queries.yml` to target the local stack (or retire `scheduled_eval` — it currently points at the now-defunct `WH_EVAL`).
- [ ] Strip Snowflake secrets from Fly (`SF_*`, `SNOWFLAKE_*`, `WP_JWT_SECRET` stays) and the `fly.toml` warehouse env (`HEALTHZ_SNOWFLAKE_CHECK_ENABLED` line, `SNOWFLAKE_LOG_SINK_*`).
- [ ] Archive the `snowflake/` DDL + loaders directory (keep in git history; remove from runtime).
- [ ] In Snowflake: drop the Cortex Search services, the `WH_TUTOR`/`WH_EVAL` warehouses, and the resource monitors. Optionally keep the account dormant (zero cost when nothing runs) for a month before fully closing, as a final rollback hatch.
- [ ] Update `docs/ops/runbook.md` and `gktuition/notes.md` to reflect the Snowflake-free architecture.

---

## 7. What this buys you

- **Idle cost → ~$0.** No warehouse to keep warm; the cost driver behind the DAY_34 incident is structurally gone, not just configured away.
- **Latency → equal or better.** In-process vector search has no cold start; the only wait left is the LLM synthesis, same as today.
- **Marginal cost per query → pennies, mostly Anthropic** (embedding + optional rerank are sub-cent), still guarded by the L5 spend cap.
- **One fewer vendor + no lock-in.** Data is in git; the stack runs on the Fly machine you already pay for.

The trade is real engineering (Phase 2 especially) and reproducing Cortex's managed reranking — but it's bounded, well-understood work, and every step is eval-gated and reversible.
