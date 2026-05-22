"""L1 — Cloudflare Turnstile bot-check.

For ``POST /query`` anonymous-tier requests, validates the
``cf-turnstile-token`` header against Cloudflare's siteverify endpoint and
returns 403 on failure. Authenticated and paying tiers bypass the check (the
JWT is sufficient signal); flagged-subnet escalation (see L2) re-applies
Turnstile *regardless* of tier, but that escalation is enforced by L2 — this
module just exposes :func:`require_turnstile_check` as a dependency.

Tokens that pass verification are cached in-process for
``settings.turnstile_cache_ttl_seconds`` (5 minutes by default) so a single
session doesn't pay for repeated Cloudflare round-trips.

Toggle: ``TURNSTILE_ENABLED=true``.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import Lock
from typing import Any

from fastapi import HTTPException, Request, status

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    ok: bool
    expires_at: float


_token_cache: dict[str, _CacheEntry] = {}
_cache_lock = Lock()


def _cache_get(token: str) -> bool | None:
    now = time.time()
    with _cache_lock:
        entry = _token_cache.get(token)
        if entry is None:
            return None
        if entry.expires_at < now:
            del _token_cache[token]
            return None
        return entry.ok


def _cache_put(token: str, ok: bool, ttl_seconds: int) -> None:
    with _cache_lock:
        _token_cache[token] = _CacheEntry(ok=ok, expires_at=time.time() + ttl_seconds)


def clear_cache() -> None:
    """Reset the in-process Turnstile cache. Used by tests."""
    with _cache_lock:
        _token_cache.clear()


# ---------------------------------------------------------------------------
# Verifier seam — injectable for tests
# ---------------------------------------------------------------------------


# A verifier takes (token, remote_ip) and returns True iff Cloudflare accepted.
Verifier = Callable[[str, str | None], Awaitable[bool]]

_verifier: Verifier | None = None


def set_verifier(fn: Verifier | None) -> None:
    """Replace the production Cloudflare HTTP verifier. Used by tests."""
    global _verifier
    _verifier = fn


async def _default_verify(token: str, remote_ip: str | None) -> bool:
    """Call Cloudflare's siteverify endpoint with the given token.

    Returns True iff Cloudflare's JSON body has ``"success": true``.
    """
    settings = get_settings()
    secret = settings.turnstile_secret_key
    if not secret:
        # Misconfiguration — fail closed. Operationally this means a deploy
        # that ships ``TURNSTILE_ENABLED=true`` without a key never lets
        # anonymous traffic through; that is the safe behaviour.
        logger.error("TURNSTILE_ENABLED but TURNSTILE_SECRET_KEY unset")
        return False

    import httpx

    data = {"secret": secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(settings.turnstile_verify_url, data=data)
        body = r.json()
    except Exception:
        logger.exception("turnstile verify call failed")
        return False
    return bool(body.get("success"))


async def _verify(token: str, remote_ip: str | None) -> bool:
    fn = _verifier or _default_verify
    return await fn(token, remote_ip)


# ---------------------------------------------------------------------------
# Public dependency
# ---------------------------------------------------------------------------


async def require_turnstile_check(
    request: Request,
    *,
    tier: str,
    forced: bool = False,
) -> None:
    """Validate the ``cf-turnstile-token`` header for anonymous traffic.

    ``tier`` is the JWT-decoded tier as resolved by ``api.routes.query``.
    ``forced=True`` means L2 has flagged the requester's subnet and Turnstile
    must run regardless of tier.

    Raises ``HTTPException(403)`` on failure. Returns ``None`` on pass-through
    or success.
    """
    settings = get_settings()
    if not settings.turnstile_enabled:
        return

    # Bypass for non-anonymous tiers unless explicitly forced.
    if tier != "anonymous" and not forced:
        return

    token = (
        request.headers.get("cf-turnstile-token")
        or request.headers.get("CF-Turnstile-Token")
        or ""
    ).strip()
    if not token:
        event("L1", "blocked", reason="missing_token", tier=tier, forced=forced)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "turnstile token required"},
        )

    cached = _cache_get(token)
    if cached is True:
        event("L1", "ok", reason="cache_hit", tier=tier, forced=forced)
        return
    if cached is False:
        event("L1", "blocked", reason="cache_hit_invalid", tier=tier, forced=forced)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "turnstile token rejected"},
        )

    remote_ip = _client_ip(request)
    ok = await _verify(token, remote_ip)
    _cache_put(token, ok, settings.turnstile_cache_ttl_seconds)

    if ok:
        event("L1", "ok", reason="verified", tier=tier, forced=forced)
        return
    event("L1", "blocked", reason="verify_failed", tier=tier, forced=forced)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "turnstile token rejected"},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP extraction.

    Behind Cloudflare the canonical IP is ``CF-Connecting-IP``; we also accept
    the first hop in ``X-Forwarded-For`` for the Fly.io edge.
    """
    xff = request.headers.get("cf-connecting-ip") or request.headers.get(
        "x-forwarded-for"
    )
    if xff:
        return xff.split(",")[0].strip()
    client: Any = getattr(request, "client", None)
    return getattr(client, "host", None) if client else None
