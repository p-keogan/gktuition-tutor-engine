"""
Auth helper — production-wire-up TBD by the user.

ASSUMPTION (Agent 06): the WordPress widget passes a JWT in
`Authorization: Bearer <token>` whose payload contains at least:

    {"user_id": "...", "tier": "anonymous" | "authenticated_free" | "paying", ...}

The full decode (signature verification, issuer check, etc.) is presumed to
live elsewhere in the codebase. If it doesn't, replace
`decode_jwt_payload` with the project's actual JWT decoder.

For the agent-06 endpoint we need only:
  - extract the JWT from the request
  - obtain its claims
  - confirm tier == "paying"
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass
class AuthContext:
    user_id: str
    tier: str


# Default decoder is a no-op that always raises — the real one MUST be
# injected at app startup via `set_jwt_decoder`. Keeping the seam explicit
# makes test mocking trivial and prevents accidentally shipping an unsigned
# token path.
_decoder: Callable[[str], dict] | None = None


def set_jwt_decoder(fn: Callable[[str], dict]) -> None:
    """Register the project's real JWT decoder at app startup."""
    global _decoder
    _decoder = fn


def decode_jwt_payload(token: str) -> dict:
    if _decoder is None:
        raise RuntimeError(
            "No JWT decoder configured. Call set_jwt_decoder(...) at app startup."
        )
    return _decoder(token)


def require_paying_tier(request: Request) -> AuthContext:
    """
    FastAPI dependency. Extracts the JWT, decodes it, and rejects with HTTP 403
    if the tier is not 'paying'.
    """
    authz = request.headers.get("authorization") or request.headers.get("Authorization")
    if not authz or not authz.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "missing or malformed authorization header"},
        )
    token = authz.split(" ", 1)[1].strip()
    try:
        claims = decode_jwt_payload(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid token"},
        ) from exc

    tier = claims.get("tier")
    if tier != "paying":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "image queries require a paid subscription"},
        )

    user_id = claims.get("user_id") or claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token missing user_id"},
        )

    return AuthContext(user_id=str(user_id), tier=tier)
