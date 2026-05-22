"""Centralised firewall settings — every layer reads here, nobody else parses env.

Each layer is independently togglable. The defaults below mirror the design
in ADR-002 (six-layer cost firewall) and the 2026-05-21 revisions documented
in ``firewall/spend_cap_rationale.md`` and ``firewall/anti_spam_decisions.md``.
"""
from __future__ import annotations

import functools
import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class FirewallSettings:
    """Pure-data settings snapshot.

    A new snapshot is built lazily on first call to :func:`get_settings` and
    cached. Tests that want a different snapshot call :func:`reload_settings`
    after mutating ``os.environ``.
    """

    # ---- L1 ----
    turnstile_enabled: bool
    turnstile_secret_key: str | None
    turnstile_verify_url: str
    turnstile_cache_ttl_seconds: int

    # ---- L2 ----
    rate_limit_enabled: bool
    rate_limit_anon_per_minute: int
    rate_limit_anon_per_day: int
    rate_limit_auth_per_minute: int
    rate_limit_auth_per_day: int
    rate_limit_paying_per_minute: int
    rate_limit_subnet_per_hour: int
    rate_limit_subnet_per_day: int
    rate_limit_subnet_flag_threshold: int  # cap-breaches in 24h to mark flagged
    rate_limit_flagged_subnet_ttl_seconds: int  # 7 days by default
    dwell_min_ms: int

    # ---- L3 ----
    cache_enabled: bool
    cache_ttl_seconds: int  # 30 days
    cache_table_fqn: str

    # ---- L4 ----
    breaker_enabled: bool
    breaker_failure_threshold: int  # 5 failures
    breaker_failure_window_seconds: int  # in 60s
    breaker_trip_cooldown_seconds: int  # 5 min

    # ---- L5 ----
    kill_switch_enabled: bool
    anonymous_tier_cap_eur: float  # 0.50
    free_tier_cap_eur: float  # 2.00
    global_cap_eur: float  # 5.00
    spend_table_fqn: str
    pricing_file_path: str | None

    # ---- L6 ----
    langfuse_enabled: bool
    langfuse_public_key: str | None
    langfuse_secret_key: str | None
    langfuse_host: str | None


def _build_from_env() -> FirewallSettings:
    here = os.path.dirname(os.path.abspath(__file__))
    return FirewallSettings(
        turnstile_enabled=_env_bool("TURNSTILE_ENABLED", default=False),
        turnstile_secret_key=os.environ.get("TURNSTILE_SECRET_KEY"),
        turnstile_verify_url=os.environ.get(
            "TURNSTILE_VERIFY_URL",
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        ),
        turnstile_cache_ttl_seconds=_env_int("TURNSTILE_CACHE_TTL_SECONDS", 300),
        rate_limit_enabled=_env_bool("RATE_LIMIT_ENABLED", default=False),
        rate_limit_anon_per_minute=_env_int("RATE_LIMIT_ANON_PER_MINUTE", 1),
        rate_limit_anon_per_day=_env_int("RATE_LIMIT_ANON_PER_DAY", 2),
        rate_limit_auth_per_minute=_env_int("RATE_LIMIT_AUTH_PER_MINUTE", 5),
        rate_limit_auth_per_day=_env_int("RATE_LIMIT_AUTH_PER_DAY", 30),
        rate_limit_paying_per_minute=_env_int("RATE_LIMIT_PAYING_PER_MINUTE", 60),
        rate_limit_subnet_per_hour=_env_int("RATE_LIMIT_SUBNET_PER_HOUR", 12),
        rate_limit_subnet_per_day=_env_int("RATE_LIMIT_SUBNET_PER_DAY", 30),
        rate_limit_subnet_flag_threshold=_env_int(
            "RATE_LIMIT_SUBNET_FLAG_THRESHOLD", 3
        ),
        rate_limit_flagged_subnet_ttl_seconds=_env_int(
            "RATE_LIMIT_FLAGGED_SUBNET_TTL_SECONDS", 7 * 24 * 60 * 60
        ),
        dwell_min_ms=_env_int("FIREWALL_DWELL_MIN_MS", 1500),
        cache_enabled=_env_bool("SEMANTIC_CACHE_ENABLED", default=False),
        cache_ttl_seconds=_env_int("SEMANTIC_CACHE_TTL_SECONDS", 30 * 24 * 60 * 60),
        cache_table_fqn=os.environ.get(
            "SEMANTIC_CACHE_TABLE_FQN", "GKTUITION_TUTOR.CORTEX.QUERY_CACHE"
        ),
        breaker_enabled=_env_bool("CIRCUIT_BREAKER_ENABLED", default=False),
        breaker_failure_threshold=_env_int("CIRCUIT_BREAKER_FAILURE_THRESHOLD", 5),
        breaker_failure_window_seconds=_env_int(
            "CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS", 60
        ),
        breaker_trip_cooldown_seconds=_env_int(
            "CIRCUIT_BREAKER_TRIP_COOLDOWN_SECONDS", 5 * 60
        ),
        kill_switch_enabled=_env_bool("KILL_SWITCH_ENABLED", default=False),
        anonymous_tier_cap_eur=_env_float("KILL_SWITCH_ANON_CAP_EUR", 0.50),
        free_tier_cap_eur=_env_float("KILL_SWITCH_FREE_CAP_EUR", 2.00),
        global_cap_eur=_env_float("KILL_SWITCH_GLOBAL_CAP_EUR", 5.00),
        spend_table_fqn=os.environ.get(
            "KILL_SWITCH_SPEND_TABLE_FQN", "GKTUITION_TUTOR.RAW.DAILY_SPEND"
        ),
        pricing_file_path=os.environ.get(
            "ANTHROPIC_PRICING_FILE",
            os.path.join(here, "anthropic_pricing.yaml"),
        ),
        langfuse_enabled=_env_bool("LANGFUSE_ENABLED", default=False),
        langfuse_public_key=os.environ.get("LANGFUSE_PUBLIC_KEY"),
        langfuse_secret_key=os.environ.get("LANGFUSE_SECRET_KEY"),
        langfuse_host=os.environ.get("LANGFUSE_HOST"),
    )


@functools.lru_cache(maxsize=1)
def get_settings() -> FirewallSettings:
    """Cached settings snapshot. Call :func:`reload_settings` to refresh."""
    return _build_from_env()


def reload_settings() -> FirewallSettings:
    """Force a re-read of env vars. Used by tests."""
    get_settings.cache_clear()
    return get_settings()
