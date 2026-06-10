# System overview

> A pull-it-all-together engineering summary of the GKTuition AI tutor — how
> the layers fit, why each piece looks the way it does, and what the
> measurable quality bar is. For deep rationale on individual design choices,
> follow the ADR links inline. For operational procedures, see
> [`docs/ops/runbook.md`](../ops/runbook.md).

## What this is

A retrieval-augmented AI tutor over a corpus of ~550 video tutorials
covering the Irish Leaving Cert Higher Level (LCHL) mathematics syllabus.
A student types a maths question (or photographs one from a textbook) into
a chat widget on [gktuition.ie](https://www.gktuition.ie); the system
classifies the question, retrieves the most relevant tutorial fragments
from Snowflake, synthesises an answer that cites those tutorials, and
returns it in under a couple of seconds. The student never sees Snowflake
or the orchestrator — only a chat panel and YouTube-embedded tutorial
links.

The corpus itself is structured: each video has a hand-written
markdown transcript with YAML frontmatter (topic strand, timestamps,
load-bearing techniques, cross-references). On top of that sits a
machine-readable solutions corpus for ten years of past LCHL papers,
each part cross-referenced to the tutorials that teach the relevant
technique. Both feed Snowflake Cortex Search.

## System layers

```
   Student browser
   ──────────────────────────────────────────────────────────────────
   WordPress  +  embedded React widget  (gktuition.ie)
                │
                │  JWT (tier=anonymous / authenticated_free / paying)
                ▼
   FastAPI orchestrator on Fly.io  (this repo, /api)
                │
                │  Snowflake Python connector (key-pair auth)
                ▼
   Snowflake  ─  Cortex Search × 3   (TUTOR / SOLUTIONS / SUMMARY)
              ─  Cortex Analyst       (semantic model on EXAM_PARTS_FLAT)
              ─  Cortex COMPLETE      (soft-path generation)
                │
                │  hard-path queries only
                ▼
   Anthropic Claude  ─  claude-haiku-4-5
```

Three layers, each with a single job:

- **WordPress widget** ([`/widget`](../../widget))  — a static React build
  embedded on every tutorial page. JWT-gated for tier; renders streaming
  responses, inline citations, and Plotly graphs. (The widget's *source*
  lives here; the WordPress plugin that mounts it lives in a separate
  private repo — see "Where the code lives" below.)
- **FastAPI orchestrator** ([`/api`](../../api)) — classifies the query,
  fans out to the right retrieval surface, calls the right LLM, applies
  the six-layer cost firewall, returns a typed contract response.
- **Snowflake** ([`/snowflake`](../../snowflake)) — single source of
  truth for the corpus, search, semantic-layer analytics, query log, and
  spend caps.

The full layer rationale (including why Fly.io for Phase 1.5–3 and AWS
Lambda for Phase 4+) is in
[`ADR-003-system-architecture.md`](ADR-003-system-architecture.md).

## Where the code lives — three repos

The product is deliberately split across three repositories with strict
public/private boundaries:

| Repo | Visibility | Holds |
|---|---|---|
| `gktuition-tutor-engine` (this repo) | **Public** | The engine: FastAPI orchestrator + cost firewall, Snowflake definitions, content-pipeline tooling, eval framework, and the **React widget source** (`/widget`). No corpus content, no secrets — ever. |
| `gktuition-prod` | Private | The commercial corpus (tutorial transcripts) and the **WordPress mounting plugin** (`wordpress-plugin/gktuition-ai-tutor/`): JWT mint, tier resolver, REST endpoint, PHPUnit tests. This plugin is what embeds the widget on gktuition.ie. |
| `gktuition-website` | Private | The gktuition.ie WordPress site itself — themes (incl. `salient-child`) and site plugins. Theme/site code only; it does **not** contain the tutor plugin. |

Decision on record (Option A): the mounting plugin stays in
`gktuition-prod`; the website repo holds theme code only.

## Query lifecycle

A `POST /query` carries one student utterance plus their tier (decoded
from the JWT). What happens to it, in order:

1. **L1 — Cloudflare Turnstile** validates that the caller is a real
   browser, not a scraper.
2. **L2 — per-IP / per-tier rate limit** — anonymous tier gets the
   tightest envelope.
3. **L3 — semantic cache** — sha256 over the normalised question + tier
   + model. A hit skips all the way to a 200 in <10ms.
4. **Classifier** assigns one of six classes: `concept`,
   `solution_lookup`, `summary_request`, `analytical`, `image_extracted`,
   `ambiguous`. The class drives both retrieval and routing.
5. **Retriever** dispatches to the right Cortex Search service (or to
   Cortex Analyst for `analytical`). Fan-out fires on `ambiguous`.
6. **L4 — model router** picks the soft or hard model based on class +
   tier + retrieval confidence.
7. **L5 — kill switch** checks the day's spend against the three nested
   caps (anonymous-only, anonymous + authenticated_free, global). Caps
   fire silently — the student gets a graceful "we're at capacity for
   today, here are the cached tutorials we found" fallback, not a 5xx.
8. **Synthesiser** renders the chosen model's response with grounded
   citations and (for `analytical` answers) an optional Plotly figure.
9. **L6 — observability** writes a structured query-log row to
   `RAW.QUERY_LOG` asynchronously through a batched Snowflake sink.

The contract that gets serialised back to the widget is defined in
[`api/orchestrator/contract.py`](../../api/orchestrator/contract.py) —
typed Pydantic, every field documented, no implicit serialisation.

## Retrieval architecture

Cortex Search isn't a single index; it's three, kept independent on
purpose:

| Service | Indexed | Used for |
|---|---|---|
| `TUTOR_SEARCH` | 237 tutorial markdowns, multi-field with topic + load-bearing technique columns | `concept` queries — *"how do I factorise difference of squares"* |
| `SOLUTIONS_SEARCH` | 1,213 exam parts across ten years of LCHL papers, with cross-refs to the tutorials that teach each part | `solution_lookup` queries — *"how was 2024 P2 Q5 solved?"* |
| `SUMMARY_SEARCH` | 20 hand-written strand summaries (cram-sheet style) | `summary_request` queries — *"I'm cramming The Line tonight"* |

A fourth retrieval surface, **Cortex Analyst**, runs over a semantic
model layered on the `EXAM_PARTS_FLAT` view (see
[`snowflake/cortex_analyst/`](../../snowflake/cortex_analyst)). It's
addressed only by the `analytical` class — questions like *"how often
has integration appeared on Paper 1 since 2020?"* — where the answer
isn't in any one document but emerges from counting across the corpus.
Cortex Analyst returns SQL plus a result set, which the synthesiser
turns into prose plus (for trend questions) a Plotly bar or line chart.

The three Search services + the one Analyst semantic model are
deliberately disjoint. The semantic model declares no relationships
between tables, which prevents Analyst from double-counting parts on a
trend question that's already targeting the by-tutorial grain. The same
disjointness is what lets the classifier's routing be cheap — no need
to reconcile overlapping result sets.

The retrieval design and the multimodal extension are recorded in
**ADR-004 (retrieval architecture and multimodal)**, which lives in the
private planning vault and is not mirrored in this repo. The image-path
section is excerpted publicly in
[`api/adr/ADR-004-section-image-path.md`](../../api/adr/ADR-004-section-image-path.md);
the routing decisions it pins are restated in
[`snowflake/cortex_analyst/routing_contract.md`](../../snowflake/cortex_analyst/routing_contract.md).

## Two-tier LLM routing

Every query takes one of two paths through generation:

- **Soft path: Cortex COMPLETE.** Snowflake-hosted `mistral-large2` (or
  similar). Same Snowflake warehouse compute that already paid for the
  search; no second API hop. Used for `concept` and `summary_request`
  queries — well-formed factual asks where a good corpus hit drives the
  whole answer. Cents per thousand queries.
- **Hard path: Anthropic Claude Haiku.** Used for `solution_lookup`,
  `analytical`, `image_extracted`, and `ambiguous` — anything that needs
  reasoning over multiple retrieved fragments, or step-by-step
  pedagogical pacing the soft model doesn't quite nail. ~10× more
  expensive per token, but reserved for the cases that actually need it.

The routing decision is one CASE expression in
[`api/firewall/L4_router.py`](../../api/firewall/L4_router.py) — class +
tier + retrieval confidence in, model name out. Override is a one-line
change.

## Cost firewall (L1–L6)

A hostile world means the question isn't whether the system *can* answer
a query, but whether the wallet *should* let it. Six layers, ordered
cheapest-first so the expensive checks never run on traffic the cheap
checks would have killed:

1. **L1 — Cloudflare Turnstile.** Browser/bot screen. Catches the
   crudest scrape attempts before they touch our compute.
2. **L2 — Rate limit.** Per-IP and per-tier sliding windows. Tighter for
   `anonymous`, looser for `paying`. Burst tolerance tuned for legitimate
   "I'm typing fast" usage.
3. **L3 — Semantic cache.** Sha256 on the normalised query + slugs +
   model + tier. Hits replay a previous response from
   `CORTEX.QUERY_CACHE` in <10ms with no LLM call. Stale rows are
   deleted on read; no scheduled cleanup needed.
4. **L4 — Model router.** Hard-path access is itself a gate: anonymous
   tier never sees the hard model on `concept` queries, no matter how
   ambiguous.
5. **L5 — Kill switch + spend caps.** Three nested daily caps stored in
   `RAW.DAILY_SPEND`. Each tier has its own cap; the kill switch fires a
   graceful "at capacity, here's the cached tutorial" fallback rather
   than a 5xx.
6. **L6 — Observability.** Batched async sink into `RAW.QUERY_LOG` —
   every request, every classifier decision, every model used, every
   cap-state at the time of the call. Never blocks request handling.

Layer-by-layer threat modelling, cap sizing, and the unit economics that
produced the cap numbers are in
[`ADR-002-product-model.md`](ADR-002-product-model.md) plus the per-layer
rationale notes in `api/firewall/`.

## Multimodal entry — `/image_query`

A second endpoint, [`POST /image_query`](../../api/routes/image_query.py),
takes a photograph (mobile camera or laptop screen capture) of a maths
question. The handler validates the upload (size, MIME, clarity), passes
the bytes to Claude's vision-capable model for OCR + structural
extraction, then folds the resulting text into the same orchestrator
pipeline as a `/query` would have used — assigned the
`image_extracted` class so the router sends it down the hard path.

This is the path that lets a student photograph a textbook question
they're stuck on, rather than typing it out. Cost-wise it's the most
expensive entry per call (vision tokens + reasoning tokens), which is
why it's tier-gated to `paying` only and rate-limited tighter than the
text endpoint.

## Visualisation layer

For `analytical` queries that return a result set (e.g. "how often has
integration appeared on Paper 1 since 2020?"), the synthesiser routes
through a small generator layer
([`api/visualisation/generators.py`](../../api/visualisation/generators.py))
that emits a Plotly JSON spec — bar, line, scatter, or histogram —
chosen by inspecting the result shape and the question's intent. The
widget side renders it via a small Plotly React wrapper. The Plotly JSON
is part of the contract response, so the API stays presentation-agnostic.

The eval set carries an `expected_graph_kind` column on the rows where a
visualisation would be helpful; the nightly eval scores both the
retrieval quality and the visualisation appropriateness.

## Content pipeline

Tutorial content changes in `tutorials/**/*.md` (the corpus, in a
sibling repo) trigger an automated propagation:

1. **Pre-commit hook** validates YAML frontmatter locally so bad content
   never reaches `main`.
2. **GitHub Action** on push runs `content-pipeline/sync/detect_changes.py`
   to identify which loaders need to fire (`load_tutorials`,
   `load_exam_parts`, `load_summaries`, `build_eval_set` — any subset).
3. **`run_loaders.py`** executes the affected loaders, MERGEs into the
   corresponding `RAW` tables, and logs the run in
   `RAW.CONTENT_CHANGE_LOG`.
4. **`refresh_cortex.py`** kicks the affected Cortex Search Services to
   re-index, then exits.

The whole flow runs in ~3–6 minutes from `git push` to "Snowflake has
the new content + Cortex Search has re-indexed". Audit history is in
`RAW.CONTENT_CHANGE_LOG`. The handbook
([`content-pipeline/docs/content-pipeline-handbook.md`](../../content-pipeline/docs/content-pipeline-handbook.md))
covers the day-to-day workflow plus the recovery path when a sync
partially fails.

## Eval and quality

A 3,194-row eval set is the system's quality gate, generated from a
combination of:

- **Per-tutorial phrasings** (~1,500 rows) — hand-written paraphrases of
  each tutorial's central question. *"What's the slope formula?"* /
  *"How do I work out the gradient between two points?"* / *"two
  points slope"* all map to the same expected tutorial.
- **Solution cross-references** (~1,700 rows) — every exam-part's
  cited tutorial becomes one row where the question is the exam-part's
  prompt and the expected answer is the cited tutorial.

A 200-row **golden subset** is stratified across topic strands +
difficulty tiers + question sources, and is the canonical surface for
trend analysis between commits.

**Locked Phase-1 baseline** (full corpus, golden subset):

| Metric | Value | Target |
|---|---|---|
| Precision@1 | 0.710 | ≥ 0.65 |
| Recall@5 | 0.985 | ≥ 0.90 |
| MRR | 0.835 | n/a |
| Phrasings precision@1 | 0.811 | ≥ 0.70 |
| Cross-ref precision@1 | 0.651 | ≥ 0.50 |
| Errors over 200 rows | 0 | 0 |

The baseline is locked in `eval/scoring_history/`; the nightly GitHub
Action re-scores and trips an alert if any metric regresses ≥ 3 points.

By topic strand, the strongest categories are Financial Maths (1.000),
Coordinate Geometry Circle (0.875), Coordinate Geometry Line (0.857).
The weakest is Algebra at 0.500 precision@1 with 0.833 recall@5 —
within-strand confusions (long-division vs. simultaneous-equations,
factorising vs. completing-the-square) where the right tutorial is in
the top-5 but not at rank 1. Algebra-tier blended scoring is the next
quality lever; targeted in the post-Phase-1 tuning pass.

The eval methodology, sampling strategy, and the metric definitions are
in [`eval/README.md`](../../eval/README.md).

## Deploy story

**Phase 1.5–3 (today through mid-2026 launch): Fly.io.** One
shared-cpu-1x machine, 256 MB RAM, scale-to-zero. Region `fra`
(Frankfurt), lowest p50 latency to Ireland of any Fly region. Cold
start is 3–6 s on first request after idle, accepted explicitly in
ADR-003's cost profile.

**Phase 4+ (>1,000 daily queries trigger): AWS Lambda.** Migration
contemplated in ADR-003 but explicitly deferred until the volume
trigger fires. Until then, the operational complexity of Lambda + API
Gateway + a separate observability stack isn't worth the per-call
savings. Architecture is shaped so the migration is plumbing not a
rewrite — the orchestrator is already a single ASGI app with no
in-process state besides the Snowflake connection pool.

CI/CD is GitHub Actions → `flyctl deploy`. The full deploy contract,
secrets list, and rollback procedure are in
[`docs/ops/runbook.md`](../ops/runbook.md).

## Repo map

| Path | What it holds |
|---|---|
| [`api/`](../../api) | FastAPI app — orchestrator, classifier, retriever, synthesiser, auth, routes, cost firewall, observability sink. |
| [`snowflake/`](../../snowflake) | Bootstrap SQL, three loader scripts, four search-service definitions, Cortex Analyst semantic model + canonical queries. |
| [`content-pipeline/`](../../content-pipeline) | Frontmatter validator, change-detector, sync runners, GitHub Action, runbook. |
| [`widget/`](../../widget) | React (Vite) chat widget source, JWT-decoded tier handling, Plotly graph component. (Mounted on gktuition.ie by the WordPress plugin in the private `gktuition-prod` repo.) |
| [`eval/`](../../eval) | Eval golden set (CSV-committed for portability), scoring scripts, methodology, baseline history. |
| [`docs/architecture/`](.) | ADRs 001–003 (vector store, product model, system architecture); this overview. |
| [`docs/ops/`](../ops) | Live runbook for the deployed app — health, spend, log queries, rollback. |
| [`scripts/`](../../scripts) | Setup scripts (Fly secrets, manual ingestion, transcribe worker). |
| [`dags/`](../../dags) | Airflow / ingestion DAGs for the corpus-build path. |

## Read next

- [`ADR-003-system-architecture.md`](ADR-003-system-architecture.md) —
  the system-design rationale in full.
- [`ADR-002-product-model.md`](ADR-002-product-model.md) — access model
  and cost-control philosophy.
- [`docs/ops/runbook.md`](../ops/runbook.md) — eight recurring ops
  procedures: health check, spend dashboard, kill switch, rollback.
- [`api/README.md`](../../api/README.md) — FastAPI app's own
  contributor docs.
- [`content-pipeline/docs/content-pipeline-handbook.md`](../../content-pipeline/docs/content-pipeline-handbook.md)
  — day-to-day content-editing workflow.
