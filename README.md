# gktuition-tutor-engine

> 🚧 **Status: Phase 1 baseline locked; Phase 2 (Fly.io deploy) underway.** Active build May–August 2026; first public demo target: Phase 3 launch (~mid-July 2026).

A retrieval-augmented AI tutor over the [GKTuition.ie](https://www.gktuition.ie) corpus of ~550 Irish Leaving Cert Higher Level (LCHL) mathematics tutorial videos. The engine answers a student's maths question by classifying it, pulling the most relevant tutorial fragments from Snowflake Cortex Search, synthesising a step-by-step answer with grounded citations, and (for analytical questions) rendering a Plotly chart over the corpus's exam-trends data.

This repo holds the **engineering and methodology** of the build — the FastAPI orchestrator, the Snowflake schemas + loaders, the six-layer cost firewall, the eval framework, the React widget, the deploy story, and the architecture decisions that produced each of them. The commercial corpus and production secrets live separately.

## Read the system overview first

**[`docs/architecture/SYSTEM_OVERVIEW.md`](docs/architecture/SYSTEM_OVERVIEW.md)** — the pull-it-all-together engineering summary. Layers, query lifecycle, retrieval architecture (3 Cortex Search services + Cortex Analyst), two-tier LLM routing (Cortex COMPLETE soft path / Claude Haiku hard path), the L1–L6 cost firewall, multimodal `/image_query`, visualisation layer, content pipeline, eval baseline, and deploy story. ~10 min read.

## Architecture decisions

Significant design choices are captured as ADRs in [`docs/architecture/`](docs/architecture/).

- [ADR-001](docs/architecture/ADR-001-vector-store.md) — Vector store: Snowflake Cortex Search.
- [ADR-002](docs/architecture/ADR-002-product-model.md) — Access model & cost controls: free-for-all with six-layer defence.
- [ADR-003](docs/architecture/ADR-003-system-architecture.md) — System architecture: 3-layer (WordPress widget · FastAPI on Fly.io · Snowflake), two-tier LLM routing.

## Phase-1 baseline (locked 2026-05-21)

| Metric | Value | Target |
|---|---|---|
| Precision@1 (golden subset, 200 rows) | 0.710 | ≥ 0.65 |
| Recall@5 | 0.985 | ≥ 0.90 |
| MRR | 0.835 | — |
| Errors over 200 rows | 0 | 0 |

Methodology + per-strand breakdown: [`docs/architecture/SYSTEM_OVERVIEW.md#eval-and-quality`](docs/architecture/SYSTEM_OVERVIEW.md#eval-and-quality).

## Operating the live app

Eight recurring ops procedures (health check, spend dashboard, kill switch, rollback, content-sync recovery, etc.) are in [`docs/ops/runbook.md`](docs/ops/runbook.md).

## Repo map

| Path | What it holds |
|---|---|
| [`api/`](api) | FastAPI orchestrator — classifier, retriever, synthesiser, auth, routes, cost firewall, observability sink. |
| [`snowflake/`](snowflake) | Bootstrap SQL, loader scripts, three Cortex Search services, Cortex Analyst semantic model. |
| [`content-pipeline/`](content-pipeline) | Frontmatter validator, change-detector, sync runners, content-edit GitHub Action. |
| [`widget/`](widget) | React (Vite) chat widget, JWT-decoded tier handling, Plotly graph component. |
| [`eval/`](eval) | Eval golden set, scoring scripts, baseline history. |
| [`docs/`](docs) | Architecture (ADRs + system overview), ops runbook, design docs. |

## Contact

Paul Keogan · [LinkedIn](https://www.linkedin.com/in/paul-keogan-5b1753158) · pkeogan@tcd.ie
