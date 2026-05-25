"""One-shot diagnostic for the reranker score=0 bug.

Calls SNOWFLAKE.CORTEX.SEARCH_PREVIEW against TUTOR_SEARCH and prints the
raw JSON response so we can see where reranker / cosine / text-match
scores actually live in the response shape.

Read-only. Delete after use (it's a scratch file, not a permanent tool).
"""
from __future__ import annotations

import json
import os

import snowflake.connector

conn = snowflake.connector.connect(
    user="GKTUITION_APP",
    account=os.environ["SF_ACCOUNT"],
    private_key_file=os.path.expanduser("~/.snowflake/gktuition_api_rsa.p8"),
    authenticator="SNOWFLAKE_JWT",
    role="GKTUITION_APP_RW",
    warehouse="WH_TUTOR",
    database="GKTUITION_TUTOR",
    schema="CORTEX",
)
cs = conn.cursor()
cs.execute(
    """
    SELECT SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
        'GKTUITION_TUTOR.CORTEX.TUTOR_SEARCH',
        %s
    )
    """,
    (
        json.dumps(
            {
                "query": "how do I factorise difference of squares",
                "columns": ["slug", "title"],
                "limit": 3,
            }
        ),
    ),
)
raw = cs.fetchone()[0]

print("=" * 70)
print("RAW response type:", type(raw).__name__)
print("=" * 70)
print()

parsed = json.loads(raw) if isinstance(raw, str) else raw

print("Top-level keys:")
print(list(parsed.keys()))
print()

print("=" * 70)
print("results[] length:", len(parsed.get("results") or []))
print("=" * 70)

results = parsed.get("results") or []
if results:
    print()
    print("results[0] keys:")
    print(list(results[0].keys()))
    print()
    print("results[0] full:")
    print(json.dumps(results[0], indent=2)[:2000])

# Also dump any sibling fields outside `results` — that's where Cortex
# Search 2024+ sometimes lands reranker / cosine / text-match scores.
print()
print("=" * 70)
print("Non-`results` top-level fields:")
print("=" * 70)
for k, v in parsed.items():
    if k == "results":
        continue
    print(f"\n{k!r}:")
    print(json.dumps(v, indent=2)[:1000] if not isinstance(v, str) else v[:1000])
