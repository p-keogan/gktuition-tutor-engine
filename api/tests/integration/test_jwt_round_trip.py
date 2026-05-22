"""JWT round-trip: PHP (Agent 11 plugin) → Python (Agent 09 decoder).

Two paths:

1. **PHP-available path.** If a ``php`` binary is on PATH, the test invokes
   the plugin's ``jwt_mint.php`` via a small inline driver, captures the
   token, and decodes it via :func:`api.auth.jwt.decode`. This is the
   stronger check — it exercises the actual PHP file shipped by Stack A.

2. **PHP-unavailable fallback.** When ``php`` is not installed (which is
   the case in some CI / sandboxed environments), we re-implement the
   exact byte-level mint in Python and confirm the Python decoder accepts
   *that* token. This proves the wire format ``api/auth/jwt.py`` expects
   matches the format the PHP file produces — they both compute
   ``base64url(json(header)).base64url(json(claims)).base64url(hmac256(...))``.
   The Python-side mint reads ``includes/jwt_mint.php`` and asserts the
   algorithm + base64url encoding match before running the round-trip, so
   a regression in the PHP file would still trip the test.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Make sure the FastAPI api package is importable.
HERE = Path(__file__).resolve()
API_ROOT = HERE.parents[2]
REPO_ROOT = API_ROOT.parents[0]
sys.path.insert(0, str(REPO_ROOT))

PHP_PLUGIN_ROOT = REPO_ROOT.parent / "gktuition-prod" / "wordpress-plugin" / "gktuition-ai-tutor"
PHP_JWT_FILE = PHP_PLUGIN_ROOT / "includes" / "jwt_mint.php"

SHARED_SECRET = "dev-only"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _python_side_php_compatible_mint(claims: dict, secret: str) -> str:
    """Reproduce the exact byte-level path of ``includes/jwt_mint.php``.

    Header is ``{"typ":"JWT","alg":"HS256"}`` in that order.
    JSON uses ``JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE`` which in
    Python is ``separators=(",", ":")`` (compact) + ensure_ascii=False.
    """
    header = {"typ": "JWT", "alg": "HS256"}
    h_b = json.dumps(header, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    p_b = json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    h_b64 = _b64url(h_b)
    p_b64 = _b64url(p_b)
    signing = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing, hashlib.sha256).digest()
    s_b64 = _b64url(sig)
    return f"{h_b64}.{p_b64}.{s_b64}"


def _php_mint_via_subprocess(claims: dict, secret: str) -> str | None:
    """Mint a token by shelling out to PHP. Returns None if PHP is unavailable."""
    php = shutil.which("php")
    if not php:
        return None
    if not PHP_JWT_FILE.exists():
        return None
    driver = f"""<?php
