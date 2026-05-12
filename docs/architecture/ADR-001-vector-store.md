# ADR-001: Snowflake Cortex Search as the vector store

| Status | Accepted (April 2026) |
|---|---|
| Decider | Paul Keogan (sole maintainer) |
| Date | 2026-04-15 |

## Context

The gktuition-tutor-engine needs a vector-search backend over ~550 Whisper-transcribed LCHL maths tutorials (chunked, ~30,000 chunks projected at full corpus). Three viable options were considered:

1. **Snowflake Cortex Search** — managed retrieval inside Snowflake, where the structured corpus already lives via dbt.
2. **Self-hosted pgvector** on Fly.io or a small VM.
3. **Pinecone / Weaviate** or similar SaaS vector DB.

Decision criteria: time-to-first-working-prototype, ongoing operational burden, integration with the existing Snowflake-based corpus pipeline, and — being open about this — strategic CV-leverage for the Senior Analytics Engineer roles I'm targeting through 2026.

## Decision

**Adopt Snowflake Cortex Search as the v1 vector store.**

## Consequences

- **Integration is trivial.** Corpus, embeddings, and retrieval queries all live in the same Snowflake account. No data movement, no separate auth model, no extra deployment surface.
- **Operational burden ≈ 0.** Managed service; daily-spend cap configurable via Snowflake resource monitors. No vector-DB ops layered on top of the existing pipeline.
- **~€30–60/month premium** over self-hosted pgvector at projected query volume. Acceptable given the time saved and the alignment with my existing Snowflake-first stack.
- **Cortex Search appears in only ~19% of Dublin Senior Analytics Engineer / Data Engineer job descriptions** (April 2026 sample, n=20) — but consistently in Tier-1 listings (Mastercard, Intercom-tier, Anthropic-adjacent). Building on it produces a scarce-and-rising CV signal that pairs with my existing Cortex AI Analyst production deployment at Eventbrite.

## Trade-offs

- **Lock-in is mitigated.** Migration to pgvector is a documented one-week swap if cost or feature pressure ever requires it. The chunking schema, retrieval interface, and eval harness are vector-DB-agnostic; only the storage and similarity-search calls would change.
- **Cortex Search is relatively new** (~12 months in GA at decision time). Failure mode considered: if Snowflake deprecates or sharply re-prices the product, the documented migration path above keeps the build viable without rearchitecting the rest of the system.
