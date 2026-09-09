"""Mỗi thẻ xe phải nói một điều KHÁC nhau, không lặp lại cùng ba câu.

Sếp 2026-08-27: *"văn của LLM sinh ra cho các đối tượng khác giống nhau"*. Bản
pitch thật trên prod, hai xe cạnh nhau, giống tới từng chữ trừ cái tên:

    **VF 8 All New** thuộc đúng dòng xe Quý khách đang tìm, với tầm vận hành
    thoải mái cho quãng đường mỗi ngày và đủ chỗ cho số người Quý khách thường chở.
    **VF 7 All New** thuộc đúng dòng xe Quý khách đang tìm, với tầm vận hành
    thoải mái cho quãng đường mỗi ngày và đủ chỗ cho số người Quý khách thường chở.

Không phải lỗi prompt: `_CLAIM_TEXT_BY_SLOT` đánh khoá theo SLOT, nên hai xe cùng
thoả một bộ lý do thì nhận đúng một bộ câu.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.agents.domain.claim_policy import UNSTRUCTURED_CLAIM_PATTERN
from src.agents.domain.standout_facts import STANDOUT_PLACEHOLDER, standout_claims

VF8 = UUID("20000000-0000-0000-0000-000000000108")
VF7 = UUID("20000000-0000-0000-0000-000000000107")
VF3 = UUID("20000000-0000-0000-0000-000000000103")


@dataclass(frozen=True)
class _Fact:
    fact_code: str
    value_text: str


def test_each_vehicle_gets_the_axis_it_actually_wins() -> None:
    claims = standout_claims(
        {
            VF8: (_Fact("CAR_RANGE_KM", "400"), _Fact("CARGO_VOLUME_STANDARD_L", "376")),
            VF7: (_Fact("CAR_RANGE_KM", "440"), _Fact("CARGO_VOLUME_STANDARD_L", "537")),
        }
    )

    # VF 7 thắng quãng đường (luật đầu tiên) nên nhận câu đó; cốp lớn nhất cũng
    # là VF 7 nhưng mỗi xe chỉ một câu, và VF 8 không thắng gì nên không có câu.
    assert claims[VF7].text == "đi được xa nhất trong nhóm em vừa chọn"
    assert VF8 not in claims


def test_two_vehicles_do_not_receive_the_same_sentence() -> None:
    """Đúng bệnh đang chữa: hai thẻ cạnh nhau phải nói hai điều khác nhau."""

    claims = standout_claims(
        {
            VF8: (_Fact("CAR_RANGE_KM", "400"), _Fact("CARGO_VOLUME_STANDARD_L", "600")),
            VF7: (_Fact("CAR_RANGE_KM", "440"), _Fact("CARGO_VOLUME_STANDARD_L", "537")),
        }
    )

    assert claims[VF7].text != claims[VF8].text
    assert claims[VF7].text == "đi được xa nhất trong nhóm em vừa chọn"
    assert claims[VF8].text == "có khoang hành lý lớn nhất trong nhóm em vừa chọn"


def test_a_tie_awards_nobody() -> None:
    """Hai xe cùng 5 chỗ mà một chiếc xưng "nhiều nhất" là nói sai.

    Sai theo kiểu khách kiểm tra được ngay trên thẻ xe bên cạnh.
    """

    claims = standout_claims(
        {
            VF8: (_Fact("CAR_SEAT_COUNT", "5"),),
            VF7: (_Fact("CAR_SEAT_COUNT", "5"),),
        }
    )

    assert claims == {}


def test_a_missing_number_is_absent_not_zero() -> None:
    """Coi thiếu là 0 sẽ trao giải "sạc nhanh nhất" cho xe không có dữ liệu sạc."""

    claims = standout_claims(
        {
            VF8: (_Fact("FAST_CHARGE_TIME_MINUTES", "31"),),
            VF3: (_Fact("FAST_CHARGE_TIME_MINUTES", "24"),),
            # Không có dòng sạc nhanh nào. Coi thiếu là 0 thì chiếc này thắng.
            VF7: (_Fact("CAR_RANGE_KM", "440"),),
        }
    )

    assert VF7 not in claims
    assert claims[VF3].text == "sạc nhanh nhất trong nhóm em vừa chọn"


def test_a_single_vehicle_has_no_group_to_beat() -> None:
    """So sánh nhất giữa một mình là câu thật mà vô nghĩa — và nghe như tự khen."""

    assert standout_claims({VF8: (_Fact("CAR_RANGE_KM", "400"),)}) == {}


def test_the_lower_is_better_axis_picks_the_smallest_number() -> None:
    claims = standout_claims(
        {
            VF8: (_Fact("FAST_CHARGE_TIME_MINUTES", "31"),),
            VF3: (_Fact("FAST_CHARGE_TIME_MINUTES", "24"),),
        }
    )

    assert claims[VF3].text == "sạc nhanh nhất trong nhóm em vừa chọn"


def test_every_sentence_survives_the_synthesis_constraints() -> None:
    """Ba ràng buộc cứng của `services/synthesis` áp cho từng câu.

    Không chữ số, không gạch dưới/tên trường, không cụm tán dương mơ hồ. Một câu
    hỏng ở đây làm rớt CẢ pitch của xe thắng giải.
    """

    claims = standout_claims(
        {
            VF8: (_Fact("CAR_RANGE_KM", "400"), _Fact("CAR_MOTOR_POWER_KW", "300")),
            VF7: (_Fact("CAR_RANGE_KM", "440"), _Fact("CAR_MOTOR_POWER_KW", "260")),
            VF3: (_Fact("CAR_SEAT_COUNT", "4"), _Fact("CARGO_VOLUME_STANDARD_L", "285")),
        }
    )

    assert claims
    for claim in claims.values():
        assert claim.placeholder == STANDOUT_PLACEHOLDER
        assert not any(character.isdigit() for character in claim.text)
        assert "_" not in claim.text
        assert UNSTRUCTURED_CLAIM_PATTERN.search(claim.text) is None
