# GKTuition tutor — Ops runbook

This is the short-form on-call doc for the FastAPI orchestrator + cost
firewall deployed to Fly.io as `gktuition-tutor-api`. It covers the eight
recurring operational tasks. If you're reading this during an incident,
the section you want is near the top.

> **Scope.** This runbook is for Phase 1.5–3 (Fly.io). The AWS Lambda
> migration is deferred until the `>1,000 daily queries` trigger in
> ADR-003 fires; when it does, this file gets a "Lambda equivalent"
> column added to each procedure, not a rewrite.

---

## 1. Is the live app healthy?

```bash
curl -s https://gktuition-tutor-api.fly.dev/healthz | jq
```

Expected:

```json
{
  "status": "ok",
  "snowflake": "connected",
  "anthropic": "reachable",
  "cache_table": "present",
  "version": "<git sha>",
  "elapsed_ms": 80,
  "cap_state": { "global_cap_fired": false, ... }
}
```

- `status: "ok"` — every sub-check passed.
- `status: "degraded"` — one or more sub-checks failed. The body lists
  which. Fly still considers the app healthy (HTTP 200) so it doesn't
  flap the machine on a transient Snowflake hiccup.
- If `curl` itself fails (connection refused, TLS error), the app is
  down or scaled to zero. Run:

  ```bash
  fly status --app gktuition-tutor-api
  fly logs --app gktuition-tutor-api --instance <id>
  ```

Cold-start latency on `min_machines_running=0` is ~3-6s for the first
request after idle. If you're paging because a student complained about
slow first response, this is expected behaviour; the fix is to set
`min_machines_running=1` in `fly.toml` (costs ~€2/mo). Don't reach for
that fix unless you have multiple complaints — the cost profile in
ADR-003 explicitly accepts the cold start.

## 2. Read the spend dashboard

Spend lives in two places. Check both:

1. **Snowflake** — `GKTUITION_TUTOR.RAW.DAILY_SPEND` (Agent 10's L5 kill
   switch table):

   ```sql
   SELECT tier, spend_date, total_eur
   FROM   GKTUITION_TUTOR.RAW.DAILY_SPEND
   WHERE  spend_date >= DATEADD(day, -7, CURRENT_DATE())
   ORDER  BY spend_date DESC, tier;
   ```

2. **Live cap state** — surfaced on `/healthz` under `cap_state` when
   `KILL_SWITCH_ENABLED=true` (the default in `fly.toml`). The Fly machine's
   in-memory counter is **not** the source of truth — it resets on a
   machine restart. Snowflake is the load-bearing belt; the in-memory
   counter is the suspenders.

The Anthropic console (https://console.anthropic.com/settings/usage)
shows API spend in dollars; the script
`scripts/etl_anthropic_usage_to_snowflake.py` (future, not yet built)
will reconcile. Today, eyeball it monthly.

## 3. Flip the kill switch manually

> "Manually" here means "the daily caps in Snowflake haven't fired, but I
> want to throttle traffic anyway — eg I'm seeing a runaway prompt or
> deploying a fix."

Tighten the global cap to €0:

```bash
fly secrets set KILL_SWITCH_GLOBAL_CAP_EUR=0 --app gktuition-tutor-api
```

All `/query` calls will return HTTP 503 with `detail.error == "global_cap"`
within seconds (Fly re-rolls the machine on `fly secrets set`). To
restore:

```bash
fly secrets set KILL_SWITCH_GLOBAL_CAP_EUR=5.0 --app gktuition-tutor-api
```

If you want to throttle a *single tier* — eg disable anonymous traffic
during a load spike but keep paying students working — set the
tier-specific cap to 0 instead:

```bash
fly secrets set KILL_SWITCH_ANON_CAP_EUR=0 --app gktuition-tutor-api
```

For a hard cutoff that the Fly app can't undo (eg the Anthropic console
shows runaway spend the kill switch missed), edit the Snowflake resource
monitor `RM_TUTOR_DAILY` directly in the Snowflake UI — that suspends
the warehouse regardless of what Fly does.

