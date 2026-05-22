"""L4 — circuit breaker tests."""
from __future__ import annotations

import time
from typing import Any

import pytest

from api.firewall import L4_router


def test_breaker_starts_closed(firewall_env: Any) -> None:
    firewall_env(CIRCUIT_BREAKER_ENABLED="true")
    assert L4_router.is_open() is False


def test_breaker_trips_after_threshold_failures(firewall_env: Any) -> None:
    firewall_env(
        CIRCUIT_BREAKER_ENABLED="true",
        CIRCUIT_BREAKER_FAILURE_THRESHOLD="5",
        CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS="60",
        CIRCUIT_BREAKER_TRIP_COOLDOWN_SECONDS="60",
    )
    for _ in range(4):
        L4_router.record_failure()
        assert L4_router.is_open() is False
    L4_router.record_failure()
    assert L4_router.is_open() is True


def test_breaker_does_not_trip_on_isolated_failures(firewall_env: Any) -> None:
    """Failures spread out over > window do not trip the breaker."""
    firewall_env(
        CIRCUIT_BREAKER_ENABLED="true",
        CIRCUIT_BREAKER_FAILURE_THRESHOLD="3",
        CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS="1",
    )
    L4_router.record_failure()
    time.sleep(1.2)
    L4_router.record_failure()
    time.sleep(1.2)
    L4_router.record_failure()
    # The window is 1s — the first two failures are out of band.
    assert L4_router.is_open() is False


def test_breaker_recovers_after_cooldown(firewall_env: Any) -> None:
    firewall_env(
        CIRCUIT_BREAKER_ENABLED="true",
        CIRCUIT_BREAKER_FAILURE_THRESHOLD="2",
        CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS="60",
        CIRCUIT_BREAKER_TRIP_COOLDOWN_SECONDS="1",
    )
    L4_router.record_failure()
    L4_router.record_failure()
    assert L4_router.is_open() is True
    time.sleep(1.1)
    assert L4_router.is_open() is False


def test_breaker_success_clears_failures(firewall_env: Any) -> None:
    firewall_env(
        CIRCUIT_BREAKER_ENABLED="true",
        CIRCUIT_BREAKER_FAILURE_THRESHOLD="3",
        CIRCUIT_BREAKER_FAILURE_WINDOW_SECONDS="60",
    )
    L4_router.record_failure()
    L4_router.record_failure()
    L4_router.record_success()  # clears the failure deque
    L4_router.record_failure()
    L4_router.record_failure()
    assert L4_router.is_open() is False


def test_install_wraps_anthropic_caller_idempotently(firewall_env: Any) -> None:
    """Calling install() twice does not double-wrap the seam."""
    firewall_env(CIRCUIT_BREAKER_ENABLED="true")
    from api.orchestrator import synthesizer

    def base(sysp: str, userp: str) -> str:
        return "OK"

    synthesizer.set_anthropic_caller(base)
    L4_router.install()
    wrapped_once = synthesizer._anthropic_caller
    L4_router.install()
    wrapped_twice = synthesizer._anthropic_caller
    assert wrapped_once is wrapped_twice
    # The wrapped caller still works.
    assert wrapped_twice("s", "u") == "OK"  # type: ignore[misc]
    synthesizer.set_anthropic_caller(None)


def test_wrapped_caller_raises_breakeropen_when_tripped(firewall_env: Any) -> None:
    firewall_env(
        CIRCUIT_BREAKER_ENABLED="true",
        CIRCUIT_BREAKER_FAILURE_THRESHOLD="1",
        CIRCUIT_BREAKER_TRIP_COOLDOWN_SECONDS="60",
    )
    from api.orchestrator import synthesizer

    def failing(sysp: str, userp: str) -> str:
        raise RuntimeError("anthropic down")

    synthesizer.set_anthropic_caller(failing)
    L4_router.install()

    # First call: caller raises, breaker trips.
    with pytest.raises(RuntimeError):
        synthesizer._anthropic_caller("s", "u")  # type: ignore[misc]
    # Second call: breaker is open, the wrapper raises BreakerOpen.
    with pytest.raises(L4_router.BreakerOpen):
        synthesizer._anthropic_caller("s", "u")  # type: ignore[misc]
    synthesizer.set_anthropic_caller(None)


def test_disabled_install_is_noop(firewall_env: Any) -> None:
    """``install()`` with the breaker disabled doesn't wrap anything."""
    from api.orchestrator import synthesizer

    def base(sysp: str, userp: str) -> str:
        return "OK"

    synthesizer.set_anthropic_caller(base)
    L4_router.install()
    # The seam should still be the original — no wrapping.
    assert synthesizer._anthropic_caller is base
    synthesizer.set_anthropic_caller(None)
