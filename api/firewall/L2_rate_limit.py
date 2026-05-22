"""L2 — rate limiting + anti-spam (revised 2026-05-21).

Five concerns live in this file. They are kept together because every check
is pure header/body inspection (no LLM, no DB) and they all return the same
class of decision: pass, soft-wall, hard-block.

1. **Per-IP / per-tier token bucket** (per-minute + per-day).

   | tier               | per-minute | per-day |
   |--------------------|-----------:|--------:|
   | anonymous          |          1 |       2 |
   | authenticated_free |          5 |      30 |
   | paying             |         60 |    none |

   The anonymous per-day breach yields a soft "email-capture" wall instead of
   a 429 — this is a funnel hand-off, not a hostile rejection. Other breaches
   yield a hard 429 with ``Retry-After``.

2. **Per-/24 subnet caps** (12/hour, 30/day) — catches IP rotation across a
   single /24. Three breaches in 24h flag the subnet; flagged subnets require
   Turnstile on every subsequent request from them for 7 days, regardless of
   tier.

3. **Honeypot field** — request body's ``website_url`` must be empty / absent.

4. **Minimum dwell-time** — ``X-Dwell-Ms`` header for anonymous tier must be
   >= 1500ms.

5. **User-Agent sanity check** — anonymous requests whose UA prefix matches
   ``bot_user_agents.txt`` get a 403 with no body.

All state is in-memory (single Fly machine, single replica — fine for v1).
When we ever run more than one replica we migrate the bucket store + flagged
subnet set to Redis; the interfaces here are deliberately small enough to
swap.

Toggle: ``RATE_LIMIT_ENABLED=true``.
"""
from __future__ import annotations

import logging
import os
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Deque

from fastapi import HTTPException, Request, status

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ANONYMOUS_SOFT_WALL_STATUS = 402  # "Payment Required" — repurposed as the
# email-capture funnel hand-off. The widget shows the email-capture modal
# whenever it sees a 402 with the JSON body shape below.

ANONYMOUS_SOFT_WALL_BODY = {
    "error": "soft_wall",
    "wall_type": "email_capture",
    "message": (
        "You've used your free questions for today. Sign up for a free "
        "account and keep going."
    ),
}

SUBNET_429_RETRY_AFTER_SECONDS = 15 * 60  # 15 minutes
DEFAULT_429_RETRY_AFTER_SECONDS = 60


# ---------------------------------------------------------------------------
# Bucket store
# ---------------------------------------------------------------------------


@dataclass
class _Bucket:
    """Per-key sliding-window counter.

    Holds two deques of timestamps: one for the per-minute window, one for the
    per-day window. Older-than-window entries are evicted at read time so the
    structures never grow unboundedly.
    """

    minute_window: Deque[float] = field(default_factory=deque)
    day_window: Deque[float] = field(default_factory=deque)

    def evict(self, now: float) -> None:
        while self.minute_window and self.minute_window[0] < now - 60.0:
            self.minute_window.popleft()
        while self.day_window and self.day_window[0] < now - 86400.0:
            self.day_window.popleft()


_buckets: dict[str, _Bucket] = {}
_buckets_lock = Lock()


def _bucket(key: str) -> _Bucket:
    with _buckets_lock:
        b = _buckets.get(key)
        if b is None:
            b = _Bucket()
            _buckets[key] = b
        return b


def clear_buckets() -> None:
    """Reset all rate-limit + subnet state. Used by tests."""
    with _buckets_lock:
        _buckets.clear()
    with _subnet_lock:
        _subnet_breaches.clear()
        _flagged_subnets.clear()


# ---------------------------------------------------------------------------
# Subnet state
# ---------------------------------------------------------------------------


_subnet_breaches: dict[str, Deque[float]] = {}
_flagged_subnets: dict[str, float] = {}  # subnet -> expiry timestamp
_subnet_lock = Lock()


def _record_subnet_breach(subnet: str, now: float) -> int:
    """Record a subnet cap breach, return total breaches in last 24h."""
    with _subnet_lock:
        breaches = _subnet_breaches.setdefault(subnet, deque())
        while breaches and breaches[0] < now - 86400.0:
            breaches.popleft()
        breaches.append(now)
        return len(breaches)


def _flag_subnet(subnet: str, ttl_seconds: int, now: float) -> None:
    with _subnet_lock:
        _flagged_subnets[subnet] = now + ttl_seconds


def is_subnet_flagged(subnet: str | None) -> bool:
    """True iff ``subnet`` is currently on the flagged list."""
    if not subnet:
        return False
    now = time.time()
    with _subnet_lock:
        expiry = _flagged_subnets.get(subnet)
        if expiry is None:
            return False
        if expiry < now:
            del _flagged_subnets[subnet]
            return False
        return True


