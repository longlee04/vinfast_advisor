"""Nhãn frontend phải phủ đúng enum backend (plan Customer 360 §2.7 — một nguồn định nghĩa).

Backend là nguồn DUY NHẤT; `frontend/.../customer360-labels.ts` chỉ phản chiếu. Test này đọc
file TS bằng regex và so khoá với enum Python — thêm giai đoạn/độ nóng/trường insight mà quên
nhãn thì đỏ ngay ở CI backend, không đợi TVV thấy "undefined".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.agents.domain.buyer_for import BuyerFor
from src.agents.domain.customer_insight import InsightField
from src.agents.domain.heat_score import HeatBand
from src.agents.domain.sales_stage import SalesStage

LABELS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "components" / "customer360" / "customer360-labels.ts"


def _keys(constant: str) -> set[str]:
    source = LABELS.read_text(encoding="utf-8")
    match = re.search(rf"export const {constant}\b[^=]*=\s*\{{(.*?)\n\}};", source, re.DOTALL)
    assert match, f"không tìm thấy {constant} trong {LABELS.name}"
    return set(re.findall(r"^\s*(\w+):", match.group(1), re.MULTILINE))


@pytest.mark.parametrize(
    ("constant", "enum"),
    [
        ("SALES_STAGE_LABELS", SalesStage),
        ("HEAT_BAND_BADGES", HeatBand),
        ("BUYER_FOR_LABELS", BuyerFor),
        ("INSIGHT_FIELD_LABELS", InsightField),
    ],
)
def test_nhan_frontend_khop_enum_backend(constant: str, enum: type) -> None:
    assert _keys(constant) == {member.value for member in enum}
