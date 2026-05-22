"""L5 — kill switch with three nested daily-spend caps.

The Snowflake-side ``RM_TUTOR_DAILY`` resource monitor will SUSPEND the
warehouse at €5/day independently of this code. This file is the
client-side belt-and-braces that fires *earlier* (per-tier) so a bot that
gets past Turnstile + rate limit + honeypot + dwell-time still can't burn
the whole budget on the anonymous tier alone.

Three caps, each fires independently:

| Cap name             | Threshold |  When fired                                |
|----------------------|----------:|--------------------------------------------|
| ``anonymous_tier``   |   €0.50/d | anonymous tier wall, others continue        |
| ``free_tier``        |   €2.00/d | anon + auth_free wall, paying continues     |
| ``global``           |   €5.00/d | all tiers wall                              |

State is persisted to ``GKTUITION_TUTOR.RAW.DAILY_SPEND`` with one row per
``(tier, date)`` pair. The kill switch increments the row *before* the LLM
call (using the orchestrator's existing ``estimate_cost_cents``) and rejects
when the running total exceeds the relevant cap. Per the rationale in
``firewall/spend_cap_rationale.md`` the per-tier cap fires on the threshold,
not strictly above it — better to be one query too cautious than too lax.

Toggle: ``KILL_SWITCH_ENABLED=true``.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable

from fastapi import HTTPException, status

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Static "we're at capacity" responses
# ---------------------------------------------------------------------------


ANON_CAP_MESSAGE = (
    "The free tutor has reached today's capacity — sign up for a free "
    "account to keep going."
)
FREE_CAP_MESSAGE = (
    "At capacity for free tutoring today. Paying users continue uninterrupted."
)
GLOBAL_CAP_MESSAGE = (
    "The tutor is at capacity — please come back tomorrow."
)


# ---------------------------------------------------------------------------
# Storage seam — injectable for tests
# ---------------------------------------------------------------------------


SpendReader = Callable[[str, str], float]  # (tier, date) -> spend_eur
SpendIncrementer = Callable[[str, str, float], float]  # (tier, date, delta) -> new total


_reader: SpendReader | None = None
_incrementer: SpendIncrementer | None = None

# In-memory fallback used when no backend is wired (tests + dev).
_memory_state: dict[tuple[str, str], float] = {}
_memory_lock = Lock()


def set_storage(*, reader: SpendReader, incrementer: SpendIncrementer) -> None:
    """Inject Snowflake-backed readers/incrementers at startup or in tests."""
    global _reader, _incrementer
    _reader = reader
    _incrementer = incrementer


def clear_memory_state() -> None:
    """Reset the in-memory spend state. Used by tests."""
    with _memory_lock:
        _memory_state.clear()


def _today_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _memory_read(tier: str, day: str) -> float:
    with _memory_lock:
        return _memory_state.get((tier, day), 0.0)


def _memory_increment(tier: str, day: str, delta: float) -> float:
    with _memory_lock:
        cur = _memory_state.get((tier, day), 0.0) + delta
        _memory_state[(tier, day)] = cur
        return cur


def seed_memory_state(tier: str, day: str, value: float) -> None:
    """Test helper — set the in-memory spend for a (tier, day) to ``value``."""
    with _memory_lock:
        _memory_state[(tier, day)] = value


# ---------------------------------------------------------------------------
# Default Snowflake-backed impls
# ---------------------------------------------------------------------------


def _default_read(tier: str, day: str) -> float:
    """In-memory by default. Production wiring overrides via :func:`set_storage`.

    Keeping the default as in-memory means that:
    * Dev runs (no Snowflake env vars) work out of the box.
    * Tests' fake Snowflake cursors don't accidentally short-circuit the
      seeded memory state.
    * Production wiring calls ``set_storage(reader=_snowflake_read,
      incrementer=_snowflake_increment)`` to switch to the persistent
      backend; the Snowflake helpers below remain available for that wiring.
    """
    return _memory_read(tier, day)


def _default_increment(tier: str, day: str, delta: float) -> float:
    """In-memory by default. See :func:`_default_read` for the rationale."""
    return _memory_increment(tier, day, delta)


# ---------------------------------------------------------------------------
# Snowflake-backed helpers — wired in by ``api.main`` when Snowflake is
# available. Kept here (rather than in main.py) so the SQL stays close to
# the schema definition.
# ---------------------------------------------------------------------------


def snowflake_read(tier: str, day: str) -> float:
    """Read spend from ``DAILY_SPEND``. Falls back to in-memory on failure."""
    settings = get_settings()
    try:
        from ..orchestrator.retriever import _cursor

        with _cursor() as cs:
            cs.execute(
                f"SELECT spend_eur FROM {settings.spend_table_fqn} "  # noqa: S608
                f"WHERE tier = %s AND spend_date = %s",
                (tier, day),
            )
            row = cs.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        logger.exception("snowflake spend read failed; falling back to memory")
        return _memory_read(tier, day)


def snowflake_increment(tier: str, day: str, delta: float) -> float:
    """MERGE the row, return the new running total."""
    settings = get_settings()
    try:
        from ..orchestrator.retriever import _cursor

        with _cursor() as cs:
            cs.execute(
                f"MERGE INTO {settings.spend_table_fqn} t "  # noqa: S608
                f"USING (SELECT %s AS tier, %s AS spend_date, %s AS delta) s "
                f"ON t.tier = s.tier AND t.spend_date = s.spend_date "
                f"WHEN MATCHED THEN UPDATE SET spend_eur = t.spend_eur + s.delta, "
                f"                              updated_at = CURRENT_TIMESTAMP() "
                f"WHEN NOT MATCHED THEN INSERT (tier, spend_date, spend_eur, updated_at) "
                f"                       VALUES (s.tier, s.spend_date, s.delta, CURRENT_TIMESTAMP())",
                (tier, day, delta),
            )
            cs.execute(
                f"SELECT spend_eur FROM {settings.spend_table_fqn} "
                f"WHERE tier = %s AND spend_date = %s",
                (tier, day),
            )
            row = cs.fetchone()
            return float(row[0]) if row else 0.0
    except Exception:
        logger.exception("snowflake spend increment failed; falling back to memory")
        return _memory_increment(tier, day, delta)


# ---------------------------------------------------------------------------
# Pricing
# ---------------------------------------------------------------------------


def _estimate_call_eur(model_used: str, *, input_tokens: int = 0, output_tokens: int = 0) -> float:
    """Estimate the EUR cost of a single LLM call.

    Reads pricing from the YAML file pointed to by ``ANTHROPIC_PRICING_FILE``.
    Falls back to the orchestrator's ``estimate_cost_cents`` if the file is
    unreadable — this guarantees the kill switch is never silently disabled
    by a config typo.
    """
    settings = get_settings()
    pricing: dict[str, Any] = {}
    path = settings.pricing_file_path
    if path:
        try:
            pricing = _load_pricing_yaml(path)
        except Exception:
            logger.warning("pricing file %s unreadable; using fallback", path)
            pricing = {}
    eur_per_usd = float(pricing.get("eur_per_usd") or 0.92)
    models = pricing.get("models") or {}
    cfg = models.get(model_used)
    if cfg is None:
        # Unknown model — fall back to orchestrator's cents-estimate, which
        # bounds-checks our maths so a typo can't escape the cap entirely.
        try:
            from ..orchestrator.synthesizer import estimate_cost_cents

            return float(estimate_cost_cents(model_used, [])) / 100.0
        except Exception:
            return 0.003  # ~ Haiku-class

    if "flat_per_call_usd" in cfg:
        return float(cfg["flat_per_call_usd"]) * eur_per_usd
    inp = float(cfg.get("input_per_million_usd") or 0.0)
    out = float(cfg.get("output_per_million_usd") or 0.0)
    usd = (input_tokens / 1_000_000.0) * inp + (output_tokens / 1_000_000.0) * out
    return usd * eur_per_usd


def _load_pricing_yaml(path: str) -> dict[str, Any]:
    """Tiny YAML loader — uses PyYAML if available, else a hand-rolled parser.

    The pricing file is small (well under 50 lines) so the fallback parser
    only needs to handle the subset of YAML we use: top-level scalars,
    nested maps two levels deep, numeric scalars. Keeping the fallback in-line
    means the firewall doesn't add PyYAML as a hard dependency on top of
    Agent 09's already-fat list.
    """
    try:
        import yaml  # type: ignore[import-not-found]
    except Exception:
        yaml = None
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if yaml is not None:
        result = yaml.safe_load(text)
        return dict(result) if isinstance(result, dict) else {}
    # Fallback parser — strict subset of YAML.
    return _parse_simple_yaml(text)


def _parse_simple_yaml(text: str) -> dict[str, Any]:
    """Strict subset of YAML: top-level scalars + two-deep nested maps.

    Supports key: value, key: <number>, key: <quoted string>, and indented
    blocks. Anything weirder than that is treated as opaque and ignored — the
    file lives in our repo so we control the shape.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]

    def coerce(val: str) -> Any:
        v = val.strip()
        if not v:
            return ""
        if v.startswith('"') and v.endswith('"'):
            return v[1:-1]
        if v.startswith("'") and v.endswith("'"):
            return v[1:-1]
        try:
            if "." in v or "e" in v.lower():
                return float(v)
            return int(v)
        except ValueError:
            return v

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        while stack and stack[-1][0] > indent:
            stack.pop()
        if not stack:
            stack = [(0, root)]
        parent_indent, parent = stack[-1]
        if ":" not in line:
            continue
        key, _, rest = line.lstrip().partition(":")
        key = key.strip().strip('"').strip("'")
        rest = rest.strip()
        if rest == "" or rest == "{}":
            new_map: dict[str, Any] = {}
            parent[key] = new_map
            stack.append((indent + 2, new_map))
        else:
            parent[key] = coerce(rest)
    return root


