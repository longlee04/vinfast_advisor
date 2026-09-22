"""`domain/agent_flag`: luật bật/tắt thuần cho đường agent (plan Bước 3)."""

from __future__ import annotations

import pytest

from src.agents.domain.agent_flag import (
    FLAG_AGENT_FALLBACK,
    AgentFlagState,
    is_enabled_for,
    parse_allowlist,
    rollout_bucket,
)


def _flag(**kw: object) -> AgentFlagState:
    base: dict[str, object] = {"name": FLAG_AGENT_FALLBACK, "enabled": True}
    base.update(kw)
    return AgentFlagState(**base)  # type: ignore[arg-type]


def test_allowlist_thang_rollout() -> None:
    flag = _flag(rollout_percent=0, customer_allowlist=frozenset({"c-vip"}))
    assert is_enabled_for(flag, "c-vip") is True
    assert is_enabled_for(flag, "c-khac") is False


def test_rollout_percent_tat_dinh_cung_khach_cung_nhanh() -> None:
    flag = _flag(rollout_percent=50)
    first = is_enabled_for(flag, "customer-42")
    assert all(is_enabled_for(flag, "customer-42") is first for _ in range(100))
    # Và phần trăm có nghĩa thật: 0 → không ai, 100 → mọi người.
    assert not any(is_enabled_for(_flag(rollout_percent=0), f"c{i}") for i in range(200))
    assert all(is_enabled_for(_flag(rollout_percent=100), f"c{i}") for i in range(200))
    # Ở 50%, phần chia gần đều (băm sha256, 400 khách → trong khoảng 35..65%).
    share = sum(is_enabled_for(flag, f"customer-{i}") for i in range(400)) / 400
    assert 0.35 <= share <= 0.65


def test_kill_switch_thang_tat_ca() -> None:
    flag = _flag(rollout_percent=100, customer_allowlist=frozenset({"c-vip"}))
    assert is_enabled_for(flag, "c-vip", kill_switch=True) is False
    assert is_enabled_for(flag, "c-bat-ky", kill_switch=True) is False


def test_flag_none_thi_tat() -> None:
    assert is_enabled_for(None, "c-vip") is False
    assert is_enabled_for(None, "c-vip", kill_switch=False) is False


def test_enabled_false_thi_tat_du_allowlist_co_ten() -> None:
    flag = _flag(enabled=False, rollout_percent=100, customer_allowlist=frozenset({"c-vip"}))
    assert is_enabled_for(flag, "c-vip") is False


def test_customer_id_rong_thi_tat() -> None:
    assert is_enabled_for(_flag(rollout_percent=100), "") is False
    assert is_enabled_for(_flag(rollout_percent=100), "   ") is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("", frozenset()), (None, frozenset()), ("a, b,,c ", frozenset({"a", "b", "c"})), (" x ", frozenset({"x"}))],
)
def test_parse_allowlist(raw: str | None, expected: frozenset[str]) -> None:
    assert parse_allowlist(raw) == expected


def test_rollout_bucket_trong_0_99_va_khac_nhau_theo_ten_co() -> None:
    buckets = {rollout_bucket(FLAG_AGENT_FALLBACK, f"c{i}") for i in range(500)}
    assert buckets <= set(range(100)) and len(buckets) > 50
    assert rollout_bucket("co_a", "c1") == rollout_bucket("co_a", "c1")
