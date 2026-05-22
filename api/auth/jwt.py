"""JWT decoder for the WordPress widget.

The WordPress plugin ``gktuition-ai-tutor.php`` mints a JWT on the
``/wp-json/gktuition/v1/token`` endpoint (Agent 11's domain). The JWT
carries at minimum:

::

    {
      "iss": "gktuition.ie",
      "sub": <wordpress_user_id>,
      "tier": "anonymous" | "authenticated_free" | "paying",
      "iat": <unix_ts>,
      "exp": <unix_ts>,                  # 60 minutes TTL in v1
      "nonce": <wordpress_nonce>         # placeholder for Phase 3 hardening
    }

We validate signature + expiry, and surface the ``tier`` claim. Anonymous
calls (no Authorization header at all) are explicitly permitted and yield
``tier="anonymous"`` so the rest of the orchestrator can rely on a tier
always being present without branching on ``None``.

The shared secret used to sign the JWT lives in ``WP_JWT_SECRET``. In dev
the WordPress side and the FastAPI side share the literal string
``dev-only`` and the JWT is HS256.

This module also wires the orchestrator's existing
``api.services.auth.set_jwt_decoder`` seam at app startup so the existing
``/image_query`` route uses the same decoder as ``/query`` — single
implementation, two consumers.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# The audience and issuer the WordPress side sets. Pinned so a JWT minted
# for a different service can't be replayed against ours.
EXPECTED_ISS = "gktuition.ie"
EXPECTED_AUD = "gktuition-ai-tutor"

# JWT lifetime is enforced by the ``exp`` claim; we don't have a separate
# "max age" knob.
JWT_ALG = "HS256"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecodedJWT:
    user_id: str
    tier: str
    raw: dict[str, object]


class JWTValidationError(Exception):
    """Raised when a JWT is present but invalid (signature, expiry, etc.).

    The route layer maps this to HTTP 401. A missing JWT is NOT a
    JWTValidationError — it's the anonymous path, and ``decode_or_anonymous``
    returns a synthetic anonymous tier instead of raising.
    """


def decode(token: str) -> DecodedJWT:
    """Decode + verify a JWT minted by the WordPress widget.

    Raises ``JWTValidationError`` on any failure (bad signature, expired,
    missing claims, wrong issuer). The error message is intentionally
    generic — we don't tell the caller *why* their token is bad so
    enumeration attacks gain nothing.
    """
    secret = _require_secret()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALG],
            options={"require": ["exp", "iat", "sub"]},
            audience=EXPECTED_AUD,
            issuer=EXPECTED_ISS,
        )
    except JWTError as exc:
        raise JWTValidationError("invalid token") from exc

    tier = claims.get("tier", "anonymous")
    if tier not in {"anonymous", "authenticated_free", "paying"}:
        raise JWTValidationError("invalid tier claim")
    user_id = claims.get("sub") or claims.get("user_id")
    if not user_id:
        raise JWTValidationError("missing user_id claim")

    return DecodedJWT(user_id=str(user_id), tier=str(tier), raw=claims)


def decode_or_anonymous(token: str | None) -> DecodedJWT:
    """Decode the token if present, else synthesise an anonymous identity.

    The route layer calls this every request. An empty string and ``None``
    are both treated as anonymous; this is the contract the WordPress widget
    expects (an unauthenticated visitor never sees a JWT minted at all).
    """
    if not token or not token.strip():
        return DecodedJWT(user_id="anonymous", tier="anonymous", raw={})
    return decode(token)


def decode_jwt_payload_compat(token: str) -> dict[str, object]:
    """Adapter for ``api.services.auth.set_jwt_decoder``.

    The existing services/auth.py seam expects a callable that returns a
    dict. This wraps :func:`decode` so the image_query route picks up the
    same secret-backed validation as /query.
    """
    res = decode(token)
    return dict(res.raw) | {"user_id": res.user_id, "tier": res.tier}


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _require_secret() -> str:
    secret = os.environ.get("WP_JWT_SECRET")
    if not secret:
        raise RuntimeError(
            "WP_JWT_SECRET environment variable is required. Set it to the "
            "shared secret configured in the WordPress plugin "
            "(in dev: WP_JWT_SECRET=dev-only)."
        )
    return secret


def mint_dev_token(user_id: str, tier: str, *, ttl_seconds: int = 3600) -> str:
    """Mint a JWT for local development / tests only.

    Not exposed on any route — this is a convenience helper for
    ``api/tests/`` and one-off curl experiments. The production token-mint
    path is the WordPress plugin.
    """
    import time as _time

    now = int(_time.time())
    claims = {
        "iss": EXPECTED_ISS,
        "aud": EXPECTED_AUD,
        "sub": user_id,
        "tier": tier,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    secret = _require_secret()
    return jwt.encode(claims, secret, algorithm=JWT_ALG)
