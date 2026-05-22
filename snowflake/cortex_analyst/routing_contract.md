# Routing contract — Cortex Analyst vs Cortex Search

**Owner:** Agent 04 (Cortex Analyst). **Audience:** the FastAPI orchestrator
that fronts the GKTuition AI Tutor.
**Pinned by:** ADR-004 Decision 2 (analytical-vs-RAG split) and Decision 1
(three Cortex Search Services).

This contract specifies the deterministic classifier the FastAPI `/query`
handler uses to decide whether an incoming question goes to Cortex Analyst
(structured, text-to-SQL) or to the Cortex Search fan-out (RAG over tutorials,
solutions, summaries). It is **v1** — keyword-based, no LLM call, sub-millisecond
latency — and is meant to stay v1 unless the eval shows the keyword classifier
is materially mis-routing live queries.

## The rule

Classify each incoming query as **analytical**, **rag**, or **both**, then
dispatch accordingly.

### Route to Cortex Analyst (`query_class = "analytical"`)

The query contains **any** of the following phrases (case-insensitive,
substring match):

```
how often
how many times
how many ... questions       (* matches "how many discriminant questions", "how many integration parts", etc.)
how many ... parts
frequency
what percentage
percentage of
proportion of
average marks
mean marks
marks per part
trend
trends
year-over-year
year over year
since 20                     (* 'since 2020', 'since 2018' etc. — the digit prefix narrows the match)
in the last \d+ years        (* regex — 'in the last 3 years', 'in the last five years')
compared to
versus
vs
deferred vs main
which strand has
which strands have
most cited
most-cited
most often
appearance count
```

Implementation note: `"how many … questions"` and `"how many … parts"` are
applied as `\bhow many\b.*\b(questions|parts|appearances|times)\b` regexes
so that incidental "how many" usage ("how many roots does this cubic have")
doesn't false-positive into the analytical bucket.

When a query matches the analytical rule, the FastAPI handler:

1. Calls the Cortex Analyst REST endpoint with the user's question and the
   staged `semantic_model.yaml` pointer.
2. Receives a generated SQL block.
3. Executes the SQL against the warehouse (cost-tracked under the same €5/day
   resource monitor as everything else).
4. Returns the result rows alongside the original question in the standard
   ADR-003 JSON contract, with `query_class = "analytical"` and
   `model_used = "cortex.analyst"`.

### Route to the RAG fan-out (`query_class ∈ {concept, solution_lookup, summary_request}`)

Everything that **doesn't** match the analytical rule goes through Cortex
Search. The fan-out itself sub-classifies further (see ADR-004 Decision 1
and Agent 01's deliverables) — that sub-classification is out of scope for
this document. From Cortex Analyst's perspective, "anything that isn't
analytical" is the only relevant case.

### Route to both (`query_class = "ambiguous"`)

A query that matches the analytical rule **and** also carries strong RAG
signal (specifically: contains *"why"*, *"explain"*, *"how does"*,
*"how do I"*, or *"prove"*) is fanned out to both paths in parallel. The
synthesiser layer composes the two answers into a single response — the
RAG answer typically becomes the prose explanation and the Analyst result
typically becomes a bullet of supporting numbers.

Ambiguous routing is the most expensive path (two retrieval calls + one
synthesis call), so the trigger is intentionally strict: an analytical
keyword **plus** a conceptual keyword in the same query. Lone "why" or
"explain" never triggers Analyst on its own.

## Examples

| Query | Match | `query_class` |
|---|---|---|
| "How often has integration by parts appeared on Paper 1 in the last five years?" | `how often` + `in the last \d+ years` | `analytical` |
| "Which strands have grown on P2 since 2020?" | `which strands have` + `since 20` | `analytical` |
| "What's the average mark allocation for a 'nature of roots' question?" | `average mark` (partial), `marks per part` synonym | `analytical` |
| "Explain how the chain rule works." | (no match) | `concept` (RAG only) |
| "How was 2024 P2 Q5 solved?" | (no match — no analytical keyword) | `solution_lookup` (RAG only) |
| "I'm cramming The Line tonight — what do I need to know?" | (no match) | `summary_request` (RAG only) |
| "Why has differentiation grown so much since 2020?" | `since 20` + `why` | `ambiguous` → both |
| "Compared to integration, how often does differentiation come up on Paper 1?" | `compared to` + `how often` | `analytical` |

## Rationale (five paragraphs)

**Why deterministic, not LLM-classified.** An LLM classifier costs one
extra round-trip plus token spend per query, has non-deterministic
behaviour that's hard to eval, and adds a failure mode (the classifier
itself can be wrong or unavailable). A keyword classifier is essentially
free, deterministic, observable in a single regex print-out, and good
enough for a workload where the analytical signal is overwhelmingly
verbal — students saying "how often" and "since 20XX" are the people
asking analytical questions. The minute the eval set says otherwise (false
negative rate on analytical queries above ~5%, or false positives causing
expensive double-routing above ~3%), promote to an LLM classifier — the
route labels are the stable contract, the classifier implementation is a
swap-in.

