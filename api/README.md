# GKTuition AI Tutor — FastAPI orchestrator

Single HTTP entrypoint for the LCHL Maths tutor. The orchestrator implements
the canonical `/query` JSON contract from ADR-003 (revised) and ADR-004, sitting
in front of:

* three Snowflake Cortex Search Services (Agents 01 + 02 own them),
* Cortex Analyst (Agent 04 owns the semantic model),
* Cortex `mistral-large2` (cheap-path synthesiser, ~80% of queries),
* Claude Haiku 4.5 via the Anthropic API (hard-path synthesiser, ~20%).

The cost firewall layers (L1 Turnstile, L2 rate limit, L3 semantic cache,
L4 router, L5 €5/day kill switch, L6 monitoring) are Agent 10's domain — this
package is the bare happy path that Agent 10 wraps.

## Layout

```
api/
├── main.py                 # FastAPI app + lifespan + CORS
├── pyproject.toml          # deps + ruff + mypy + pytest config
├── README.md               # this file
├── AGENT_09_DELIVERY.md    # delivery note + verification record
├── auth/
│   └── jwt.py              # WordPress JWT decoder (HS256 + WP_JWT_SECRET)
├── orchestrator/
│   ├── contract.py         # Pydantic models (QueryRequest / QueryResponse / ...)
│   ├── classifier.py       # deterministic intent classifier (routing_contract.md)
│   ├── retriever.py        # fan-out to Cortex Search + Analyst
│   └── synthesizer.py      # two-tier LLM router + guardrail
├── routes/
│   ├── query.py            # POST /query (Agent 09)
│   └── image_query.py      # POST /image_query (Agent 06 — untouched)
├── services/               # Agent 06's seams; query_log.py extended for Agent 09
├── sql/
│   └── query_log_table.sql # GKTUITION_TUTOR.RAW.QUERY_LOG schema
└── tests/                  # pytest suite — 48 tests, all green
```

## Run locally

```bash
cd gktuition-tutor-engine/api
pip install -e ".[dev]"          # or: pip install -r ../<your-requirements>

# Required at startup (the lifespan handler reads them):
export WP_JWT_SECRET=dev-only
export GKTUITION_ENV=dev          # opens CORS for localhost too

# Optional — set these to hit live Snowflake / Anthropic in dev:
# export SNOWFLAKE_ACCOUNT=...
# export SNOWFLAKE_USER=...
# export SNOWFLAKE_PASSWORD=...
# export ANTHROPIC_API_KEY=...

uvicorn api.main:app --reload --port 8000
```

Then:

* OpenAPI / Swagger UI: <http://localhost:8000/docs>
* Health check: <http://localhost:8000/healthz>

Smoke test from a fresh terminal (relies on live Snowflake + Anthropic to
return a non-guardrail answer):

```bash
curl -s -X POST http://localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"q":"how do I factorise difference of squares"}' | jq
```

Expected on a populated warehouse: `query_class: "concept"` and a citation
pointing at `algebra-1-revision-of-jc-factorising`.

## Environment variables

| Variable | Required? | Purpose |
|---|---|---|
| `WP_JWT_SECRET` | yes (boot fails without it) | HS256 secret shared with the WordPress plugin. Dev value: `dev-only`. |
| `GKTUITION_ENV` | no (defaults to `prod`) | `dev` adds `localhost` to the CORS allow-list. |
| `SNOWFLAKE_ACCOUNT` | for live retrieval | Snowflake account locator. |
| `SNOWFLAKE_USER` | for live retrieval | Snowflake username. |
| `SNOWFLAKE_PASSWORD` *or* `SNOWFLAKE_PRIVATE_KEY_PATH` | for live retrieval | Auth — password or RSA private key. |
| `SNOWFLAKE_ROLE` | no (default `ACCOUNTADMIN`) | Override role. |
| `SNOWFLAKE_WAREHOUSE` | no (default `WH_TUTOR`) | Warehouse name. |
| `SNOWFLAKE_DATABASE` | no (default `GKTUITION_TUTOR`) | Database name. |
| `SNOWFLAKE_PAT` | for live Cortex Analyst | Programmatic Access Token for the Analyst REST endpoint. Falls back to `SNOWFLAKE_PASSWORD`. |
| `ANTHROPIC_API_KEY` | for live hard path | Claude Haiku 4.5 + Sonnet vision (image_query). |
| `GKTUITION_DISABLE_QUERY_LOG` | no | When set, skips wiring the Snowflake query-log writer even if creds exist. |

