# gktuition-tutor-engine

> 🚧 **Status: in progress.** Active build May–August 2026. First public demo target: Phase 3 launch (~mid-July 2026).

A retrieval-augmented AI tutor over the [GKTuition.ie](https://www.gktuition.ie) corpus of Irish Leaving Cert Higher Level (LCHL) mathematics tutorial videos (~550 videos, ~100 hours of recorded teaching). This repo holds the **engineering and methodology** of the build — architecture decisions, ingestion pipeline, postprocessing rules, eval framework, and FastAPI scaffold. The commercial corpus and production deployment live in a separate private repo.

## Architecture overview

Student browser → gktuition.ie (WordPress + embedded chat widget)
↓
Backend API (FastAPI on Fly.io v1 → AWS Lambda production)
↓
Snowflake Cortex Search + Cortex COMPLETE / Claude API

The tutor is embedded in gktuition.ie as a chat widget; students never see Snowflake or the backend. The freemium product model, two-tier LLM routing, and full architecture rationale are documented in the ADRs below.

## Architecture Decision Records (ADRs)

| # | Decision | Status |
|---|---|---|
| [ADR-001](docs/architecture/ADR-001-vector-store.md) | Snowflake Cortex Search as the vector store | ✅ accepted |
| ADR-002 | Freemium product model + two-tier LLM routing | in progress |
| ADR-003 | WordPress widget + FastAPI/Lambda + Snowflake architecture | planned |

## About the corpus

The LCHL maths corpus spans the full Irish Leaving Certificate Higher Level mathematics syllabus across both papers and 22 topic strands. Whisper transcription, hand-correction via a postprocessing rules engine, and structured tutorial markdown generation are ongoing through Phases 1–2 of the build.

## Contact

Paul Keogan · [LinkedIn](https://www.linkedin.com/in/paul-keogan-5b1753158) · pkeogan@tcd.ie
