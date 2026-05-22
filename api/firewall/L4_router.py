"""L4 — circuit breaker around the Anthropic API.

The two-tier router itself lives in :mod:`api.orchestrator.synthesizer`. This
module wraps the Anthropic caller registered there with a circuit breaker so
that a sustained Anthropic outage doesn't pile retries on every request.

Behaviour:

* Track failure timestamps in a rolling window.
* After ``breaker_failure_threshold`` failures within
  ``breaker_failure_window_seconds`` (defaults: 5 in 60s), TRIP — for the
  next ``breaker_trip_cooldown_seconds`` (default: 5 min) the synthesiser
  short-circuits to Cortex ``mistral-large2`` instead of calling Anthropic.
* Every trip + every recovery is logged via :mod:`._log`.

The breaker is installed by :func:`install` which wraps the existing
synthesiser seam. Toggle: ``CIRCUIT_BREAKER_ENABLED=true``.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, Deque

from ._log import event
from .settings import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class _BreakerState:
    failures: Deque[float] = field(default_factory=deque)
    tripped_until: float = 0.0  # unix ts; 0 means closed
    last_trip_at: float = 0.0
    last_recovery_at: float = 0.0


_state = _BreakerState()
_lock = Lock()


def reset() -> None:
    """Reset breaker state. Used by tests."""
    global _state
    with _lock:
        _state = _BreakerState()


def is_open() -> bool:
    """Is the breaker currently routing-away from Anthropic?"""
    with _lock:
        if _state.tripped_until == 0.0:
            return False
        if time.time() >= _state.tripped_until:
            # Cooldown elapsed — close the breaker.
            _state.tripped_until = 0.0
            _state.last_recovery_at = time.time()
            event("L4", "recover")
            return False
        return True


def record_failure() -> None:
    """Log an Anthropic failure; may trip the breaker."""
    settings = get_settings()
    now = time.time()
    with _lock:
        window = settings.breaker_failure_window_seconds
        threshold = settings.breaker_failure_threshold
        _state.failures.append(now)
        while _state.failures and _state.failures[0] < now - window:
            _state.failures.popleft()
        if len(_state.failures) >= threshold and _state.tripped_until == 0.0:
            _state.tripped_until = now + settings.breaker_trip_cooldown_seconds
            _state.last_trip_at = now
            event(
                "L4",
                "trip",
                failures=len(_state.failures),
                cooldown_seconds=settings.breaker_trip_cooldown_seconds,
            )


def record_success() -> None:
    """Best-effort: a successful Anthropic call clears the failure deque."""
    with _lock:
        _state.failures.clear()


# ---------------------------------------------------------------------------
# Install — wrap the synthesiser's Anthropic seam
# ---------------------------------------------------------------------------


def install() -> None:
    """Replace ``synthesizer._anthropic_caller`` with a breaker-wrapped version.

    The wrapper:
    * If the breaker is open, raises ``BreakerOpen`` to force the synthesiser
      down its fallback path (Cortex mistral-large2).
    * If closed, calls the underlying caller; success clears the failure
      deque, failure records one.

    Idempotent — calling :func:`install` twice does not double-wrap.
    """
    settings = get_settings()
    if not settings.breaker_enabled:
        return

    from ..orchestrator import synthesizer

    # Already wrapped?
    if getattr(synthesizer._anthropic_caller, "_l4_wrapped", False):  # type: ignore[union-attr]
        return

    inner: Callable[[str, str], str] = (
        synthesizer._anthropic_caller or synthesizer._default_anthropic_caller
    )

    def wrapped(system_prompt: str, user_prompt: str) -> str:
        if is_open():
            event("L4", "shortcircuit")
            raise BreakerOpen("Anthropic breaker open")
        try:
            ans = inner(system_prompt, user_prompt)
        except Exception:
            record_failure()
            raise
        record_success()
        return ans

    wrapped._l4_wrapped = True  # type: ignore[attr-defined]
    synthesizer.set_anthropic_caller(wrapped)


class BreakerOpen(Exception):
    """Raised by the wrapped caller when the breaker is open."""