# ---------------------------------------------------------------------------
# Bot UA list (loaded lazily, refreshed on file mtime change)
# ---------------------------------------------------------------------------


_ua_list_cache: tuple[float, tuple[str, ...]] | None = None
_ua_lock = Lock()


def _load_bot_user_agents() -> tuple[str, ...]:
    """Read and cache the bot-UA prefix list from ``bot_user_agents.txt``.

    Refreshes from disk if the file's mtime has changed.
    """
    global _ua_list_cache
    path = os.environ.get("FIREWALL_BOT_UA_FILE") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "bot_user_agents.txt"
    )
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return ()
    with _ua_lock:
        if _ua_list_cache and _ua_list_cache[0] == mtime:
            return _ua_list_cache[1]
        try:
            with open(path, encoding="utf-8") as fh:
                prefixes = tuple(
                    line.strip().lower()
                    for line in fh
                    if line.strip() and not line.strip().startswith("#")
                )
        except OSError:
            prefixes = ()
        _ua_list_cache = (mtime, prefixes)
        return prefixes


# ---------------------------------------------------------------------------
# Public API — three checks the route layer calls in order
# ---------------------------------------------------------------------------


def check_anti_spam(
    request: Request,
    *,
    body: dict[str, Any],
    tier: str,
) -> None:
    """Honeypot + dwell-time + bot-UA checks.

    Called BEFORE the token-bucket so a bot whose request never had a chance
    of passing the bucket doesn't burn one of the bucket's slots.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    # --- 1. Honeypot ----------------------------------------------------
    honeypot = body.get("website_url")
    if honeypot:
        event(
            "L2",
            "blocked",
            reason="honeypot",
            tier=tier,
            ip=_client_ip(request),
        )
        # 403 with no body — a real browser never fills this field, so a
        # populated value is an unambiguous bot signal.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # --- 2. Dwell-time (anonymous tier only) ----------------------------
    if tier == "anonymous":
        dwell_header = request.headers.get("x-dwell-ms") or request.headers.get(
            "X-Dwell-Ms"
        )
        if dwell_header is not None:
            try:
                dwell_ms = int(dwell_header)
            except ValueError:
                dwell_ms = 0
            if dwell_ms < settings.dwell_min_ms:
                event(
                    "L2",
                    "blocked",
                    reason="dwell_too_short",
                    tier=tier,
                    ip=_client_ip(request),
                    dwell_ms=dwell_ms,
                )
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # --- 3. Bot UA (anonymous tier only) --------------------------------
    if tier == "anonymous":
        ua = (request.headers.get("user-agent") or "").strip().lower()
        if not ua:
            event(
                "L2",
                "blocked",
                reason="empty_ua",
                tier=tier,
                ip=_client_ip(request),
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        prefixes = _load_bot_user_agents()
        for prefix in prefixes:
            if ua.startswith(prefix):
                event(
                    "L2",
                    "blocked",
                    reason="bot_ua",
                    tier=tier,
                    ua=ua[:80],
                )
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


def check_rate_limit(
    request: Request,
    *,
    tier: str,
    user_id: str,
) -> None:
    """Token-bucket per-tier + per-/24-subnet enforcement.

    Returns ``None`` on pass, raises ``HTTPException`` on breach. The
    anonymous per-day breach uses status 402 (soft email-capture wall) per
    the funnel hand-off rationale; every other breach is a hard 429.
    """
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return

    now = time.time()
    ip = _client_ip(request) or "unknown"
    subnet = _subnet_24(ip)

    # --- Per-tier bucket ------------------------------------------------
    if tier == "anonymous":
        per_min = settings.rate_limit_anon_per_minute
        per_day = settings.rate_limit_anon_per_day
        key = f"anon:{ip}"
    elif tier == "authenticated_free":
        per_min = settings.rate_limit_auth_per_minute
        per_day = settings.rate_limit_auth_per_day
        key = f"auth:{user_id}"
    elif tier == "paying":
        per_min = settings.rate_limit_paying_per_minute
        per_day = 0  # unbounded
        key = f"paying:{user_id}"
    else:
        # Unknown tier — be conservative, treat as anonymous.
        per_min = settings.rate_limit_anon_per_minute
        per_day = settings.rate_limit_anon_per_day
        key = f"anon:{ip}"

    b = _bucket(key)
    with _buckets_lock:
        b.evict(now)
        minute_count = len(b.minute_window)
        day_count = len(b.day_window)

        # Day breach for anonymous is a soft wall, not a 429.
        if tier == "anonymous" and per_day and day_count >= per_day:
            event(
                "L2",
                "blocked",
                reason="anon_soft_wall",
                tier=tier,
                ip=ip,
            )
            raise HTTPException(
                status_code=ANONYMOUS_SOFT_WALL_STATUS,
                detail=ANONYMOUS_SOFT_WALL_BODY,
            )

        if per_day and day_count >= per_day:
            event(
                "L2",
                "blocked",
                reason="day_cap",
                tier=tier,
                key=key,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": "rate limit exceeded (daily)"},
                headers={"Retry-After": str(86400)},
            )
        if per_min and minute_count >= per_min:
            event(
                "L2",
                "blocked",
                reason="minute_cap",
                tier=tier,
                key=key,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"error": "rate limit exceeded"},
                headers={"Retry-After": str(DEFAULT_429_RETRY_AFTER_SECONDS)},
            )

        # Within budget — record the request.
        b.minute_window.append(now)
        b.day_window.append(now)
        remaining_minute = max(0, per_min - len(b.minute_window))
        remaining_day = max(0, per_day - len(b.day_window)) if per_day else -1

    # --- Per-/24 subnet cap (anonymous tier only) -----------------------
    if tier == "anonymous":
        sub_key = f"subnet:{subnet}"
        sb = _bucket(sub_key)
        with _buckets_lock:
            sb.evict(now)
            # Convert the minute_window deque into "hour" tracking by storing
            # all timestamps in day_window; we filter the per-hour slice on
            # read. This avoids a third structure.
            hour_count = sum(1 for t in sb.day_window if t >= now - 3600.0)
            day_count = len(sb.day_window)
            hour_cap = settings.rate_limit_subnet_per_hour
            day_cap = settings.rate_limit_subnet_per_day

            breached = hour_count >= hour_cap or day_count >= day_cap
            if breached:
                total = _record_subnet_breach(subnet, now)
                if total >= settings.rate_limit_subnet_flag_threshold:
                    _flag_subnet(
                        subnet,
                        settings.rate_limit_flagged_subnet_ttl_seconds,
                        now,
                    )
                    event(
                        "L2",
                        "flagged",
                        reason="subnet_flag",
                        subnet=subnet,
                        breaches_in_24h=total,
                    )
                event(
                    "L2",
                    "blocked",
                    reason="subnet_cap",
                    subnet=subnet,
                    hour_count=hour_count,
                    day_count=day_count,
                )
                # Persist the firewall_event row to RAW.QUERY_LOG (per the
                # revised spec). We invoke the shared query-log writer so the
                # row joins the same audit trail as actual /query rows.
                _log_subnet_cap_to_query_log(
                    request=request, subnet=subnet, ip=ip
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": "subnet rate limit"},
                    headers={"Retry-After": str(SUBNET_429_RETRY_AFTER_SECONDS)},
                )
            sb.day_window.append(now)

    # Stash the remaining counters on the request for the response wrapper.
    request.state.firewall_rate_limit_remaining_minute = remaining_minute
    if remaining_day >= 0:
        request.state.firewall_rate_limit_remaining_day = remaining_day
    event("L2", "ok", tier=tier, key=key, remaining_minute=remaining_minute)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP — same precedence as L1's helper."""
    xff = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if xff:
        return xff.split(",")[0].strip()
    client: Any = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None