If Snowflake / Anthropic env vars are absent, the orchestrator still boots
and serves traffic, but every retrieval call fails and the guardrail
("I'm not sure — try one of these related tutorials") fires. The test
suite is fully offline: all four collaborators (Snowflake cursor, Cortex
Analyst, Cortex Complete, Anthropic Messages) are injected via the
`set_*_caller` seams.

## JWT validation

The WordPress plugin (`gktuition-ai-tutor.php`, Agent 11's domain) mints
HS256 JWTs with claims:

```json
{"iss":"gktuition.ie","aud":"gktuition-ai-tutor","sub":"<wp_user_id>",
 "tier":"anonymous|authenticated_free|paying","iat":...,"exp":...}
```

The decoder validates signature, expiry, issuer (`gktuition.ie`), and
audience (`gktuition-ai-tutor`). A missing `Authorization` header is
treated as `tier=anonymous` (the unauthenticated path); a malformed token
returns 401.

In dev you can mint your own tokens via:

```python
from api.auth.jwt import mint_dev_token
import os; os.environ["WP_JWT_SECRET"] = "dev-only"
print(mint_dev_token("u_42", "paying"))
```

## Tests

```bash
cd gktuition-tutor-engine
WP_JWT_SECRET=dev-only GKTUITION_ENV=dev python -m pytest api/tests/ -v
```

Headline runs (see `AGENT_09_DELIVERY.md` for the per-check record):

| Suite | Tests | Status |
|---|---|---|
| `test_classifier.py` | 9 | green; 30-case ground-truth accuracy = 100% |
| `test_retriever.py` | 7 | green; fan-out + dedupe + analyst path covered |
| `test_synthesizer.py` | 10 | green; two-tier routing + guardrail covered |
| `test_query_e2e.py` | 12 | green; every `query_class` exercised through `TestClient` |
| `test_eval_regression.py` | 1 | green; ≥ 40/50 phrasings classify as `concept` |
| `test_image_query.py` (Agent 06) | 9 + 1 skipped | green; unchanged |

## Lint + type check

```bash
cd gktuition-tutor-engine/api
python -m ruff check .                     # clean
cd ..
MYPYPATH=. python -m mypy --strict --explicit-package-bases \
    --config-file api/pyproject.toml \
    api/orchestrator api/auth api/routes/query.py api/main.py
# Success: no issues found in 9 source files
```

Agent 06's pre-existing modules under `api/services`, `api/models`, and
`api/routes/image_query.py` have a relaxed override in
`api/pyproject.toml` (the Agent 09 spec bounds Agent 09 to the
orchestrator + `routes/query.py` + `auth` + `main.py` + new tests).

## Snowflake DDL

```bash
# From a SnowSQL session (Agent 01 + 02 + 04 bootstraps already dispatched):
snowsql -f api/sql/query_log_table.sql
```

Idempotent — the SQL is `CREATE OR REPLACE TABLE`, safe to re-run any
number of times.

## Live Snowflake roundtrip (deferred-to-user)

The agent has no Snowflake credentials in its sandbox. Once your
warehouse is live, the spec's roundtrip is:

```bash
curl -X POST localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"q":"how do I factorise difference of squares"}'
```

Expected: `query_class: "concept"`, top citation slug
`algebra-1-revision-of-jc-factorising`.
