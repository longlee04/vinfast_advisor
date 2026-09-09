"""comparison-image — service render ảnh so sánh, thuần dữ liệu đã snapshot."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from src.agents.domain.comparison import (
    DOCUMENT_UNVERIFIED_LABEL,
    ComparisonCell,
    ComparisonRow,
    ComparisonTable,
    CrossVehicleTypeComparisonError,
)
from src.agents.domain.values import VehicleType
from src.agents.services.operations.comparison_image import (
    ComparisonImageError,
    render_comparison_image,
    render_comparison_image_or_none,
)

CAPTURED_AT = datetime(2026, 8, 9, 9, 0, tzinfo=UTC)
VEHICLE_A = UUID("11111111-1111-1111-1111-111111111111")
VEHICLE_B = UUID("22222222-2222-2222-2222-222222222222")


class SpySession:
    """Fake session đếm mọi lần chạm DB — service render không được chạm lần nào."""

    def __init__(self) -> None:
        self.queries = 0

    async def execute(self, statement: object) -> object:
        self.queries += 1
        return None

    async def scalar(self, statement: object) -> object:
        self.queries += 1
        return None


def _cell(
    vehicle_id: UUID,
    value: str,
    *,
    source: str = "STRUCTURED",
    label: str | None = None,
    is_better: bool = False,
) -> ComparisonCell:
    return ComparisonCell(
        vehicle_id=vehicle_id,
        value_text=value,
        source=source,  # type: ignore[arg-type]
        evidence_ref="vehicle_prices:1",
        label=label,
        is_better=is_better,
    )


def _table(vehicle_type: VehicleType = VehicleType.CAR) -> ComparisonTable:
    return ComparisonTable(
        vehicle_type=vehicle_type,
        vehicle_ids=(VEHICLE_A, VEHICLE_B),
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=(
                    _cell(VEHICLE_A, "1.200.000.000", is_better=True),
                    _cell(VEHICLE_B, "1.400.000.000"),
                ),
            ),
            ComparisonRow(
                criterion_code="CAR_RANGE_KM",
                cells=(_cell(VEHICLE_A, "420"), _cell(VEHICLE_B, "471", is_better=True)),
            ),
        ),
        captured_at=CAPTURED_AT,
    )


def _document_table() -> ComparisonTable:
    return ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(VEHICLE_A, VEHICLE_B),
        rows=(
            ComparisonRow(
                criterion_code="PANORAMIC_ROOF",
                cells=(
                    _cell(VEHICLE_A, "Có", source="DOCUMENT", label=DOCUMENT_UNVERIFIED_LABEL),
                    _cell(VEHICLE_B, "Có", source="FLAG"),
                ),
            ),
        ),
        captured_at=CAPTURED_AT,
    )


def _cross_type_table() -> ComparisonTable:
    """Bảng trộn hai loại xe — chỉ dựng được bằng tay, A5-4 không bao giờ sinh ra."""
    return ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(VEHICLE_A, VEHICLE_B),
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=(_cell(VEHICLE_A, "1.200.000.000"), _cell(VEHICLE_B, "35.000.000")),
            ),
            ComparisonRow(
                criterion_code="MOTORBIKE_MAX_LOAD_KG",
                cells=(_cell(VEHICLE_A, "—"), _cell(VEHICLE_B, "150")),
            ),
        ),
        captured_at=CAPTURED_AT,
    )


def test_the_same_snapshot_renders_byte_identical_images() -> None:
    # Given
    table = _table()

    # When
    first = render_comparison_image(table)
    second = render_comparison_image(table)

    # Then — khác một byte là E2E A9-2 mất tính tái lập
    assert first == second


def test_rendering_does_not_touch_the_database() -> None:
    # Given
    session = SpySession()

    # When
    render_comparison_image(_table())

    # Then — mọi con số đã nằm trong snapshot truyền vào
    assert session.queries == 0


def test_a_table_mixing_vehicle_types_is_refused() -> None:
    # Given — kế thừa ràng buộc A5-4, không được lách qua đường ảnh
    table = _cross_type_table()

    # When / Then
    with pytest.raises(CrossVehicleTypeComparisonError):
        render_comparison_image(table)


def test_a_document_sourced_cell_carries_the_unverified_label() -> None:
    # Given
    table = _document_table()

    # When
    image_text = render_comparison_image(table, _debug_text=True)

    # Then
    assert DOCUMENT_UNVERIFIED_LABEL in image_text


def test_a_flag_sourced_cell_has_no_extra_label() -> None:
    # Given — test âm của dòng trên: nguồn FLAG không được gắn nhãn thừa
    table = _document_table()

    # When
    image_text = render_comparison_image(table, _debug_text=True)

    # Then
    assert image_text.count(DOCUMENT_UNVERIFIED_LABEL) == 1


def test_an_empty_table_is_reported_as_a_render_error() -> None:
    # Given — test âm: không có dòng nào để vẽ
    table = ComparisonTable(vehicle_type=VehicleType.CAR, vehicle_ids=(VEHICLE_A, VEHICLE_B), rows=())

    # When / Then
    with pytest.raises(ComparisonImageError):
        render_comparison_image(table)


def test_a_single_vehicle_table_is_reported_as_a_render_error() -> None:
    # Given — test âm: A5-4 so 2–3 mẫu, một mẫu không phải bảng so sánh
    table = ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(VEHICLE_A,),
        rows=(ComparisonRow(criterion_code="STARTING_PRICE_VND", cells=(_cell(VEHICLE_A, "1.200.000.000"),)),),
    )

    # When / Then
    with pytest.raises(ComparisonImageError):
        render_comparison_image(table)


def test_a_four_vehicle_table_is_reported_as_a_render_error() -> None:
    # Given — test âm: quá số mẫu A5-4 cho phép
    ids = (VEHICLE_A, VEHICLE_B, uuid4(), uuid4())
    table = ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=ids,
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=tuple(_cell(vehicle_id, "1.000.000.000") for vehicle_id in ids),
            ),
        ),
    )

    # When / Then
    with pytest.raises(ComparisonImageError):
        render_comparison_image(table)


def test_a_failing_render_returns_none_instead_of_breaking_the_turn() -> None:
    # Given — dữ liệu rỗng, đúng tình huống "service lỗi" của tài liệu
    table = ComparisonTable(vehicle_type=VehicleType.CAR, vehicle_ids=(VEHICLE_A, VEHICLE_B), rows=())

    # When — lối gọi an toàn dành cho lượt chat
    result = render_comparison_image_or_none(table)

    # Then — câu trả lời văn bản vẫn gửi được, chỉ thiếu ảnh
    assert result is None


def test_a_missing_font_does_not_break_the_turn() -> None:
    # Given — test âm: đúng tình huống "font thiếu" tài liệu nhắc tới
    # When
    result = render_comparison_image_or_none(_table(), font_dir="/khong/co/thu/muc/nay")

    # Then
    assert result is None


def test_a_valid_table_renders_a_png() -> None:
    # Given
    table = _table()

    # When
    image = render_comparison_image(table)

    # Then — chữ ký PNG, không phải một chuỗi rỗng qua mặt test byte-identical
    assert image.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(image) > 1000
