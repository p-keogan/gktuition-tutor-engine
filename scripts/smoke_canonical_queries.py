"""Canonical-query nightly smoke test for ``POST /query``.

Probes production (or any ``--base-url``) with a small set of canonical
"explain X" / single-word queries every morning and asserts each one
returns a real Paul-voiced answer — not the guardrail and not a
voice-anchor-null degraded response. Designed to close the observability
gap surfaced on DAY_31, when voice anchoring shipped, the firewall path
missed it, and ``explain pensions`` silently returned the guardrail for
two days before a manual curl caught it. A daily smoke run would have
caught the regression within 24 hours of deploy.

Why this lives next to ``always_warm.py`` (and is not a richer
``always_warm``)
------------------------------------------------------------------------
``always_warm`` keeps the warehouse + JIT path warm; it only asserts
HTTP 200 because the warm window is meant to be a soft signal. This
script asserts response content: a 200 that returns the guardrail is a
regression we want to page on. Keeping the responsibilities separate
means the warm pinger can stay tolerant (it already self-recovers on
the next fire) while the smoke test stays strict.

Design constraints
------------------
* **Pure stdlib only.** Runs on a stock GitHub Actions Python 3.12 image
  with zero ``pip install``. JWT minting is done by hand (HS256 = base64
  + HMAC-SHA256) so we don't pull ``python-jose``.
* **One script, one purpose.** Does not exercise ``/healthz``,
  ``/image_query``, or the streaming endpoint. The eval harness already
  scores latency and retrieval quality; the smoke test only answers
  *"did the live API return a real Paul-voiced answer for this set of
  queries?"*.
* **Failure JSON is the contract.** The workflow consumes stdout
  verbatim and pastes it into a GitHub issue body, so the structured
  per-query failure block is the API the workflow depends on.
* **Default mode is the resilient bar.** The smoke test asserts that
  ``voice_anchor_strand`` is *not None* (and matches the expected
  strand) — but the README-level resilience contract is "not the
  guardrail, voice-anchored at all". The strict-strand check is run
  alongside but a soft mismatch (anchor populated, wrong strand)
  reports rather than fails — that way a future strand rename doesn't
  page on a green system. Set ``--strict-strand`` to flip the soft
  mismatch into a hard failure when the canonical list is being
  re-baselined.

Exit codes
----------
* 0 — every required query passed.
* 1 — script-level error (network unreachable, JWT minting failed,
  malformed JSON from the server). Distinct from 2 so the workflow can
  tell "API down" (page Fly status) from "API regressed" (open a
  GitHub issue).
* 2 — at least one canonical query failed an assertion. The workflow
  treats this as the open-an-issue signal.

Auth model
----------
The firewall (``L1_turnstile``) requires a Turnstile token for
anonymous-tier traffic. Paying-tier JWT bypasses it. We mint an HS256
token in the exact shape ``api.auth.jwt`` expects (issuer
``gktuition.ie``, audience ``gktuition-ai-tutor``, ``tier=paying``,
``sub=<configurable user>``), so the smoke test rides the same JWT
contract as the WordPress widget — no firewall bypass, no special
"test" tier.

The secret comes from ``WP_JWT_SECRET`` (same env var ``always_warm``
uses). In CI this lives as a GitHub repo secret; locally, export it
before running.
"""
from __future__ import annotations

import argparse
import base64
import dataclasses
import hashlib
import hmac
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger("smoke_canonical_queries")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "https://gktuition-tutor-api.fly.dev"
DEFAULT_USER_ID = "smoke-canonical-bot"
HTTP_TIMEOUT_SECONDS = 30.0

