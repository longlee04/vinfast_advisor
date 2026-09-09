"""Sếp 2026-08-29: "anh đang quan tâm vf8" bị hỏi ngân sách/mục đích thay vì trả thông tin VF 8."""

from __future__ import annotations

import pytest

from src.agents.domain.intent_reconciliation import reconcile_intents
from src.agents.domain.values import Intent, SlotName


def _run(message: str, raw: list[Intent], known: dict | None = None, mentions: list[str] | None = None) -> list[Intent]:
    return reconcile_intents(
        user_message=message,
        raw_intents=raw,
        normalized_slots={},
        vehicle_mentions=["VF 8"] if mentions is None else mentions,
        known_slots=known or {},
    )


@pytest.mark.parametrize("message", ["anh đang quan tâm vf8", "em đang xem VF 8", "tôi cân nhắc vf 8"])
@pytest.mark.parametrize("raw", [[Intent.ADVISORY], []])
def test_chi_neu_xe_dang_quan_tam_la_tra_cuu(message: str, raw: list[Intent]) -> None:
    assert _run(message, raw) == [Intent.CATALOG_LOOKUP]


def test_co_nhu_cau_kem_theo_van_la_tu_van() -> None:
    assert Intent.ADVISORY in _run("tôi đang phân vân vf8 có hợp không, tư vấn giúp", [Intent.ADVISORY])


def test_dang_giua_cuoc_tu_van_thi_giu_tu_van() -> None:
    known = {SlotName.VEHICLE_TYPE: "CAR", SlotName.BUDGET_MAX_VND: 900_000_000}
    assert Intent.ADVISORY in _run("anh đang quan tâm vf8", [Intent.ADVISORY], known=known)


def test_khong_ten_xe_thi_khong_doi() -> None:
    assert Intent.CATALOG_LOOKUP not in _run("anh đang quan tâm xe điện", [Intent.ADVISORY], mentions=[])