**Why this exact keyword list.** Each phrase corresponds to a SQL shape the
semantic model is verified to produce. "How often" and "how many times" →
`COUNT(*)`. "Frequency" / "appearance count" → same. "What percentage" /
"proportion" → `COUNT(*) / SUM(COUNT(*)) OVER ()`. "Average marks" / "marks
per part" → `AVG(marks)`. "Trends" / "year-over-year" / "since 20XX" →
`GROUP BY year ORDER BY year`. "Compared to" / "vs" → CTE-based delta
patterns or `COUNT_IF` pivots. The list was harvested from the actual
phrasings in `LCHL_exam_trends.md` and the ten canonical queries in
`canonical_queries.md`. New phrases land here only when an eval-set query
fails to route correctly with the current list — additions are eval-driven.

**Why the ambiguous path exists at all.** A genuinely-ambiguous question
("why has differentiation grown so much since 2020") has two answers — a
RAG-style narrative ("here's what changed in the SEC marking scheme...")
and an analytical-style number ("there are 14 differentiation parts in
2025 vs 6 in 2019"). Routing it to only one path drops half the answer.
The synthesiser's job is to weave both into one response, which is exactly
the shape the ADR-003 JSON contract is built for: `answer` is the prose,
the `retrieved` array carries the RAG citations, and a new `analytical_rows`
field (declared in ADR-004 but not yet implemented in Phase 1.5) carries
the Analyst output. v1 puts the Analyst rows into the `answer` string and
defers the structured field to Phase 2.

**Why no recall / precision targets pinned here.** The classifier doesn't
have one; it's the eval harness's job (Agent 05). The contract this
document fixes is the **interface** — which keywords trigger which route,
and what the orchestrator should do with each label. Tuning the recall/
precision of the analytical bucket is downstream work, gated on
Agent 05's eval runs. If those runs show the analytical recall is below
~90% (i.e. more than 1-in-10 analytical questions are being mis-routed to
RAG), the fix is either (a) add the missing phrases to the keyword list,
or (b) promote the classifier to LLM-backed. The eval harness is what
discovers which case applies.

**Why this is in `cortex_analyst/` and not in the FastAPI repo.** Two
reasons. First, the routing contract is a property of the Cortex Analyst
service — it specifies what kinds of questions the Analyst is meant to
answer, which is information the Analyst needs documented next to its own
artefacts (semantic model, verified queries) for any future
synonym-maintenance pass to make sense. Second, the orchestrator's
implementation of the contract is mechanical (one regex match against the
keyword list), so the contract document is doing the load-bearing work
and the code is just executing it. When the orchestrator is built, the
implementation can quote this document verbatim and avoid keyword-list
drift across two repos.

## What this contract does NOT specify

- The implementation of the orchestrator itself (Phase 1.5 FastAPI
  deliverable, not Agent 04's mandate).
- The sub-classifier that picks between TUTOR_SEARCH, SOLUTIONS_SEARCH, and
  SUMMARY_SEARCH within the RAG path (ADR-004 Decision 1; Agent 01/02
  deliverables; documented separately).
- The Anthropic / Cortex generation-model selection for the synthesiser
  (ADR-003 Decision 2 — two-tier routing on confidence-of-retrieval).
- The cost-firewall layers (ADR-002 — independent of routing).
- The `image_extracted` route label (ADR-004 Decision 3; Agent 06).