# The firewall serves the guardrail when retrieval falls below
# ``RETRIEVAL_FLOOR`` and no slug-anchor override saves it. The canonical
# string is defined exactly once in the source tree:
#
#   api/orchestrator/synthesizer.py — ``GUARDRAIL_ANSWER`` constant.
#
# We pin a prefix here rather than the full string so the check is robust
# to whitespace tweaks. If the copy ever changes in the source, this
# constant MUST be updated in lockstep — the smoke test starts failing
# the next morning until the operator fixes both places. That tight
# coupling is desired: we never want the smoke test to silently pass on
# a refreshed guardrail string.
#
# Format note: the source uses U+2014 EM DASH (—), not "--". Don't
# substitute it.
GUARDRAIL_PREFIX_RE = re.compile(r"^\s*I'm not sure\s*—\s*try one of these related tutorials")


# ---------------------------------------------------------------------------
# Canonical query list
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class CanonicalQuery:
    """One entry in the smoke list.

    * ``query`` — the literal student-facing text we POST.
    * ``expected_strand`` — the voice anchor we expect. Used for the
      strict-strand soft check; the default (loose) bar only asserts
      that ``voice_anchor_strand`` is not None.
    * ``note`` — operator-readable rationale for inclusion. Surfaces in
      both the success log line and any failure JSON.
    * ``known_floor_miss`` — True for entries that depend on a
      feature flag that hasn't shipped yet (case in point on
      2026-05-28: the AGENT_24 iter-2 fallback for "circumcentre" as a
      single-word query). Default-mode runs report these but don't
      assert on them; ``--include-known-floor-misses`` promotes them
      to strict so the operator can probe a fix candidate.
    """

    query: str
    expected_strand: str
    note: str
    known_floor_miss: bool = False


CANONICAL_QUERIES: tuple[CanonicalQuery, ...] = (
    CanonicalQuery(
        query="explain pensions please",
        expected_strand="LCHL_Financial_Maths",
        note="DAY_31 original failure mode — must stay green post-iter-1.",
    ),
    CanonicalQuery(
        query="explain how pin codes work",
        expected_strand="LCHL_Probability",
        note="DAY_31 original failure mode.",
    ),
    CanonicalQuery(
        query="explain bernoulli trials",
        expected_strand="LCHL_Probability",
        note="DAY_31 original failure mode.",
    ),
    CanonicalQuery(
        query="explain the circumcentre",
        expected_strand="LCHL_Geometry_1",
        note="DAY_32 'explain X' construction-strand probe.",
    ),
    CanonicalQuery(
        query="what is a confidence interval",
        expected_strand="LCHL_Statistics",
        note="Sanity — single-strand concept query.",
    ),
    CanonicalQuery(
        query="what is the central limit theorem",
        expected_strand="LCHL_Statistics",
        note="Sanity — multi-word concept query.",
    ),
    CanonicalQuery(
        query="circumcentre",
        expected_strand="LCHL_Geometry_1",
        note=(
            "DAY_32 single-word synonym-mismatch case. Currently a known "
            "floor miss; flip known_floor_miss=False once AGENT_24 ships."
        ),
        known_floor_miss=True,
    ),
)


