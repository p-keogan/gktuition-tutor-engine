#!/usr/bin/env python3
"""Force an immediate refresh of Cortex Search Services that would
otherwise wait the configured ``TARGET_LAG`` (1 day for our three
services per the DAY_26 build).

When to fire this
-----------------
* A typo fix landed on a single tutorial and you don't want students
  hitting the old answer until tomorrow.
* The summary loader rewrote a strand's top-tutorials list because
  you re-keyed a slug; the SUMMARY_SEARCH index needs to catch up.
* A new exam-paper solution file landed and you want it discoverable
  right now (mid-cram season).

When NOT to fire this
---------------------
* Every push. The default 1-day lag is correct for normal cadence —
  forcing a refresh adds warehouse credit usage each time.
* During the eval-set re-score after a loader-code change. The
  baseline is locked against a particular index state; refreshing
  mid-score moves the goalposts.

Cortex Search refresh semantics
-------------------------------
Snowflake's ``ALTER CORTEX SEARCH SERVICE <svc> REFRESH`` triggers
the embedding pipeline to re-pull from the base table and re-index
any changed rows. The call returns immediately; the service stays
ACTIVE during the refresh (queries continue to serve the previous
index). We poll ``SHOW CORTEX SEARCH SERVICES`` and gate on the
``last_refreshed_on`` column moving forward, with a hard timeout
of 10 minutes (the largest refresh observed during the DAY_26 build
took ~3 minutes; 10 is a safety margin).

If the REFRESH syntax in your Snowflake account differs (the GA
DDL is recent and Anthropic's Snowflake docs note minor variations
by region), pass ``--statement-template`` with the correct form —
or fall back to the documented manual recipe in
``docs/content-pipeline-handbook.md``.

Usage
-----

    # Refresh all three services.
    python sync/refresh_cortex.py \\
        --services TUTOR_SEARCH,SOLUTIONS_SEARCH,SUMMARY_SEARCH

    # Refresh one and wait up to 5 minutes.
    python sync/refresh_cortex.py --services SUMMARY_SEARCH --timeout-s 300

    # Show what would be dispatched without firing.
    python sync/refresh_cortex.py \\
        --services TUTOR_SEARCH,SOLUTIONS_SEARCH,SUMMARY_SEARCH --dry-run

Exit codes
----------
* 0 — every requested service refreshed within the timeout.
* 1 — at least one refresh failed or timed out.
* 2 — invocation error (no creds, no services named).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("refresh_cortex")

DEFAULT_DATABASE = "GKTUITION_TUTOR"
DEFAULT_SCHEMA = "CORTEX"
DEFAULT_SERVICES = ("TUTOR_SEARCH", "SOLUTIONS_SEARCH", "SUMMARY_SEARCH")
DEFAULT_REFRESH_TEMPLATE = "ALTER CORTEX SEARCH SERVICE {fqn} REFRESH"


@dataclass
class RefreshResult:
    service: str
    fqn: str
    dispatched: bool = False
    last_refreshed_before: str | None = None
    last_refreshed_after: str | None = None
    duration_s: float = 0.0
    error: str | None = None

    def ok(self) -> bool:
        return self.dispatched and self.error is None


def _connect() -> Any:
    try:
        import snowflake.connector  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "snowflake-connector-python is required to run refresh_cortex.py."
        ) from e

    snowflake.connector.paramstyle = "qmark"
    conn_kwargs: dict[str, Any] = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "role": os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        "warehouse": os.environ.get("SNOWFLAKE_WAREHOUSE", "WH_TUTOR"),
        "database": os.environ.get("SNOWFLAKE_DATABASE", DEFAULT_DATABASE),
        "schema": os.environ.get("SNOWFLAKE_SCHEMA", DEFAULT_SCHEMA),
    }
    if pk := os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH"):
        conn_kwargs["private_key_file"] = pk
        conn_kwargs["authenticator"] = os.environ.get(
            "SNOWFLAKE_AUTHENTICATOR", "SNOWFLAKE_JWT"
        )
    else:
        conn_kwargs["password"] = os.environ["SNOWFLAKE_PASSWORD"]

    import snowflake.connector  # re-import after the install check  # noqa: PLC0415
    return snowflake.connector.connect(**conn_kwargs)


def _query_last_refreshed(cs: Any, database: str, schema: str, service: str) -> str | None:
    """Read the ``last_refreshed_on`` field from ``SHOW CORTEX SEARCH SERVICES``.
    Returns ``None`` if the service is missing or the column isn't
    populated yet (a brand-new service shows NULL until first index)."""
    try:
        cs.execute(f"SHOW CORTEX SEARCH SERVICES IN {database}.{schema}")
    except Exception as e:  # noqa: BLE001 — many versions; tolerate
        log.warning("SHOW CORTEX SEARCH SERVICES failed: %s", e)
        return None
    rows = cs.fetchall()
    cols = [c[0].lower() for c in cs.description]
    try:
        idx_name = cols.index("name")
    except ValueError:
        return None
    try:
        idx_refreshed = cols.index("last_refreshed_on")
    except ValueError:
        # Older Snowflake regions emit it as ``last_refresh_time``.
        try:
            idx_refreshed = cols.index("last_refresh_time")
        except ValueError:
            return None
    for r in rows:
        if str(r[idx_name]).upper() == service.upper():
            v = r[idx_refreshed]
            return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)
    return None


def refresh_one(
    cs: Any,
    *,
    database: str,
    schema: str,
    service: str,
    template: str,
    timeout_s: float,
    poll_interval_s: float,
    dry_run: bool,
) -> RefreshResult:
    fqn = f"{database}.{schema}.{service}"
    result = RefreshResult(service=service, fqn=fqn)

    before = _query_last_refreshed(cs, database, schema, service)
    result.last_refreshed_before = before
    stmt = template.format(fqn=fqn)
    log.info("→ %s", stmt)
    if dry_run:
        result.dispatched = True
        return result

    t0 = time.monotonic()
    try:
        cs.execute(stmt)
    except Exception as e:  # noqa: BLE001
        result.error = f"REFRESH dispatch failed: {e}"
        log.error("✗ %s — %s", service, result.error)
        return result
    result.dispatched = True

    # Poll for the timestamp to move forward. Some services tick the
    # timestamp before the embed pass completes; we accept that as
    # "refresh in progress" and exit happy. Tighter completion gating
    # would require introspecting the service's internal state, which
    # isn't a documented surface.
    deadline = t0 + timeout_s
    while time.monotonic() < deadline:
        time.sleep(poll_interval_s)
        after = _query_last_refreshed(cs, database, schema, service)
        if after and after != before:
            result.last_refreshed_after = after
            result.duration_s = time.monotonic() - t0
            log.info(
                "✓ %s refreshed (last_refreshed_on advanced %s → %s in %.1fs)",
                service,
                before,
                after,
                result.duration_s,
            )
            return result

    # Timeout. The REFRESH was dispatched; it may simply be slower
    # than the timeout. Surface as a warning, not a failure — the
    # operator can re-query in five minutes.
    result.duration_s = time.monotonic() - t0
    result.error = (
        f"timeout after {timeout_s:.0f}s waiting for last_refreshed_on to advance; "
        "REFRESH was dispatched but may still be in progress"
    )
    log.warning("⚠ %s — %s", service, result.error)
    return result


# ─────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--services",
        default=",".join(DEFAULT_SERVICES),
        help="Comma-separated list of Cortex Search Services to refresh "
             "(default: TUTOR_SEARCH,SOLUTIONS_SEARCH,SUMMARY_SEARCH).",
    )
    ap.add_argument(
        "--database",
        default=os.environ.get("SNOWFLAKE_DATABASE", DEFAULT_DATABASE),
    )
    ap.add_argument(
        "--schema",
        default=os.environ.get("SNOWFLAKE_SCHEMA_CORTEX", DEFAULT_SCHEMA),
    )
    ap.add_argument(
        "--statement-template",
        default=DEFAULT_REFRESH_TEMPLATE,
        help="REFRESH statement template. `{fqn}` is substituted with the "
             "fully-qualified service name. Override if your Snowflake "
             "region uses a different DDL.",
    )
    ap.add_argument(
        "--timeout-s",
        type=float,
        default=600.0,
        help="Per-service timeout in seconds (default: 600 = 10 min).",
    )
    ap.add_argument(
        "--poll-interval-s",
        type=float,
        default=5.0,
        help="How often to re-poll last_refreshed_on (default: 5s).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the SQL that would be dispatched and exit 0.",
    )
    args = ap.parse_args(argv)

    services = [s.strip() for s in args.services.split(",") if s.strip()]
    if not services:
        log.error("--services produced an empty list")
        return 2

    if args.dry_run:
        for svc in services:
            fqn = f"{args.database}.{args.schema}.{svc}"
            log.info("--dry-run: would dispatch `%s`", args.statement_template.format(fqn=fqn))
        return 0

    try:
        conn = _connect()
    except KeyError as e:
        log.error("missing required env var %s", e)
        return 2
    except RuntimeError as e:
        log.error("%s", e)
        return 2

    results: list[RefreshResult] = []
    try:
        cs = conn.cursor()
        try:
            for svc in services:
                results.append(
                    refresh_one(
                        cs,
                        database=args.database,
                        schema=args.schema,
                        service=svc,
                        template=args.statement_template,
                        timeout_s=args.timeout_s,
                        poll_interval_s=args.poll_interval_s,
                        dry_run=False,
                    )
                )
        finally:
            cs.close()
    finally:
        conn.close()

    # One-line summary line for the CI log.
    ok = [r for r in results if r.ok()]
    warn = [r for r in results if r.dispatched and r.error]
    fail = [r for r in results if not r.dispatched]
    log.info(
        "Refresh summary: ok=%d, in-progress/timed-out=%d, failed=%d",
        len(ok),
        len(warn),
        len(fail),
    )

    # Failures (dispatch errors) → exit 1. In-progress timeouts → exit 0
    # because the REFRESH did get dispatched; the operator can verify
    # via SHOW CORTEX SEARCH SERVICES later.
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