## 4. Roll back a deploy

The deploy workflow in `.github/workflows/ci.yml` does this automatically
on smoke-test failure. To roll back manually:

```bash
# Pick the release to roll back to (list shows version numbers).
fly releases --app gktuition-tutor-api

# Roll back. The number is the `Version` column, eg "v123".
fly releases rollback v123 --app gktuition-tutor-api
```

This is image-level rollback — secrets stay where they are. If the
problem is a bad secret, see §5.

## 5. Swap the Anthropic API key without downtime

```bash
# Update locally first.
sed -i '' "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=sk-ant-NEW|" ~/.gktuition_secrets

# Push to Fly. The script restarts machines atomically; the new key is
# active before the old one is revoked.
./scripts/setup_fly_secrets.sh

# Wait for the new release to settle, then revoke the old key in the
# Anthropic console. The window between rotation and revocation is the
# graceful overlap; usually a few minutes is plenty.
```

If you need a zero-downtime rotation (eg revoke-and-replace is forced by
a security incident), you'll need to set the new key *first*, wait for
the machine to pick it up (~30s with `auto_start_machines=true`), then
revoke. Don't do them in the reverse order.

## 6. Monitor the nightly eval scoring report

The workflow `.github/workflows/scheduled_eval.yml` runs at 02:00 UTC.
On success it commits `eval/scoring_history/YYYY-MM-DD.md`. On a
regression (precision@1 down ≥ 5pp vs. the prior 7-day median), it opens
a PR with the `eval-regression` label.

To audit a specific day:

```bash
ls -1 eval/scoring_history/ | tail -7   # last week
cat eval/scoring_history/2026-05-22.md
```

If the workflow itself failed (the run shows as red in the Actions tab)
the most common causes are:

1. WH_EVAL credentials rotated — re-encode the new key:
   ```bash
   base64 -i path/to/new.p8 -o /dev/stdout | gh secret set EVAL_SF_PRIVATE_KEY
   ```
2. The golden subset CSV changed shape (new column, slug rename) — the
   scorer will fail-loud with a parse error. Fix the CSV in the same PR
   as the schema change.
3. Snowflake account is suspended — check the account status before
   blaming the workflow.

## Smoke regression issue triage

The workflow `.github/workflows/smoke_canonical_queries.yml` runs daily
at 06:00 UTC. It POSTs a small set of canonical "explain X" /
single-word queries at live production and asserts each one returns a
real Paul-voiced answer (not the guardrail, voice anchor populated).
On failure it opens — or comments on the existing — `smoke/regression`
issue with the failing-query JSON in the body.

The exit code in the issue tells you which path to take first:

- **Exit 1 — API unreachable** (`[smoke-unreachable]`). The script
  couldn't reach `/query` at all. Check Fly status first:

  ```bash
  curl -sS https://gktuition-tutor-api.fly.dev/healthz | jq .status
  fly status --app gktuition-tutor-api
  ```

  If `/healthz` is green but the smoke probe timed out, the most
  likely cause is `WP_JWT_SECRET` rotated on Fly without being
  re-mirrored to GitHub Actions secrets — the JWT will mint OK but
  the API rejects it with 401, which the script reports as
  `http_status=401`.