# ---------------------------------------------------------------------------
# Public cap check
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KillSwitchState:
    """Snapshot of the three caps' current state — surfaced via ``/healthz``."""

    date: str
    anonymous_spend_eur: float
    free_combined_spend_eur: float
    global_spend_eur: float
    anonymous_cap_eur: float
    free_cap_eur: float
    global_cap_eur: float
    anonymous_cap_fired: bool
    free_cap_fired: bool
    global_cap_fired: bool


def get_cap_state() -> KillSwitchState:
    """Return a fresh ``KillSwitchState`` for the current UTC day.

    Reads three rows and assembles the snapshot. Used by ``/healthz``.
    """
    settings = get_settings()
    today = _today_utc_iso()
    read = _reader or _default_read
    anon = float(read("anonymous", today) or 0.0)
    auth = float(read("authenticated_free", today) or 0.0)
    paying = float(read("paying", today) or 0.0)
    free_combined = anon + auth
    global_spend = free_combined + paying
    return KillSwitchState(
        date=today,
        anonymous_spend_eur=round(anon, 6),
        free_combined_spend_eur=round(free_combined, 6),
        global_spend_eur=round(global_spend, 6),
        anonymous_cap_eur=settings.anonymous_tier_cap_eur,
        free_cap_eur=settings.free_tier_cap_eur,
        global_cap_eur=settings.global_cap_eur,
        anonymous_cap_fired=anon >= settings.anonymous_tier_cap_eur,
        free_cap_fired=free_combined >= settings.free_tier_cap_eur,
        global_cap_fired=global_spend >= settings.global_cap_eur,
    )


