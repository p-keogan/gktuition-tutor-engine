# ADR-003: System Architecture

- **Status:** Accepted
- **Date:** 2026-05-14
- **Supersedes:** none
- **Related:** ADR-001 (Vector Store — Snowflake Cortex Search), ADR-002 (Access Model and Cost Controls)

## Context

ADR-001 fixed the retrieval store (Snowflake Cortex Search). ADR-002 fixed the access model (free-for-all + six-layer cost firewall, €5/day kill switch). What remains is the **deployment topology, generation-layer model selection, frontend integration, and JSON response contract** — the decisions that, together, get a working AI tutor widget onto `gktuition.ie/staging/ai-tutor/` by end of Phase 1.5.

## Decision

Three logical layers, deployed as below:

```
                    Student browser
                          │
                          ▼
┌───────────────────────────────────────────────────────┐
│  gktuition.ie  (WordPress on WP Engine)               │
│  ┌─────────────────────────────────────────────┐      │
│  │ React widget — [gktuition_ai_tutor] shortcode│     │
│  │ Auth: current_user_can('subscriber') gate    │     │
│  └────────────────────┬────────────────────────┘      │
└───────────────────────┼───────────────────────────────┘
                        │  HTTPS · CORS scoped to gktuition.ie
                        ▼
┌───────────────────────────────────────────────────────┐
│  FastAPI on Fly.io (fra region)                       │
│  ┌─────────────────────────────────────────────┐      │
│  │ GET /query?q=...                            │      │
│  │   • Cloudflare Turnstile (firewall L1)      │      │
│  │   • Per-IP rate limit (L2)                  │      │
│  │   • Semantic cache lookup (L3)              │      │
│  │   • Two-tier LLM router (L4)                │      │
│  │   • Hard €5/day kill switch (L5)            │      │
│  │   • Monitoring webhook (L6)                 │      │
│  └────────────────────┬────────────────────────┘      │
└───────────────────────┼───────────────────────────────┘
                        │  Snowflake Python connector
                        ▼
┌───────────────────────────────────────────────────────┐
│  Snowflake (Enterprise, AWS-EU)                       │
│   • WH_TUTOR (XS, auto-suspend 60s, €5/day RM)        │
│   • Cortex Search Service over RAW.TRANSCRIPTS        │
│   • Cortex mistral-large2 (cheap path, ~80%)          │
└───────────────────────────────────────────────────────┘
                        │
                        │  hard-path queries only (~20%)
                        ▼
┌───────────────────────────────────────────────────────┐
│  Anthropic API — Claude Haiku 4.5                     │
│   • Pedagogical-reasoning queries                     │
│   • Bypass-able if eval shows quality gap → Sonnet    │
└───────────────────────────────────────────────────────┘
```

**Specific commitments:**

1. **Deployment:** Fly.io carries Phases 1.5–3. AWS Lambda migration is **deferred and conditional** — trigger is sustained >1000 daily queries, not a calendar date.
2. **Generation layer:** two-tier routing. Cheap path (~80% of queries) = Snowflake Cortex `mistral-large2`. Hard path (~20%, pedagogical-reasoning queries — *"why does this work?"*, *"prove that..."*) = Claude Haiku 4.5 via Anthropic API. Routing decided by a confidence-of-retrieval heuristic in the FastAPI layer. Upgrade to Sonnet for the hard path is a one-line config change if eval scores show Haiku underperforming.
3. **Frontend:** WordPress plugin `gktuition-ai-tutor.php` registers a `[gktuition_ai_tutor]` shortcode rendering a React widget. CORS scoped to the gktuition.ie origin only.
4. **Auth (v1):** WordPress role check — invite-codes are subscriber-role assignments via wp-admin. Production-grade auth deferred to Phase 3.
5. **Response shape (canonical JSON contract):**
   ```json
   {
     "query": "...",
     "answer": "...",
     "citations": [{"slug","title","timestamp_seconds","score"}],
     "retrieved": [{"slug","snippet","score"}],
     "exam_appearances": [{"year","paper","question","level","marks","note"}],
     "related_learning_work": [{"topic","tutorial_slug","note"}],
     "model_used": "cortex.mistral-large2",      // OR "anthropic.claude-haiku-4-5"
     "from_cache": false,
     "elapsed_ms": 0
   }
   ```
   The two domain-specific arrays (`exam_appearances`, `related_learning_work`) are sourced from per-tutorial YAML frontmatter (per `tutorials/SCHEMA.md`); these populate incrementally as the corpus is hand-curated. v1 will return empty arrays for tutorials not yet curated — this is acceptable degraded behaviour.

## Consequences

**Easier:** ship-by-DAY_36 timeline (widget on staging) is achievable on a free Fly.io machine. Two-tier routing keeps the 80% cheap-path queries cost-free in Snowflake and reserves Anthropic API spend for the ~20% genuinely-hard queries — total LLM spend bounded well below the €5/day kill switch even at high traffic. WordPress role-check auth is free and reversible. The JSON contract's domain-specific arrays (`exam_appearances`, `related_learning_work`) lock in the differentiation vs. a generic ChatGPT wrap — these are the fields no competitor can populate without Paul's corpus.

**Harder:** every layer must work for the demo to work. Fly.io deploys need their own observability story (logs piped to Snowflake `RAW.QUERY_LOG` per the cost-firewall design). The Anthropic API adds one external dependency for the hard path (mitigated by the kill switch + a "fall back to Cortex on API failure" retry). The WordPress widget's React build pipeline is one more place that can break.

**Future doors held open:** AWS Lambda migration is a single PR away (Fly.io deployment is already a Docker container). Upgrade from Haiku 4.5 to Sonnet for the hard path is a one-line config change. Streaming responses (Phase 2 UX upgrade) are compatible with the JSON contract via SSE.

**Largest single bet:** Snowflake remains the load-bearing dependency (per ADR-001). Generation, retrieval, and observability all live in one vendor. Re-evaluated only if Snowflake pricing or capability changes materially.