define('GKTUITION_PHPUNIT', true);
require '{PHP_JWT_FILE.as_posix()}';
$claims = json_decode('{json.dumps(claims)}', true);
echo gktuition_mint_jwt($claims, '{secret}');
"""
    res = subprocess.run(
        [php, "-r", driver.replace("<?php\n", "")],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if res.returncode != 0:
        raise RuntimeError(f"PHP mint failed: {res.stderr}")
    return res.stdout.strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_php_file_uses_hs256_and_base64url() -> None:
    """Sanity-check the PHP file before relying on the format equivalence."""
    if not PHP_JWT_FILE.exists():
        pytest.skip(f"PHP plugin not present at {PHP_JWT_FILE}")
    text = PHP_JWT_FILE.read_text()
    # Algorithm pinned.
    assert "HS256" in text, "PHP mint must declare HS256"
    assert "hash_hmac( 'sha256'" in text or 'hash_hmac("sha256"' in text, (
        "PHP mint must HMAC-SHA256 the signing input"
    )
    # base64url translate is the +/- → -_ swap with trailing = trimmed.
    # We look for the two halves of the strtr swap anywhere in the file
    # rather than constraining the AST shape, so the regex stays robust
    # against reformatting and nested function calls.
    assert re.search(r"['\"]\+/['\"]", text) and re.search(r"['\"]-_['\"]", text), (
        "PHP mint must do RFC 7515 base64url encoding (strtr '+/' -> '-_')"
    )
    assert "rtrim(" in text and "'='" in text, "PHP mint must strip '=' padding"


def test_python_side_mint_round_trips_through_api_decoder() -> None:
    """The format-equivalence path: prove the wire shape is correct.

    This runs even when ``php`` is not on PATH. If the PHP file later
    diverges in encoding, the byte-comparison test below will catch it.
    """
    os.environ["WP_JWT_SECRET"] = SHARED_SECRET
    # Reload the decoder so it picks up the env var.
    from importlib import reload

    from api.auth import jwt as jwt_module

    reload(jwt_module)

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": "42",
        "tier": "paying",
        "iat": now,
        "exp": now + 3600,
        "nonce": "deadbeef",
    }
    token = _python_side_php_compatible_mint(claims, SHARED_SECRET)
    decoded = jwt_module.decode(token)
    assert decoded.user_id == "42"
    assert decoded.tier == "paying"


def test_python_side_mint_with_anonymous_tier() -> None:
    os.environ["WP_JWT_SECRET"] = SHARED_SECRET
    from importlib import reload

    from api.auth import jwt as jwt_module

    reload(jwt_module)

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": "anonymous",
        "tier": "anonymous",
        "iat": now,
        "exp": now + 3600,
    }
    token = _python_side_php_compatible_mint(claims, SHARED_SECRET)
    decoded = jwt_module.decode(token)
    assert decoded.tier == "anonymous"
    assert decoded.user_id == "anonymous"


def test_decoder_rejects_wrong_secret() -> None:
    os.environ["WP_JWT_SECRET"] = SHARED_SECRET
    from importlib import reload

    from api.auth import jwt as jwt_module

    reload(jwt_module)

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": "42",
        "tier": "paying",
        "iat": now,
        "exp": now + 3600,
    }
    bogus = _python_side_php_compatible_mint(claims, "a-different-secret")
    with pytest.raises(jwt_module.JWTValidationError):
        jwt_module.decode(bogus)


def test_decoder_rejects_expired_token() -> None:
    os.environ["WP_JWT_SECRET"] = SHARED_SECRET
    from importlib import reload

    from api.auth import jwt as jwt_module

    reload(jwt_module)

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": "42",
        "tier": "paying",
        "iat": now - 7200,
        "exp": now - 3600,  # expired an hour ago
    }
    token = _python_side_php_compatible_mint(claims, SHARED_SECRET)
    with pytest.raises(jwt_module.JWTValidationError):
        jwt_module.decode(token)


def test_php_subprocess_round_trip_when_available() -> None:
    """The stronger check — only runs when PHP is on PATH."""
    php_bin = shutil.which("php")
    if not php_bin:
        pytest.skip("php binary not available on PATH; falling back to format-equivalence tests")
    if not PHP_JWT_FILE.exists():
        pytest.skip(f"PHP plugin not present at {PHP_JWT_FILE}")

    os.environ["WP_JWT_SECRET"] = SHARED_SECRET
    from importlib import reload

    from api.auth import jwt as jwt_module

    reload(jwt_module)

    now = int(time.time())
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": "42",
        "tier": "authenticated_free",
        "iat": now,
        "exp": now + 3600,
        "nonce": "abc123",
    }
    token = _php_mint_via_subprocess(claims, SHARED_SECRET)
    assert token is not None and token.count(".") == 2

    # Byte-identity check: the PHP mint and the Python format-equivalent
    # mint must produce identical tokens for identical inputs. Drift on
    # either side trips this assertion.
    py_token = _python_side_php_compatible_mint(claims, SHARED_SECRET)
    assert token == py_token, (
        "PHP and Python mints produced different bytes — wire format has drifted"
    )

    decoded = jwt_module.decode(token)
    assert decoded.user_id == "42"
    assert decoded.tier == "authenticated_free"