def _subnet_24(ip: str) -> str:
    """Return the /24 prefix for ``ip`` (IPv4) or the /48 for IPv6."""
    if ":" in ip:
        # IPv6 — group into /48 (first three hextets).
        parts = ip.split(":")
        return ":".join(parts[:3]) + "::/48"
    parts = ip.split(".")
    if len(parts) != 4:
        return ip
    return ".".join(parts[:3]) + ".0/24"


def _log_subnet_cap_to_query_log(
    *,
    request: Request,
    subnet: str,
    ip: str,
) -> None:
    """Best-effort: write one firewall_event row to RAW.QUERY_LOG.

    Logged via the same writer Agent 09 uses so the row is visible alongside
    actual queries. Failures here are intentionally swallowed — the rate limit
    response must not be blocked on logging.
    """
    try:
        from ..services import query_log

        row = {
            "query_id": f"firewall_event_{int(time.time() * 1000)}",
            "q": "(firewall_event)",
            "tier": "anonymous",
            "query_type": "firewall_event",
            "query_class": "(none)",
            "model_used": "(none)",
            "top_slug": None,
            "top_reranker_score": 0.0,
            "from_cache": False,
            "elapsed_ms": 0,
            "cost_estimate_cents": 0.0,
            "extracted_question": None,
            "image_bytes_size": None,
            "extraction_outcome": f"firewall_event_type=subnet_cap subnet={subnet} ip={ip}",
            "user_id": "anonymous",
            "created_at": time.time(),
        }
        writer = query_log._writer  # type: ignore[attr-defined]
        if writer is not None:
            res = writer(row)
            # Don't await — keep this strictly fire-and-forget.
            del res
    except Exception:
        logger.debug("subnet_cap logging skipped", exc_info=True)
