"""Always-warm worker for the GKTuition AI tutor.

Pings ``POST /query`` once per invocation with a stable, cache-friendly
warmup question so that the Snowflake ``WH_TUTOR`` warehouse never
auto-suspends during expected-active hours and the synthesiser path
stays JIT-hot.

Why not rely on the Fly ``/healthz`` probe?
------------------------------------------
``/healthz`` (see ``api/routes/health.py``) exercises ``SELECT 1`` against
the Snowflake connection pool — that's enough to keep the warehouse from
auto-suspending on the 60-second timer, but it does *not* exercise the
full classifier → retriever → synthesiser path. The DAY_30 live trace
caught a ~205s cold-start on the synthesiser side even with the
warehouse warm — module import, embedding-model warm-up, and the
two-tier router's first Anthropic round-trip all contribute. A real
``/query`` call walks the entire pipeline and keeps every layer warm.

Cost model
----------
Snowflake side: ``WH_TUTOR`` is XSMALL (1 credit/hour = ~€2.5/h), idle
suspends after 60s. Pinging every ~60s during a 7-hour warm window keeps
the warehouse running ≈ 7h × ~€2.5/h = ~€17/month *if* every ping were
the only activity. In practice organic ``/healthz`` already keeps it
warm; the marginal cost of layering ``/query`` on top is the difference
between "warehouse busy" and "warehouse idle-but-running", which on
XSMALL is negligible. Anthropic side: the L3 semantic cache absorbs
identical queries with a 7-day TTL, so the first ping of each day pays
the model cost (~€0.005 for a Mistral Large 2 hop) and subsequent
pings hit cache for €0. Total marginal: < €2/month.

Hours
-----
Warm window: 15:00–22:00 IE (Mon–Sun). Outside this window the script
exits 0 immediately so a stray cron fire is a no-op. Cold-start of the
first 15:00 query is acceptable; we trade one cold-start a day for
sub-5s response time the rest of the active window.

Invocation modes
----------------
This script supports two invocation patterns:

* **one-shot (default)** — Fire-and-forget single ping. Designed to be
  driven by a Fly Machines scheduled run (``flyctl m run --schedule
  '*/1 15-22 * * *' ...``). Exits 0 on success, non-zero on hard
  failure. The script self-gates to the warm window; outside it,
  exits 0 with no HTTP call.

* **loop** (``--loop``) — Long-running loop with a 40s sleep between
  pings. Use when running as a Fly process (declared in ``[processes]``
  of ``fly.toml``) rather than a scheduled machine. Cron's minimum
  resolution is 1 minute, so this is the path if you want closer to
  the 40s cadence spec'd in the AGENT_18 brief.

Configuration (all via env vars)
--------------------------------
* ``WP_JWT_SECRET`` — required. HS256 shared secret. Same value as the
  Fly secret of the same name.
* ``WARM_TARGET_URL`` — optional. Default
  ``https://gktuition-tutor-api.fly.dev``.
* ``WARM_QUESTION`` — optional. Default ``"warmup ping — what is the
  slope formula"`` (well-covered in the corpus; the L3 cache absorbs
  repeats).
* ``WARM_USER_ID`` — optional. Default ``"warmup-worker"`` — this
  becomes the ``sub`` claim and is what shows up in ``RAW.QUERY_LOG``
  for filtering / accounting.
* ``WARM_WINDOW_START_HOUR_IE`` / ``WARM_WINDOW_END_HOUR_IE`` —
  optional. Defaults ``15`` / ``22``. End hour is exclusive — i.e. a
  fire at 22:00:01 IE no-ops.

Read-only outside its own behaviour
-----------------------------------
This script never writes to disk, never edits secrets, never bypasses
the firewall. It uses only the public ``/query`` endpoint with a valid
JWT exactly as a logged-in student would.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Any

logger = logging.getLogger("always_warm")


# --- Configuration ---------------------------------------------------------

DEFAULT_TARGET_URL = "https://gktuition-tutor-api.fly.dev"
DEFAULT_QUESTION = "warmup ping — what is the slope formula"
DEFAULT_USER_ID = "warmup-worker"

# Ireland is UTC+1 in summer (IST), UTC+0 in winter (GMT). The Python
# stdlib does not ship a zoneinfo entry guarantee on every base image;
# rather than bring in tzdata as a dependency, we approximate IE time as
# UTC + Ireland-summer-offset. This is correct for the LC-tutoring season
# (April-September) which is when the warm worker matters most. Outside
# of summer, the warm window will shift by 1 hour relative to clock time
# — acceptable trade for zero extra deps.
_IE_UTC_OFFSET_HOURS = 1

DEFAULT_WINDOW_START_HOUR_IE = 15
DEFAULT_WINDOW_END_HOUR_IE = 22

DEFAULT_LOOP_SLEEP_SECONDS = 40
HTTP_TIMEOUT_SECONDS = 30.0


# --- JWT minting -----------------------------------------------------------


def _mint_jwt(*, user_id: str, secret: str, ttl_seconds: int = 3600) -> str:
    """Mint an HS256 JWT shaped to the WordPress contract.

    Mirrors ``api.auth.jwt.mint_dev_token`` exactly (issuer, audience,
    algorithm, claim layout) so the API accepts it without any code path
    diverging for warmup traffic. We use ``python-jose`` (already a
    runtime dependency of the API venv) so the script needs no extra
    install.
    """
    # Imported lazily so a syntax-check / --help works without jose installed.
    from jose import jwt as _jose_jwt  # type: ignore[import-not-found]

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": user_id,
        "tier": "paying",  # bypass anonymous / free rate limits
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return _jose_jwt.encode(claims, secret, algorithm="HS256")


# --- Warm-window gating ----------------------------------------------------


def _now_ie() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=_IE_UTC_OFFSET_HOURS)


def _in_warm_window(
    *,
    now_ie: datetime | None = None,
    start_hour: int = DEFAULT_WINDOW_START_HOUR_IE,
    end_hour: int = DEFAULT_WINDOW_END_HOUR_IE,
) -> bool:
    """True iff ``now_ie`` falls inside ``[start_hour, end_hour)`` IE.

    Window is inclusive on the start (>= start_hour) and exclusive on
    the end (< end_hour). A 22:00:00 fire is the last one of the day;
    22:00:01 onward no-ops.
    """
    now = now_ie if now_ie is not None else _now_ie()
    return start_hour <= now.hour < end_hour


# --- /query ping -----------------------------------------------------------


def _ping_query(
    *,
    target_url: str,
    question: str,
    jwt_token: str,
    timeout_s: float = HTTP_TIMEOUT_SECONDS,
) -> tuple[int, dict[str, Any] | str]:
    """POST a single warmup query to /query. Returns (status_code, body).

    On HTTP error we still return the response — the warmup worker is
    intentionally tolerant. A 4xx/5xx is logged but not raised; the
    next scheduled fire will retry on its own.
    """
    url = target_url.rstrip("/") + "/query"
    payload = json.dumps({"q": question}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_token}",
            "User-Agent": "gktuition-always-warm/1.0",
        },
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status_code = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info(
        "warm ping target=%s status=%s elapsed_ms=%d",
        url, status_code, elapsed_ms,
    )
    try:
        return status_code, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status_code, raw


# --- One-shot + loop drivers ----------------------------------------------


def _run_once(
    *,
    target_url: str,
    question: str,
    user_id: str,
    secret: str,
    start_hour: int,
    end_hour: int,
    force: bool = False,
) -> int:
    """Single warmup ping. Returns the exit code (0 = success or out-of-window)."""
    now = _now_ie()
    if not force and not _in_warm_window(
        now_ie=now, start_hour=start_hour, end_hour=end_hour,
    ):
        logger.info(
            "outside warm window (IE hour=%d, window=[%d,%d)); exiting 0",
            now.hour, start_hour, end_hour,
        )
        return 0

    token = _mint_jwt(user_id=user_id, secret=secret)
    status_code, body = _ping_query(
        target_url=target_url, question=question, jwt_token=token,
    )

    if status_code == 200:
        # Body is the QueryResponse contract; log a compact summary.
        if isinstance(body, dict):
            qc = body.get("query_class")
            elapsed = body.get("elapsed_ms")
            mused = body.get("model_used")
            logger.info(
                "warm ok query_class=%s model_used=%s elapsed_ms=%s",
                qc, mused, elapsed,
            )
        return 0

    logger.warning(
        "warm ping returned non-200 status=%d body=%r — will retry on next fire",
        status_code, body,
    )
    # Non-zero exit so Fly's machine-run log surfaces the failure, but the
    # next scheduled fire is independent so this isn't a "page me" event.
    return 1


def _run_loop(
    *,
    target_url: str,
    question: str,
    user_id: str,
    secret: str,
    start_hour: int,
    end_hour: int,
    sleep_seconds: int,
) -> int:
    """Long-running loop. Sleeps ``sleep_seconds`` between pings; self-gates
    to the warm window. Outside-window iterations sleep ``sleep_seconds``
    rather than busy-checking the clock.
    """
    logger.info(
        "loop mode: target=%s sleep=%ds window=[%d,%d) IE",
        target_url, sleep_seconds, start_hour, end_hour,
    )
    while True:
        try:
            _run_once(
                target_url=target_url, question=question, user_id=user_id,
                secret=secret, start_hour=start_hour, end_hour=end_hour,
                force=False,
            )
        except KeyboardInterrupt:
            logger.info("loop interrupted; exiting")
            return 0
        except Exception:  # noqa: BLE001 — loop must never die on transient errors
            logger.exception("warmup iteration raised; sleeping and continuing")
        time.sleep(sleep_seconds)


# --- CLI entrypoint --------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Always-warm worker — pings /query during active hours.",
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously (40s cadence); otherwise fire once and exit.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Ignore the warm-window gate (for ad-hoc smoke tests).",
    )
    parser.add_argument(
        "--sleep-seconds", type=int, default=DEFAULT_LOOP_SLEEP_SECONDS,
        help="Loop-mode sleep between pings.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )

    secret = os.environ.get("WP_JWT_SECRET")
    if not secret:
        logger.error(
            "WP_JWT_SECRET not set — refusing to run. "
            "In Fly, this is already set as a secret; in local dev, "
            "export WP_JWT_SECRET=dev-only first."
        )
        return 2

    target_url = os.environ.get("WARM_TARGET_URL", DEFAULT_TARGET_URL)
    question = os.environ.get("WARM_QUESTION", DEFAULT_QUESTION)
    user_id = os.environ.get("WARM_USER_ID", DEFAULT_USER_ID)
    start_hour = int(os.environ.get("WARM_WINDOW_START_HOUR_IE", DEFAULT_WINDOW_START_HOUR_IE))
    end_hour = int(os.environ.get("WARM_WINDOW_END_HOUR_IE", DEFAULT_WINDOW_END_HOUR_IE))

    if args.loop:
        return _run_loop(
            target_url=target_url, question=question, user_id=user_id,
            secret=secret, start_hour=start_hour, end_hour=end_hour,
            sleep_seconds=args.sleep_seconds,
        )
    return _run_once(
        target_url=target_url, question=question, user_id=user_id,
        secret=secret, start_hour=start_hour, end_hour=end_hour,
        force=args.force,
    )


if __name__ == "__main__":
    sys.exit(main())
