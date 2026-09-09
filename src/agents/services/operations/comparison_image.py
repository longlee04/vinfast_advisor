"""Vẽ `ComparisonTable` đã đóng băng thành PNG byte-identical với dải ảnh xe."""

from __future__ import annotations

import io
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Final
from uuid import UUID

from src.agents.domain.comparison import (
    ComparisonRow,
    ComparisonTable,
    CrossVehicleTypeComparisonError,
)
from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger

try:
    from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    UnidentifiedImageError = OSError

#: Font đóng gói trong repo — xem lý do ở docstring module.
DEFAULT_FONT_DIR: Final = Path(__file__).resolve().parents[2] / "assets" / "fonts"
REGULAR_FONT_NAME: Final = "DejaVuSans.ttf"
BOLD_FONT_NAME: Final = "DejaVuSans-Bold.ttf"

#: A5-4 so sánh 2–3 mẫu; ảnh kế thừa đúng giới hạn đó.
MIN_VEHICLES: Final = 2
MAX_VEHICLES: Final = 3

#: Tiêu chí nào thuộc loại xe nào — dùng để bắt bảng trộn hai loại xe.
CAR_ONLY_CRITERIA: Final = frozenset({"CAR_RANGE_KM", "CAR_SEAT_COUNT", "HOME_CHARGE_TIME_MINUTES"})
MOTORBIKE_ONLY_CRITERIA: Final = frozenset(
    {
        "MOTORBIKE_RANGE_MAX_KM",
        "MOTORBIKE_MAX_LOAD_KG",
        "BATTERY_REMOVABLE",
        "BATTERY_SWAPPABLE",
    }
)

CRITERION_LABELS: Final = {
    "STARTING_PRICE_VND": "Giá từ (đồng)",
    "CAR_RANGE_KM": "Quãng đường mỗi lần sạc (km)",
    "CAR_SEAT_COUNT": "Số chỗ ngồi",
    "HOME_CHARGE_TIME_MINUTES": "Thời gian sạc tại nhà (phút)",
    "MOTORBIKE_RANGE_MAX_KM": "Quãng đường tối đa (km)",
    "MOTORBIKE_MAX_LOAD_KG": "Tải trọng tối đa (kg)",
    "BATTERY_REMOVABLE": "Pin tháo rời",
    "BATTERY_SWAPPABLE": "Pin đổi được",
}

TITLE: Final = "So sánh mẫu xe"
EMPTY_CELL: Final = "—"
BEST_MARK: Final = " ★"
PHOTO_WIDTH: Final = 192
PHOTO_HEIGHT: Final = 108
PHOTO_STRIP_HEIGHT: Final = 132
PHOTO_PLACEHOLDER: Final = "Chưa có ảnh"

_PADDING: Final = 24
_ROW_HEIGHT: Final = 38
_HEADER_HEIGHT: Final = 46
_TITLE_HEIGHT: Final = 44
_LABEL_WIDTH: Final = 260
_COLUMN_WIDTH: Final = 210
_FONT_SIZE: Final = 15
_LABEL_FONT_SIZE: Final = 12

_INK: Final = (28, 27, 25)
_MUTED: Final = (110, 106, 100)
_LINE: Final = (222, 219, 214)
_BACKGROUND: Final = (255, 255, 255)
_HEADER_BACKGROUND: Final = (243, 236, 228)

logger = get_agent_logger("agent.services.comparison_image")


class ComparisonImageError(Exception):
    """Không vẽ được ảnh — dữ liệu không hợp lệ, thiếu font, hoặc bảng rỗng."""


COMPARISON_IMAGE_DIR_ENV = "COMPARISON_IMAGE_DIR"
DEFAULT_COMPARISON_IMAGE_DIR = Path("data/comparison_images")


