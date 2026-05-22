"""L5 — three nested kill-switch caps."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from api.firewall import L5_kill_switch as L5


def _today() -> str:
    return L5._today_utc_iso()


def test_no_caps_fire_when_empty(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    L5.precheck("anonymous")
    L5.precheck("authenticated_free")
    L5.precheck("paying")


def test_anonymous_cap_fires_only_for_anonymous(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 0.49)
    # 0.49 < 0.50 → still below the cap.
    L5.precheck("anonymous")
    L5.seed_memory_state("anonymous", today, 0.50)
    with pytest.raises(HTTPException) as exc:
        L5.precheck("anonymous")
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "anonymous_cap"
    # But authenticated_free + paying are unaffected.
    L5.precheck("authenticated_free")
    L5.precheck("paying")


def test_free_cap_blocks_anon_and_auth(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 1.00)
    L5.seed_memory_state("authenticated_free", today, 1.10)
    # Combined free spend is 2.10 → > €2.00 cap.
    with pytest.raises(HTTPException) as exc:
        L5.precheck("anonymous")
    assert exc.value.detail["error"] == "free_tier_cap"
    with pytest.raises(HTTPException) as exc:
        L5.precheck("authenticated_free")
    assert exc.value.detail["error"] == "free_tier_cap"
    # Paying continues.
    L5.precheck("paying")


def test_global_cap_blocks_everyone(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 1.5)
    L5.seed_memory_state("authenticated_free", today, 1.5)
    L5.seed_memory_state("paying", today, 2.5)
    # Global combined is 5.5 → > €5.00.
    for tier in ("anonymous", "authenticated_free", "paying"):
        with pytest.raises(HTTPException) as exc:
            L5.precheck(tier)
        assert exc.value.detail["error"] == "global_cap"


def test_get_cap_state_shape(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 0.20)
    L5.seed_memory_state("authenticated_free", today, 0.30)
    state = L5.get_cap_state()
    assert state.anonymous_spend_eur == 0.20
    assert state.free_combined_spend_eur == 0.50
    assert state.global_spend_eur == 0.50
    assert state.anonymous_cap_fired is False
    assert state.free_cap_fired is False
    assert state.global_cap_fired is False


def test_record_spend_increments(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    new = L5.record_spend(
        tier="anonymous",
        model_used="anthropic.claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=500,
    )
    # input: 1000/1M * $1.0 = $0.001; output: 500/1M * $5.0 = $0.0025;
    # total $0.0035 * 0.92 ≈ €0.00322.
    assert 0.003 < new < 0.0045


def test_disabled_record_spend_is_noop(firewall_env: Any) -> None:
    new = L5.record_spend(
        tier="anonymous",
        model_used="anthropic.claude-haiku-4-5",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert new == 0.0


def test_midnight_reset_isolates_days(firewall_env: Any) -> None:
    """Spend recorded against a different date does not affect today's caps."""
    firewall_env(KILL_SWITCH_ENABLED="true")
    # Seed yesterday with maxed-out spend.
    L5.seed_memory_state("anonymous", "1999-01-01", 99.0)
    L5.seed_memory_state("authenticated_free", "1999-01-01", 99.0)
    L5.seed_memory_state("paying", "1999-01-01", 99.0)
    # Today's row remains empty; precheck passes.
    L5.precheck("anonymous")
    L5.precheck("authenticated_free")
    L5.precheck("paying")


def test_dry_run_scenario_a_anonymous_cap(firewall_env: Any) -> None:
    """Verification scenario (a): anonymous_tier_cap at €0.49 + one query."""
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 0.49)
    # Simulate one more anonymous query landing — record a Haiku-class call.
    # Use a token count large enough to push us over the €0.50 cap.
    # Haiku: $1/M input, $5/M output, ~€0.92/$1. ~2,500/2,500 tokens ≈ €0.013.
    new = L5.record_spend(
        tier="anonymous",
        model_used="anthropic.claude-haiku-4-5",
        input_tokens=2_500,
        output_tokens=2_500,
    )
    assert new >= 0.50
    with pytest.raises(HTTPException) as exc:
        L5.precheck("anonymous")
    assert exc.value.detail["error"] == "anonymous_cap"
    # Authenticated_free and paying still succeed.
    L5.precheck("authenticated_free")
    L5.precheck("paying")


def test_dry_run_scenario_b_free_cap(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("anonymous", today, 0.0)
    L5.seed_memory_state("authenticated_free", today, 1.99)
    L5.record_spend(
        tier="authenticated_free",
        model_used="anthropic.claude-haiku-4-5",
        input_tokens=2_500,
        output_tokens=2_500,
    )
    for t in ("anonymous", "authenticated_free"):
        with pytest.raises(HTTPException) as exc:
            L5.precheck(t)
        assert exc.value.detail["error"] in {"free_tier_cap", "global_cap"}
    L5.precheck("paying")


def test_dry_run_scenario_c_global_cap(firewall_env: Any) -> None:
    firewall_env(KILL_SWITCH_ENABLED="true")
    today = _today()
    L5.seed_memory_state("paying", today, 4.99)
    L5.record_spend(
        tier="paying",
        model_used="anthropic.claude-haiku-4-5",
        input_tokens=2_500,
        output_tokens=2_500,
    )
    for t in ("anonymous", "authenticated_free", "paying"):
        with pytest.raises(HTTPException) as exc:
            L5.precheck(t)
        assert exc.value.detail["error"] == "global_cap"