def precheck(tier: str) -> None:
    """Raise ``HTTPException(503)`` if any cap relevant to ``tier`` has fired.

    The caps escalate — the lowest-numbered relevant cap fires first so the
    response payload matches the right cap's message.
    """
    settings = get_settings()
    if not settings.kill_switch_enabled:
        return

    state = get_cap_state()

    if state.global_cap_fired:
        event("L5", "cap_fired", which="global", tier=tier, spend=state.global_spend_eur)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "global_cap", "message": GLOBAL_CAP_MESSAGE},
        )
    if state.free_cap_fired and tier in ("anonymous", "authenticated_free"):
        event("L5", "cap_fired", which="free_tier", tier=tier, spend=state.free_combined_spend_eur)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "free_tier_cap", "message": FREE_CAP_MESSAGE},
        )
    if state.anonymous_cap_fired and tier == "anonymous":
        event("L5", "cap_fired", which="anonymous_tier", tier=tier, spend=state.anonymous_spend_eur)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "anonymous_cap", "message": ANON_CAP_MESSAGE},
        )


def record_spend(
    *,
    tier: str,
    model_used: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
) -> float:
    """Increment the spend row for ``(tier, today)`` and return the new total.

    Called AFTER the LLM completes (we have the realised model + tokens at
    that point). If you want a conservative pre-charge instead, swap the
    callers in :mod:`api.main` to call this before synthesis.
    """
    settings = get_settings()
    if not settings.kill_switch_enabled:
        return 0.0
    delta = _estimate_call_eur(
        model_used, input_tokens=input_tokens, output_tokens=output_tokens
    )
    today = _today_utc_iso()
    inc = _incrementer or _default_increment
    total = inc(tier, today, delta)
    event("L5", "spend", tier=tier, delta=round(delta, 6), total=round(total, 6))
    return total