def default_comparison_image_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Chỗ lưu ảnh đã render, lấy từ env để không phụ thuộc quyền ghi của `data/`.

    `data/` thường do container tạo nên thuộc `root`; tiến trình chạy bằng tài
    khoản thường không ghi được vào đó, và lỗi ấy bị `image_for_review` nuốt
    thành ảnh rỗng — rất khó lần ra. Cho phép trỏ sang chỗ khác bằng env.
    """

    source = os.environ if environ is None else environ
    configured = source.get(COMPARISON_IMAGE_DIR_ENV, "").strip()
    return Path(configured) if configured else DEFAULT_COMPARISON_IMAGE_DIR


class ComparisonImageStore:
    """Giữ ảnh đã render theo `run_id` cho tới lúc bản nháp được duyệt và gửi đi.

    Ảnh sinh ra ở lượt chat nhưng chỉ được phép rời hệ thống sau khi tư vấn viên
    duyệt (HITL A7), nên nó phải sống qua ranh giới hai bước đó. Lưu theo `run_id`
    để đường gửi khách lấy đúng ảnh của đúng lượt, không cần thêm cột vào bảng.
    """

    def __init__(self, directory: str | Path) -> None:
        self._directory = Path(directory)

    def save(self, run_id: UUID, image: bytes) -> Path:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._path_for(run_id)
        path.write_bytes(image)
        return path

    def load(self, run_id: UUID) -> bytes | None:
        """`None` khi lượt đó không có ảnh — không có ảnh không phải là lỗi."""
        path = self._path_for(run_id)
        return path.read_bytes() if path.is_file() else None

    def _path_for(self, run_id: UUID) -> Path:
        return self._directory / f"{run_id}.png"


def render_comparison_image(
    table: ComparisonTable,
    *,
    photos: Mapping[UUID, bytes] | None = None,
    font_dir: str | Path | None = None,
    _debug_text: bool = False,
) -> bytes | str:
    """Vẽ bảng so sánh thành PNG.

    `_debug_text` trả về phần văn bản đã đặt lên ảnh thay vì bytes — dùng cho
    test nội dung nhãn, không dùng ở đường chạy thật.
    """
    _reject_cross_vehicle_type(table)
    _reject_unrenderable(table)

    valid_photo_ids = _valid_photo_ids(table, photos)
    lines = _text_layout(table, photos, valid_photo_ids)
    if _debug_text:
        return "\n".join(text for _, _, text, _ in lines)

    if Image is None or ImageDraw is None or ImageFont is None:
        return None
    regular, bold = _load_fonts(font_dir)

    return _draw(table, lines, photos, valid_photo_ids, regular, bold)


def render_comparison_image_or_none(
    table: ComparisonTable,
    *,
    photos: Mapping[UUID, bytes] | None = None,
    font_dir: str | Path | None = None,
) -> bytes | None:
    """Lối gọi an toàn cho lượt chat: vẽ được thì trả ảnh, không thì trả `None`.

    Lượt chat không được chết vì thiếu font hay dữ liệu rỗng — câu trả lời văn
    bản vẫn phải tới khách, chỉ thiếu ảnh.
    """
    try:
        image = render_comparison_image(table, photos=photos, font_dir=font_dir)
    except (ComparisonImageError, CrossVehicleTypeComparisonError, OSError):
        return None
    return image if isinstance(image, bytes) else None


def _reject_cross_vehicle_type(table: ComparisonTable) -> None:
    """Bảng trộn ô tô với xe máy điện bị từ chối, kể cả khi đi vòng qua đường ảnh."""
    codes = {row.criterion_code for row in table.rows}
    if codes & CAR_ONLY_CRITERIA and codes & MOTORBIKE_ONLY_CRITERIA:
        raise CrossVehicleTypeComparisonError
    foreign = MOTORBIKE_ONLY_CRITERIA if table.vehicle_type is VehicleType.CAR else CAR_ONLY_CRITERIA
    if codes & foreign:
        raise CrossVehicleTypeComparisonError


def _reject_unrenderable(table: ComparisonTable) -> None:
    if not table.rows:
        raise ComparisonImageError("bảng so sánh không có dòng nào để vẽ")
    if not MIN_VEHICLES <= len(table.vehicle_ids) <= MAX_VEHICLES:
        raise ComparisonImageError(f"bảng so sánh cần {MIN_VEHICLES}–{MAX_VEHICLES} mẫu, nhận {len(table.vehicle_ids)}")


def _load_fonts(font_dir: str | Path | None) -> tuple[ImageFont.FreeTypeFont, ImageFont.FreeTypeFont]:
    """Nạp font đóng gói; thiếu file là lỗi để giữ ảnh byte-identical."""
    directory = Path(font_dir) if font_dir is not None else DEFAULT_FONT_DIR
    paths = [directory / REGULAR_FONT_NAME, directory / BOLD_FONT_NAME]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ComparisonImageError(f"thiếu font: {', '.join(missing)}")
    regular = ImageFont.truetype(str(paths[0]), _FONT_SIZE)
    bold = ImageFont.truetype(str(paths[1]), _FONT_SIZE)
    return regular, bold


def _cell_text(row: ComparisonRow, index: int) -> tuple[str, str | None]:
    """Giá trị hiển thị và nhãn thẩm quyền của một ô."""
    if index >= len(row.cells):
        return EMPTY_CELL, None
    cell = row.cells[index]
    value = cell.value_text or EMPTY_CELL
    if cell.is_better:
        value += BEST_MARK
    return value, cell.label


def _valid_photo_ids(table: ComparisonTable, photos: Mapping[UUID, bytes] | None) -> frozenset[UUID]:
    if photos is None or Image is None:
        return frozenset()

    valid_ids: set[UUID] = set()
    for vehicle_id in table.vehicle_ids:
        payload = photos.get(vehicle_id)
        if payload is None:
            continue
        try:
            with Image.open(io.BytesIO(payload)) as photo:
                photo.load()
                if photo.size != (PHOTO_WIDTH, PHOTO_HEIGHT):
                    logger.warning("invalid vehicle photo: unexpected dimensions")
                    continue
        except (UnidentifiedImageError, OSError):
            logger.warning("invalid vehicle photo: cannot decode payload", exc_info=True)
            continue
        valid_ids.add(vehicle_id)
    return frozenset(valid_ids)


def _text_layout(
    table: ComparisonTable,
    photos: Mapping[UUID, bytes] | None,
    valid_photo_ids: frozenset[UUID],
) -> list[tuple[int, int, str, bool]]:
    """Mọi mẩu chữ sẽ đặt lên ảnh: `(x, y, text, is_muted)`."""
    lines: list[tuple[int, int, str, bool]] = [(_PADDING, _PADDING, TITLE, False)]
    header_y = _PADDING + _TITLE_HEIGHT + (PHOTO_STRIP_HEIGHT if photos is not None else 0)
    for column, vehicle_id in enumerate(table.vehicle_ids):
        x = _PADDING + _LABEL_WIDTH + column * _COLUMN_WIDTH
        if photos is not None and vehicle_id not in valid_photo_ids:
            name = table.vehicle_names[column] if table.vehicle_names else f"Mẫu {column + 1}"
            lines.append((x + 24, _PADDING + _TITLE_HEIGHT + 52, f"{PHOTO_PLACEHOLDER}: {name}", True))
        lines.append((x, header_y + 12, f"Mẫu {column + 1}", False))

    for index, row in enumerate(table.rows):
        y = header_y + _HEADER_HEIGHT + index * _ROW_HEIGHT
        label = CRITERION_LABELS.get(row.criterion_code, row.criterion_code)
        lines.append((_PADDING, y + 10, label, False))
        for column in range(len(table.vehicle_ids)):
            x = _PADDING + _LABEL_WIDTH + column * _COLUMN_WIDTH
            value, cell_label = _cell_text(row, column)
            lines.append((x, y + 4, value, False))
            if cell_label:
                lines.append((x, y + 21, cell_label, True))
    return lines


def _canvas_size(table: ComparisonTable, photos: Mapping[UUID, bytes] | None) -> tuple[int, int]:
    width = _PADDING * 2 + _LABEL_WIDTH + _COLUMN_WIDTH * len(table.vehicle_ids)
    height = _PADDING * 2 + _TITLE_HEIGHT + _HEADER_HEIGHT + _ROW_HEIGHT * len(table.rows)
    if photos is not None:
        height += PHOTO_STRIP_HEIGHT
    return width, height


def _draw(
    table: ComparisonTable,
    lines: list[tuple[int, int, str, bool]],
    photos: Mapping[UUID, bytes] | None,
    valid_photo_ids: frozenset[UUID],
    regular: ImageFont.FreeTypeFont,
    bold: ImageFont.FreeTypeFont,
) -> bytes:
    width, height = _canvas_size(table, photos)
    image = Image.new("RGB", (width, height), _BACKGROUND)
    canvas = ImageDraw.Draw(image)

    photo_y = _PADDING + _TITLE_HEIGHT
    if photos is not None:
        for column, vehicle_id in enumerate(table.vehicle_ids):
            x = _PADDING + _LABEL_WIDTH + column * _COLUMN_WIDTH + (_COLUMN_WIDTH - PHOTO_WIDTH) // 2
            if vehicle_id in valid_photo_ids:
                with Image.open(io.BytesIO(photos[vehicle_id])) as photo:
                    image.paste(photo, (x, photo_y))
            else:
                canvas.rectangle([(x, photo_y), (x + PHOTO_WIDTH, photo_y + PHOTO_HEIGHT)], outline=_LINE, width=1)

    header_y = photo_y + (PHOTO_STRIP_HEIGHT if photos is not None else 0)
    canvas.rectangle(
        [(_PADDING, header_y), (width - _PADDING, header_y + _HEADER_HEIGHT)],
        fill=_HEADER_BACKGROUND,
    )
    for index in range(len(table.rows) + 1):
        y = header_y + _HEADER_HEIGHT + index * _ROW_HEIGHT
        canvas.line([(_PADDING, y), (width - _PADDING, y)], fill=_LINE)

    small = ImageFont.truetype(regular.path, _LABEL_FONT_SIZE)
    for x, y, text, muted in lines:
        font = small if muted else (bold if text == TITLE else regular)
        canvas.text((x, y), text, font=font, fill=_MUTED if muted else _INK)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False, compress_level=6)
    return buffer.getvalue()