- **Exit 2 — strict-assertion failure** (`[smoke-regression]`). The
  API answered, but at least one canonical query came back wrong.
  Common causes in order of frequency:

  1. A feature flag drifted. Check whether `QUERY_REWRITE_ENABLED` and
     `SLUG_ANCHOR_OVERRIDE_ENABLED` are still `true` on the Fly app:

     ```bash
     fly secrets list --app gktuition-tutor-api | grep -E "(QUERY_REWRITE|SLUG_ANCHOR)"
     ```

     Flip them back on with `fly secrets set ...=true` if either has
     fallen off.

  2. A response builder lost the voice-anchor mirror (the original
     DAY_31 failure mode). The firewall path is the one prod traffic
     takes; check
     `api/firewall/wire.py::run_with_firewall` is still threading
     `voice_anchor_strand = infer_strand_from_retrieval(...)` into
     the `QueryResponse(...)` constructor.

  3. The corpus subset bundled into the engine image at
     `corpus/` drifted from the sibling repo. Re-run
     `scripts/sync_corpus.sh` and redeploy.

  4. The guardrail copy in
     `api/orchestrator/synthesizer.py::GUARDRAIL_ANSWER` changed and
     the smoke script's `GUARDRAIL_PREFIX_RE` didn't track. The smoke
     test starts firing every morning until both are updated — that
     coupling is intentional.

Manual verification of a failing query (copy the `q` field out of the
issue body into this curl):

```bash
curl -sS -X POST https://gktuition-tutor-api.fly.dev/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $(WP_JWT_SECRET=... python3 -c '...')" \
  -d '{"q":"<the failing query>","debug":true}' | jq '.voice_anchor_strand, .model_used, .answer[:200]'
```

(Easier: run the script locally — `python scripts/smoke_canonical_queries.py
--base-url https://gktuition-tutor-api.fly.dev` — with the same
`WP_JWT_SECRET` exported. The structured failure JSON it prints is
the same one the workflow pasted into the issue.)

A known-floor-miss query (currently `circumcentre` on its own) is
reported softly by default and won't open an issue. To probe a fix
candidate before flipping `known_floor_miss=False`, run the script
with `--include-known-floor-misses` locally — the workflow itself
never sets that flag, to avoid the issue inbox flapping while a
follow-up agent is still landing the fix.

## 7. Eval regression PR — triage

When the nightly workflow opens an `[eval-regression]` PR:

1. Open the PR — the body lists today's precision@1 + the prior 7-day
   median.
2. Open the report at `eval/scoring_history/YYYY-MM-DD.md`. Look at the
   per-row CSV at `eval/scoring_rows_*.csv` (committed alongside) to see
   exactly which queries regressed.
3. Likely causes in order of frequency:
   - A new tutorial slug was added but not threaded into the golden set.
   - Cortex Search reindexed (DAG ran) and ordering shifted.
   - A retriever change in `api/orchestrator/retriever.py` shifted ranks.
   - The model behind `cortex.mistral-large2` was updated by Snowflake.
4. If the cause is the first one (golden set out of date), close the
   regression PR and open a fix-the-golden-set PR. Don't merge the
   regression PR — that would silently accept the lower score as the new
   baseline.
5. If the cause is a real retriever regression, revert the offending
   change and re-run the workflow with `workflow_dispatch`.

## 8. Common Fly commands cheat sheet

```bash
# What's deployed?
fly status --app gktuition-tutor-api

# Tail logs
fly logs --app gktuition-tutor-api

# SSH into a running machine (eg to inspect the spend counter mid-day)
fly ssh console --app gktuition-tutor-api

# Force a redeploy of the current image (useful after secrets change)
fly machine restart --app gktuition-tutor-api

# Scale up temporarily for a load test (don't forget to scale back)
fly scale count 2 --app gktuition-tutor-api
fly scale count 1 --app gktuition-tutor-api

# Show all secrets (names only — values are write-only)
fly secrets list --app gktuition-tutor-api
```

---

## Appendix — what's NOT in this runbook

Some procedures live elsewhere on purpose:

- **Snowflake DDL changes** — see `snowflake/README.md` and the
  per-warehouse SQL files. Do not change schemas from this app's
  deploy path; schemas have their own change process.
- **WordPress widget rollout** — see `widget/README.md` (Agent 11).
- **The AWS Lambda migration** — deferred. When the >1,000-daily-queries
  trigger from ADR-003 fires, the migration plan goes in
  `gktuition/ADR-005-lambda-migration.md`. Until then, do not deploy
  the app to Lambda; the orchestrator's connection pool is Fly-shaped.