# ---------------------------------------------------------------------------
# JWT minting (stdlib HS256)
# ---------------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    """Base64-url-encode without padding (the JWT spec strips ``=``)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _mint_jwt(*, user_id: str, secret: str, ttl_seconds: int = 3600) -> str:
    """Mint an HS256 JWT shaped to the WordPress contract.

    Mirrors :func:`api.auth.jwt.mint_dev_token` exactly: issuer
    ``gktuition.ie``, audience ``gktuition-ai-tutor``, ``tier=paying``
    (so the firewall bypasses Turnstile), and ``iat``/``exp`` set
    relative to wall clock. Stdlib-only by design — we don't pull
    ``python-jose`` because the smoke script needs to run on a stock
    Python 3.12 image with zero ``pip install``.
    """
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    claims = {
        "iss": "gktuition.ie",
        "aud": "gktuition-ai-tutor",
        "sub": user_id,
        "tier": "paying",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    sig = hmac.new(
        secret.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return signing_input + "." + _b64url(sig)


# ---------------------------------------------------------------------------
# HTTP probe
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class ProbeResult:
    """Outcome of a single canonical-query POST."""

    query: str
    expected_strand: str
    note: str
    known_floor_miss: bool

    status_code: int
    elapsed_ms: int
    body: dict[str, Any] | None
    raw_body_preview: str  # first 120 chars of the response text

    network_error: str | None = None  # set iff the request itself failed

    @property
    def got_strand(self) -> str | None:
        if not self.body:
            return None
        val = self.body.get("voice_anchor_strand")
        return val if isinstance(val, str) else None

    @property
    def answer(self) -> str:
        return (self.body or {}).get("answer", "") or ""

    @property
    def is_guardrail(self) -> bool:
        return bool(GUARDRAIL_PREFIX_RE.match(self.answer))


def _probe_one(
    *,
    base_url: str,
    jwt_token: str,
    query: CanonicalQuery,
    timeout_s: float = HTTP_TIMEOUT_SECONDS,
) -> ProbeResult:
    """POST one canonical query and capture the result.

    Never raises on a remote error — we want the failure JSON to carry
    network errors verbatim so the workflow can paste them into the
    GitHub issue body.
    """
    url = base_url.rstrip("/") + "/query"
    payload = json.dumps({"q": query.query, "debug": False}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {jwt_token}",
            "User-Agent": "gktuition-smoke-canonical/1.0",
        },
    )

    started = time.perf_counter()
    status_code = 0
    raw = ""
    network_error: str | None = None
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status_code = resp.getcode()
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        raw = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Distinct from an HTTPError — the API didn't answer at all.
        network_error = f"{type(exc).__name__}: {exc}"
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    body: dict[str, Any] | None = None
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                body = parsed
        except json.JSONDecodeError:
            body = None

    return ProbeResult(
        query=query.query,
        expected_strand=query.expected_strand,
        note=query.note,
        known_floor_miss=query.known_floor_miss,
        status_code=status_code,
        elapsed_ms=elapsed_ms,
        body=body,
        raw_body_preview=raw[:120],
        network_error=network_error,
    )


# ---------------------------------------------------------------------------
# Assertion logic
# ---------------------------------------------------------------------------


def _failure_reason(result: ProbeResult, *, strict_strand: bool) -> str | None:
    """Return a short human-readable failure reason, or None if pass.

    Order of checks mirrors how an operator would triage: network →
    HTTP → guardrail → voice-anchor populated → (optional) strand
    matches.
    """
    if result.network_error is not None:
        return f"network_error: {result.network_error}"
    if result.status_code != 200:
        return f"http_status={result.status_code}"
    if result.body is None:
        return "non_json_body"
    if result.is_guardrail:
        return "guardrail_returned"
    if result.got_strand is None:
        return "voice_anchor_strand=null"
    if strict_strand and result.got_strand != result.expected_strand:
        return (
            f"strand_mismatch: expected={result.expected_strand} "
            f"got={result.got_strand}"
        )
    return None


def _failure_json(result: ProbeResult, *, reason: str) -> dict[str, Any]:
    """Structured per-failure record. The workflow pastes this verbatim."""
    return {
        "query": result.query,
        "expected_strand": result.expected_strand,
        "got_strand": result.got_strand,
        "body_first_120_chars": (
            result.answer[:120] if result.answer else result.raw_body_preview
        ),
        "elapsed_ms": result.elapsed_ms,
        "failure_reason": reason,
        "note": result.note,
    }


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def _run(
    *,
    base_url: str,
    user_id: str,
    secret: str,
    include_known_floor_misses: bool,
    strict_strand: bool,
    report_only: bool,
) -> int:
    """Run every canonical query and return the appropriate exit code."""
    try:
        jwt_token = _mint_jwt(user_id=user_id, secret=secret)
    except Exception as exc:  # noqa: BLE001 — diagnostic catch-all on init.
        logger.error("JWT minting failed: %s", exc)
        return 1

    strict_results: list[tuple[ProbeResult, str]] = []   # (result, reason)
    soft_results: list[ProbeResult] = []                 # known-floor-miss reports
    network_seen = False

    for q in CANONICAL_QUERIES:
        result = _probe_one(base_url=base_url, jwt_token=jwt_token, query=q)
        if result.network_error is not None:
            network_seen = True

        reason = _failure_reason(result, strict_strand=strict_strand)
        treat_strict = (not q.known_floor_miss) or include_known_floor_misses

        if treat_strict:
            if reason is None:
                logger.info(
                    "ok query=%r strand=%s elapsed_ms=%d",
                    q.query, result.got_strand, result.elapsed_ms,
                )
            else:
                logger.warning(
                    "FAIL query=%r reason=%s elapsed_ms=%d",
                    q.query, reason, result.elapsed_ms,
                )
                strict_results.append((result, reason))
        else:
            # known-floor-miss row in default mode: report soft and move on.
            soft_results.append(result)
            soft_status = (
                "soft_pass" if reason is None else f"soft_fail({reason})"
            )
            logger.info(
                "soft query=%r status=%s elapsed_ms=%d",
                q.query, soft_status, result.elapsed_ms,
            )

    strict_total = sum(1 for q in CANONICAL_QUERIES if (not q.known_floor_miss) or include_known_floor_misses)
    strict_pass = strict_total - len(strict_results)
    soft_total = len(soft_results)
    soft_pass = sum(
        1 for r in soft_results
        if _failure_reason(r, strict_strand=strict_strand) is None
    )

    # Print a single-line summary even on failure so the workflow log is
    # immediately legible. Detailed per-failure JSON comes after.
    print(
        f"SMOKE {'OK' if not strict_results else 'FAIL'} "
        f"— {strict_pass}/{strict_total} strict"
        + (f" + {soft_pass}/{soft_total} known-floor-miss (reported only)" if soft_total else ""),
        flush=True,
    )

    if strict_results:
        print("", flush=True)  # blank separator
        for result, reason in strict_results:
            print(json.dumps(_failure_json(result, reason=reason), indent=2), flush=True)

    if report_only:
        return 0

    # Exit-code policy: distinguish "API down" from "API regressed" so the
    # workflow can route the issue to the right runbook section. A network
    # error on *any* probe → exit 1 (API down). Otherwise, any strict
    # failure → exit 2 (API regressed).
    if network_seen:
        return 1
    if strict_results:
        return 2
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical-query smoke test for POST /query. Asserts each "
            "query returns a real Paul-voiced answer (not the guardrail)."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SMOKE_BASE_URL", DEFAULT_BASE_URL),
        help=f"API root (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--user-id",
        default=os.environ.get("SMOKE_USER_ID", DEFAULT_USER_ID),
        help="JWT 'sub' claim; surfaces in RAW.QUERY_LOG.",
    )
    parser.add_argument(
        "--include-known-floor-misses",
        action="store_true",
        help=(
            "Promote known-floor-miss queries to strict assertion. Use "
            "when probing a fix candidate; default mode reports them softly."
        ),
    )
    parser.add_argument(
        "--strict-strand",
        action="store_true",
        help=(
            "Fail on voice_anchor_strand mismatch as well as null. "
            "Default mode treats a populated-but-wrong strand as a soft "
            "warning so a future strand rename doesn't page on a green system."
        ),
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help=(
            "Print the summary + any failure JSON, but always exit 0. "
            "Use when piping output to a paste-only consumer (eg a dry "
            "workflow run that should never open an issue)."
        ),
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,  # keep stdout reserved for the workflow contract.
    )

    secret = os.environ.get("WP_JWT_SECRET")
    if not secret:
        logger.error(
            "WP_JWT_SECRET not set — refusing to run. In CI this is a "
            "repo secret; locally, export WP_JWT_SECRET first."
        )
        return 1

    return _run(
        base_url=args.base_url,
        user_id=args.user_id,
        secret=secret,
        include_known_floor_misses=args.include_known_floor_misses,
        strict_strand=args.strict_strand,
        report_only=args.report_only,
    )


if __name__ == "__main__":
    sys.exit(main())
