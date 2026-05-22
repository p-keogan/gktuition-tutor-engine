"""L2 — rate limit + anti-spam tests.

Covers every check declared in the prompt's verification grid:

* token-bucket exhaustion + refill
* per-tier limits enforced separately
* per-/24 subnet cap
* flagged-subnet persistence
* honeypot rejection
* dwell-time rejection
* bot UA rejection
"""
from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import HTTPException, Request

from api.firewall import L2_rate_limit


def _req(headers: dict[str, str] | None = None, *, client_host: str = "1.2.3.4") -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/query",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": (client_host, 0),
        "query_string": b"",
    }
    return Request(scope)


# ----------------------------------------------------------------------------
# Anti-spam
# ----------------------------------------------------------------------------


def test_honeypot_rejected(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_anti_spam(
            req, body={"q": "foo", "website_url": "http://evil.example"}, tier="anonymous"
        )
    assert exc.value.status_code == 403


def test_dwell_too_short_rejected(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0", "x-dwell-ms": "200"})
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="anonymous")
    assert exc.value.status_code == 403


def test_dwell_above_threshold_passes(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0", "x-dwell-ms": "2500"})
    L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="anonymous")


def test_bot_user_agent_rejected(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "python-requests/2.31"})
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="anonymous")
    assert exc.value.status_code == 403


def test_empty_user_agent_rejected(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={})
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="anonymous")
    assert exc.value.status_code == 403


def test_paying_bypasses_dwell_and_ua(firewall_env: Any) -> None:
    """Authenticated and paying tiers bypass dwell / UA checks."""
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={})  # no UA, no dwell
    L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="paying")
    L2_rate_limit.check_anti_spam(req, body={"q": "foo"}, tier="authenticated_free")


# ----------------------------------------------------------------------------
# Per-tier token bucket
# ----------------------------------------------------------------------------


def test_anonymous_minute_cap(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    # 2nd hit in the same minute — per-minute is 1.
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    assert exc.value.status_code == 429


def test_anonymous_soft_wall_after_two_requests(firewall_env: Any) -> None:
    """The 3rd anonymous request in a day yields a 402 soft wall, not 429."""
    firewall_env(
        RATE_LIMIT_ENABLED="true",
        RATE_LIMIT_ANON_PER_MINUTE="10",  # generous on the minute axis
    )
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    assert exc.value.status_code == L2_rate_limit.ANONYMOUS_SOFT_WALL_STATUS
    assert exc.value.detail["error"] == "soft_wall"


def test_auth_free_independent_of_anonymous(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    # Anonymous quota burns.
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    # Authenticated user from the same IP gets their own bucket.
    for _ in range(5):
        L2_rate_limit.check_rate_limit(req, tier="authenticated_free", user_id="u_alice")
    with pytest.raises(HTTPException):
        L2_rate_limit.check_rate_limit(
            req, tier="authenticated_free", user_id="u_alice"
        )


def test_paying_per_minute_is_60(firewall_env: Any) -> None:
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    for _ in range(60):
        L2_rate_limit.check_rate_limit(req, tier="paying", user_id="u_paying")
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_rate_limit(req, tier="paying", user_id="u_paying")
    assert exc.value.status_code == 429


def test_token_bucket_refill_after_minute(firewall_env: Any) -> None:
    """The per-minute bucket evicts entries older than 60s."""
    firewall_env(RATE_LIMIT_ENABLED="true")
    req = _req(headers={"user-agent": "Mozilla/5.0"})
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    # Backdate the recorded timestamp so the eviction logic considers the
    # earlier request to be > 60s old.
    bucket = L2_rate_limit._bucket("anon:1.2.3.4")
    bucket.minute_window[0] = time.time() - 120  # type: ignore[union-attr]
    # The next call should pass — minute bucket has been emptied.
    L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")


# ----------------------------------------------------------------------------
# Per-/24 subnet cap + flagging
# ----------------------------------------------------------------------------


def test_subnet_cap_fires(firewall_env: Any) -> None:
    """30 requests from different IPs in the same /24 trip the day-cap."""
    firewall_env(
        RATE_LIMIT_ENABLED="true",
        # Loosen the per-IP limits so the subnet cap is what fires.
        RATE_LIMIT_ANON_PER_MINUTE="100",
        RATE_LIMIT_ANON_PER_DAY="100",
        RATE_LIMIT_SUBNET_PER_HOUR="100",
        RATE_LIMIT_SUBNET_PER_DAY="5",
    )
    for i in range(5):
        req = _req(
            headers={"user-agent": "Mozilla/5.0"},
            client_host=f"1.2.3.{10 + i}",
        )
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    # 6th request from a 6th IP in the same /24 → subnet cap.
    req = _req(headers={"user-agent": "Mozilla/5.0"}, client_host="1.2.3.99")
    with pytest.raises(HTTPException) as exc:
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    assert exc.value.status_code == 429
    assert exc.value.headers["Retry-After"] == str(
        L2_rate_limit.SUBNET_429_RETRY_AFTER_SECONDS
    )


def test_subnet_flagged_after_three_breaches(firewall_env: Any) -> None:
    firewall_env(
        RATE_LIMIT_ENABLED="true",
        RATE_LIMIT_ANON_PER_MINUTE="100",
        RATE_LIMIT_ANON_PER_DAY="100",
        RATE_LIMIT_SUBNET_PER_HOUR="100",
        RATE_LIMIT_SUBNET_PER_DAY="0",  # immediate trip
        RATE_LIMIT_SUBNET_FLAG_THRESHOLD="3",
    )
    for _ in range(3):
        req = _req(
            headers={"user-agent": "Mozilla/5.0"}, client_host="5.6.7.8"
        )
        with pytest.raises(HTTPException):
            L2_rate_limit.check_rate_limit(
                req, tier="anonymous", user_id="anonymous"
            )
    assert L2_rate_limit.is_subnet_flagged("5.6.7.0/24") is True


def test_subnet_flag_expires_at_ttl(firewall_env: Any) -> None:
    firewall_env(
        RATE_LIMIT_ENABLED="true",
        RATE_LIMIT_FLAGGED_SUBNET_TTL_SECONDS="1",
        RATE_LIMIT_ANON_PER_DAY="100",
        RATE_LIMIT_ANON_PER_MINUTE="100",
        RATE_LIMIT_SUBNET_PER_DAY="0",
        RATE_LIMIT_SUBNET_FLAG_THRESHOLD="1",
    )
    req = _req(headers={"user-agent": "Mozilla/5.0"}, client_host="9.9.9.1")
    with pytest.raises(HTTPException):
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
    assert L2_rate_limit.is_subnet_flagged("9.9.9.0/24") is True
    time.sleep(1.1)
    assert L2_rate_limit.is_subnet_flagged("9.9.9.0/24") is False


# ----------------------------------------------------------------------------
# Disabled passthrough
# ----------------------------------------------------------------------------


def test_disabled_is_passthrough(firewall_env: Any) -> None:
    req = _req(headers={"user-agent": "python-requests/2.31"})
    # Anti-spam — no-op when disabled.
    L2_rate_limit.check_anti_spam(req, body={"website_url": "x"}, tier="anonymous")
    # Rate limit — no-op when disabled.
    for _ in range(100):
        L2_rate_limit.check_rate_limit(req, tier="anonymous", user_id="anonymous")
