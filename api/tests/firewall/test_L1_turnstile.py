"""L1 — Turnstile dependency tests."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException, Request

from api.firewall import L1_turnstile


def _make_request(headers: dict[str, str] | None = None, client_host: str = "1.2.3.4") -> Request:
    """Cheap synthetic Request — covers the headers + client attributes the
    layer reads. Avoids spinning up a full TestClient where unnecessary.
    """
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


@pytest.mark.asyncio
async def test_anonymous_with_valid_token_passes(firewall_env: Any) -> None:
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")

    async def fake_verify(token: str, ip: str | None) -> bool:
        return token == "good"

    L1_turnstile.set_verifier(fake_verify)

    req = _make_request(headers={"cf-turnstile-token": "good"})
    await L1_turnstile.require_turnstile_check(req, tier="anonymous")


@pytest.mark.asyncio
async def test_anonymous_with_invalid_token_403s(firewall_env: Any) -> None:
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")

    async def fake_verify(token: str, ip: str | None) -> bool:
        return False

    L1_turnstile.set_verifier(fake_verify)
    req = _make_request(headers={"cf-turnstile-token": "bad"})
    with pytest.raises(HTTPException) as exc:
        await L1_turnstile.require_turnstile_check(req, tier="anonymous")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_anonymous_with_missing_token_403s(firewall_env: Any) -> None:
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")
    req = _make_request()
    with pytest.raises(HTTPException) as exc:
        await L1_turnstile.require_turnstile_check(req, tier="anonymous")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_authenticated_tiers_bypass(firewall_env: Any) -> None:
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")
    req = _make_request()  # no token
    await L1_turnstile.require_turnstile_check(req, tier="authenticated_free")
    await L1_turnstile.require_turnstile_check(req, tier="paying")


@pytest.mark.asyncio
async def test_paying_tier_forced_via_flagged_subnet(firewall_env: Any) -> None:
    """Flagged-subnet escalation forces Turnstile regardless of tier."""
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")
    req = _make_request()  # no token
    with pytest.raises(HTTPException) as exc:
        await L1_turnstile.require_turnstile_check(req, tier="paying", forced=True)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_token_validation_cached(firewall_env: Any) -> None:
    """A valid token should not re-hit Cloudflare on the second request."""
    firewall_env(TURNSTILE_ENABLED="true", TURNSTILE_SECRET_KEY="test-secret")
    calls = {"n": 0}

    async def fake_verify(token: str, ip: str | None) -> bool:
        calls["n"] += 1
        return True

    L1_turnstile.set_verifier(fake_verify)
    req = _make_request(headers={"cf-turnstile-token": "good"})
    await L1_turnstile.require_turnstile_check(req, tier="anonymous")
    await L1_turnstile.require_turnstile_check(req, tier="anonymous")
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_disabled_is_passthrough(firewall_env: Any) -> None:
    """With ``TURNSTILE_ENABLED=false`` (default) the check is a no-op."""
    # No env vars set → settings.turnstile_enabled is False.
    req = _make_request()
    await L1_turnstile.require_turnstile_check(req, tier="anonymous")


@pytest.mark.asyncio
async def test_misconfigured_secret_fails_closed(firewall_env: Any) -> None:
    """Enabling Turnstile without a secret means every request fails."""
    firewall_env(TURNSTILE_ENABLED="true")  # no TURNSTILE_SECRET_KEY
    # The default verifier won't be reached because we don't inject a
    # caller — the layer hits its own ``_default_verify``, which short-circuits
    # to False when no secret is set.
    L1_turnstile.set_verifier(None)
    req = _make_request(headers={"cf-turnstile-token": "good"})
    with pytest.raises(HTTPException) as exc:
        await L1_turnstile.require_turnstile_check(req, tier="anonymous")
    assert exc.value.status_code == 403
