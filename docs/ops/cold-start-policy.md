# Cold-start policy — no 24/7 warm worker (decided 2026-06-12)

**Decision (Paul, 2026-06-12):** launch on cold-start + SSE streaming. The
always-warm worker (AGENT_18) stays **disabled**.

## Why

- The DAY_34 ~€18/day incident *was* the warm pattern: `/healthz` keeping the
  warehouse awake around the clock with zero users. Re-enabling 24/7 warmth is
  ~€500+/month of mostly idle compute.
- Streaming (AGENT_17) already turned cold-start from a 205-second wall of
  silence into "Looking up answer…" within 50 ms and first tokens in ~25 s
  cold / ~3–4 s warm. Survivable for v1.
- With real traffic, auto-suspend makes warmth usage-priced: the warehouse is
  warm while students are actually asking and asleep otherwise.

## Playbook

1. **Launch:** cold + streaming. No warm worker, no /healthz warehouse ping.
2. **Demo moments** (showing a teacher/school, recording a video): fire one
   throwaway query a minute beforehand; the warehouse stays warm for the
   session at usage cost.
3. **Escalation trigger:** if the query log shows real students bouncing on
   cold waits (abandon before first token), buy a **scheduled warm window**
   (resume/suspend cron, e.g. 16:00–22:00 Irish time) — hours × ~€2–3/hr, not
   24/7. Re-evaluate with a week of latency data.
4. The L5 spend kill-switch and the spend dashboard remain the backstop for
   anything that warms the warehouse unexpectedly.
