"""Dai anh xe tren dau bang so sanh — thang cot, thieu anh thi co o giu cho."""

from __future__ import annotations

import io
from datetime import UTC, datetime
from uuid import UUID

from PIL import Image

from src.agents.domain.comparison import ComparisonCell, ComparisonRow, ComparisonTable
from src.agents.domain.values import VehicleType
from src.agents.services.operations.comparison_image import (
    PHOTO_HEIGHT,
    PHOTO_STRIP_HEIGHT,
    PHOTO_WIDTH,
    render_comparison_image,
)

VEHICLE_A = UUID("11111111-1111-1111-1111-111111111111")
VEHICLE_B = UUID("22222222-2222-2222-2222-222222222222")


def _photo(colour: tuple[int, int, int], size: tuple[int, int] = (PHOTO_WIDTH, PHOTO_HEIGHT)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, colour).save(buffer, format="PNG")
    return buffer.getvalue()


def _comparison_table_two_cars() -> ComparisonTable:
    def cell(vehicle_id: UUID, value: str) -> ComparisonCell:
        return ComparisonCell(
            vehicle_id=vehicle_id,
            value_text=value,
            source="STRUCTURED",
            evidence_ref="vehicle_prices:1",
            label=None,
        )

    return ComparisonTable(
        vehicle_type=VehicleType.CAR,
        vehicle_ids=(VEHICLE_A, VEHICLE_B),
        vehicle_names=("VF 8 Eco", "VF 9 Plus"),
        rows=(
            ComparisonRow(
                criterion_code="STARTING_PRICE_VND",
                cells=(cell(VEHICLE_A, "1.200.000.000"), cell(VEHICLE_B, "1.400.000.000")),
            ),
        ),
        captured_at=datetime(2026, 8, 9, 9, 0, tzinfo=UTC),
    )


def test_photo_strip_makes_the_canvas_taller() -> None:
    table = _comparison_table_two_cars()

    without = render_comparison_image(table)
    with_photos = render_comparison_image(table, photos={VEHICLE_A: _photo((200, 30, 30))})

    assert Image.open(io.BytesIO(with_photos)).height == (Image.open(io.BytesIO(without)).height + PHOTO_STRIP_HEIGHT)


def test_missing_photo_renders_a_named_placeholder() -> None:
    image_text = render_comparison_image(_comparison_table_two_cars(), photos={}, _debug_text=True)

    assert "Chưa có ảnh: VF 8 Eco" in image_text
    assert "Chưa có ảnh: VF 9 Plus" in image_text


def test_valid_photo_is_pasted_at_the_planned_column_coordinates() -> None:
    table = _comparison_table_two_cars()
    payload = _photo((200, 30, 30))

    image = Image.open(io.BytesIO(render_comparison_image(table, photos={VEHICLE_A: payload})))

    assert image.getpixel((293, 68)) == (200, 30, 30)
    assert image.getpixel((484, 175)) == (200, 30, 30)
    assert image.getpixel((292, 68)) == (255, 255, 255)


def test_rendering_twice_is_byte_identical() -> None:
    photos = {VEHICLE_A: _photo((10, 90, 200))}
    table = _comparison_table_two_cars()

    first = render_comparison_image(table, photos=photos)
    second = render_comparison_image(table, photos=photos)

    assert first == second


def test_invalid_photo_size_renders_placeholder_and_logs(caplog) -> None:
    table = _comparison_table_two_cars()

    with caplog.at_level("WARNING", logger="agent.services.comparison_image"):
        image_text = render_comparison_image(
            table,
            photos={VEHICLE_A: _photo((10, 90, 200), size=(PHOTO_WIDTH + 1, PHOTO_HEIGHT))},
            _debug_text=True,
        )

    assert "Chưa có ảnh: VF 8 Eco" in image_text
    assert "Chưa có ảnh: VF 9 Plus" in image_text
    assert "invalid vehicle photo" in caplog.text


def test_invalid_photo_payload_does_not_crash_and_logs(caplog) -> None:
    with caplog.at_level("WARNING", logger="agent.services.comparison_image"):
        image_text = render_comparison_image(
            _comparison_table_two_cars(), photos={VEHICLE_A: b"not-an-image"}, _debug_text=True
        )

    assert "Chưa có ảnh: VF 8 Eco" in image_text
    assert "Chưa có ảnh: VF 9 Plus" in image_text
    assert "invalid vehicle photo" in caplog.text
