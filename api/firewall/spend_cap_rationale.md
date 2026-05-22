# L5 spend-cap rationale

Three nested daily caps fire independently. Numbers in EUR. Reset at midnight UTC.

| Cap | Threshold | Who is blocked when it fires | Why this number |
|---|---|---|---|
| `anonymous_tier_cap` | €0.50 / day | anonymous tier only | €0.50 buys ~25 Claude Haiku 4.5 calls or ~200 Cortex `mistral-large2` calls. A bot that gets past Turnstile + per-IP + per-/24 + honeypot + dwell-time + UA-list cannot burn more than that on the anonymous tier alone — and €0.50 is well inside the user's recovery budget. |
| `free_tier_cap` | €2.00 / day | anonymous + authenticated_free | The free funnel is supposed to seed conversion, not be the main spend driver. €2.00 across both free tiers leaves ≥ €3.00 of headroom for paying customers within the €5.00 global ceiling. |
| `global_cap` | €5.00 / day | everyone | Matches ADR-002's non-negotiable financial circuit-breaker. The Snowflake-side `RM_TUTOR_DAILY` resource monitor will independently SUSPEND `WH_TUTOR` at this point — L5 is the client-side belt that fires *before* the Snowflake belt so the user gets a graceful "at capacity" response instead of an opaque warehouse failure. |

## Why three caps and not one

The original ADR-002 design specified a single €5/day cap. The 2026-05-21 revision (this document) adds the two lower-tier caps because the access-model assumptions have tightened in the intervening days:

- Anonymous tier is now capped at **2 questions per IP per day** (L2). A determined bot that rotates IPs across a /24 can still consume free-tier spend even after L1 + L2 reject most of its requests. Allowing the bot to burn the *entire* €5 ceiling on the anonymous tier would leave the user paying for traffic they got no funnel benefit from. Carving out €0.50 for anonymous specifically caps the worst-case bot blast radius at 10 % of the daily ceiling.
- The free-tier cap exists to keep the paying funnel uninterrupted by free-tier traffic spikes. If a popular tutorial gets shared on social media and 500 students hit the widget in an hour, free-tier spend will balloon; the cap protects paying customers from being collateral damage.
- The global cap is the same number ADR-002 promised — €5/day worst-case daily blast radius. It hasn't changed.

## How the caps interact

Each request increments the row for its own tier *before* the LLM call. The cap is then checked atomically against the running total. If two requests race the cap, one wins by a few cents and the other lands behind the wall — acceptable race semantics for a cost-control mechanism (better one cent over than ten cents over).

The precheck logic in `precheck(tier)` short-circuits to the *highest-severity* cap that matches:

1. `global_cap_fired` → all tiers blocked.
2. `free_cap_fired` + tier in (anonymous, authenticated_free) → free tiers blocked.
3. `anonymous_cap_fired` + tier == anonymous → anonymous blocked.

So if both anonymous and free caps have fired, an anonymous request sees the `free_tier_cap` error (which is more honest about what's wrong: the whole free funnel is at capacity, not just the anonymous slice of it).

## Operational observability

`/healthz` returns a `cap_state` block whenever `KILL_SWITCH_ENABLED=true`:

```json
{
  "status": "ok",
  "cap_state": {
    "date": "2026-05-22",
    "anonymous_spend_eur": 0.42,
    "free_combined_spend_eur": 1.07,
    "global_spend_eur": 2.31,
    "anonymous_cap_eur": 0.50,
    "free_cap_eur": 2.00,
    "global_cap_eur": 5.00,
    "anonymous_cap_fired": false,
    "free_cap_fired": false,
    "global_cap_fired": false
  }
}
```

A monitoring dashboard can poll `/healthz` once a minute and chart all three running totals against their caps. The first cap to fire is usually `anonymous_tier_cap`, which is also the cheapest to recover from (it just means tomorrow's free students start fresh).

## When to revise these numbers

Re-evaluation triggers, in priority order:

1. `anonymous_tier_cap` fires before 6 p.m. local time on three consecutive days → either Turnstile is failing or the prefix-bot list needs an update. Investigate, don't raise the cap.
2. `free_tier_cap` fires before midnight on more than ~10 % of days → the authenticated-free tier is generating real demand; consider promoting paying conversions or raising the cap to €3.00 while monitoring the global ceiling.
3. `global_cap` fires → revisit the whole architecture. Either we have real product-market fit (raise the ceiling, plan capacity) or we have an attack we haven't seen (tighten the lower tiers first).

Refreshing the pricing table in `anthropic_pricing.yaml` is part of the same monthly cadence — Anthropic prices change. The cap thresholds here are in EUR and stable regardless of FX; the per-call costs that contribute to the running total are recomputed from current pricing every request.
