"""Cost firewall package — Agent 10.

Six concentric layers wrapping the ``/query`` endpoint, in execution order:

* :mod:`api.firewall.L1_turnstile`     — Cloudflare bot-check (anonymous tier).
* :mod:`api.firewall.L2_rate_limit`    — per-IP + per-/24 + anti-spam.
* :mod:`api.firewall.L3_semantic_cache` — between retrieval and synthesis.
* :mod:`api.firewall.L4_router`        — circuit breaker around Anthropic.
* :mod:`api.firewall.L5_kill_switch`   — three nested daily-spend caps.
* :mod:`api.firewall.L6_tracing`       — Langfuse spans for every request.

Every layer is independently togglable via an env var documented in
:mod:`api.firewall.settings`. With every flag disabled the firewall becomes a
zero-cost pass-through and the existing Agent 09 contract is unchanged.

The ``cap_state`` shape exposed under ``/healthz`` is defined in
:mod:`api.firewall.L5_kill_switch` and re-exported here.
"""
from __future__ import annotations

from .L5_kill_switch import KillSwitchState, get_cap_state
from .settings import FirewallSettings, get_settings

__all__ = [
    "FirewallSettings",
    "KillSwitchState",
    "get_cap_state",
    "get_settings",
]
