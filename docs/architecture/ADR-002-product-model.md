# ADR-002: Access Model and Cost Controls

- **Status:** Accepted
- **Date:** 2026-05-13
- **Supersedes:** none
- **Related:** ADR-001 (Vector Store — Snowflake Cortex Search)

## Context

The AI tutor is intended to deepen engagement with the existing GKTuition product and seed adoption ahead of future commercial surfaces (paid student access, and a possible schoolbook companion product). Maximising the funnel into those surfaces favours unrestricted access during the prototype phase.

Unrestricted LLM access, however, exposes the project to runaway cost from automated abuse. A single misconfigured bot, scraper, or other LLM crawling the public widget could exhaust the daily Anthropic and Snowflake Cortex budget overnight. The decision below resolves the tension between open funnel and bounded cost.

## Decision

Adopt **free-for-all access** during the prototype phase. No login is required to query the tutor. Cost protection is engineered at the infrastructure layer through six concentric defences:

1. **Cloudflare front** — Turnstile (invisible CAPTCHA), geo-filtering to IE / UK / EU, per-IP rate limits.
2. **Application rate limits** — per-session, per-IP, and per-browser-fingerprint quotas enforced in FastAPI middleware.
3. **Semantic cache** — vector-similarity lookup in front of every LLM call; repeat or near-repeat queries cost zero.
4. **Two-tier LLM routing** — simple retrieval-with-explanation queries route to a cheap model (Cortex COMPLETE / Haiku-class). Only pedagogical reasoning queries route to Sonnet-class.
5. **Daily spend cap (kill switch)** — a server-side spend tracker; when €5/day is reached, all subsequent queries return "the tutor is resting, please come back tomorrow." This is the non-negotiable financial circuit breaker.
6. **Monitoring and alerting** — webhook fires when daily spend crosses €2 by midday, when any IP exceeds 10 queries/hour, or when the kill switch trips.

Authenticated user tiers are deferred until observed usage pressure on the daily spend cap indicates real demand worth gating behind a sign-up.

## Consequences

**Easier:** faster product-market-fit signal; cleaner future sign-up funnel (every authenticated user is a *converted* free user, not a forced one); recruiter showcase reads as cost-aware production thinking rather than generic SaaS templating.

**Harder:** all six layers must be built and tested before any public launch — no skipping ahead.

**Guaranteed:** worst-case daily blast radius is bounded at €5 regardless of any single defence failing.

**Re-evaluation trigger:** if the daily spend cap begins hurting real students (e.g. caps tripping before 6 p.m. local time on consecutive days), introduce authenticated tiers at that point — and not before.
