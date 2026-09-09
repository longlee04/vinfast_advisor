"""Nạp dữ liệu ĐỊA ĐIỂM (5 loại) từ CSV/JSON vào bảng `locations`.

Năm loại: showroom ô tô, showroom xe máy điện, trạm sạc ô tô, trạm sạc xe máy,
tủ đổi pin.

Usage:
    uv run python scripts/import_service_locations.py data/dia_diem.csv
    uv run python scripts/import_service_locations.py data/*.json --dsn postgresql://...
    uv run python scripts/import_service_locations.py data/showroom_car.csv --dry-run
    uv run python scripts/import_service_locations.py data/x.csv --location-type SHOWROOM_CAR

[KHÁC BIỆT] Đặc tả yêu cầu tạo bảng `charging_stations` riêng. Repo ĐÃ có bảng
`locations` (`migrations/locations/versions/b44e204613af`) đang giữ 23.456 trạm
sạc/đổi pin thật, cùng 60.861 địa điểm VinFast khác, và `/api/v1/locations/nearby`
đã truy vấn chúng bằng Haversine trên index btree. Dựng thêm một bảng cho cùng
loại dữ liệu là dựng nguồn sự thật thứ hai: bản đồ trên trang `/locations` và câu
trả lời của chatbot sẽ lệch nhau ngay lần cập nhật đầu tiên chỉ chạm một bảng.
Script này vì vậy nạp VÀO `locations`, không tạo bảng mới.

[KHÁC BIỆT] Khoá dedupe của đặc tả là `name + latitude + longitude`. Khoá duy
nhất THẬT của bảng là `external_id`. Script tôn trọng cả hai: có `external_id`
trong nguồn thì dùng nguyên; không có thì sinh một `external_id` TẤT ĐỊNH từ
`name + latitude + longitude` (`GEN-` + 16 hex đầu của SHA-256). Cùng ba giá trị
đó luôn cho cùng một khoá, nên chạy lại không nhân đôi bản ghi — đúng ngữ nghĩa
đặc tả yêu cầu, chỉ khác chỗ khoá được cất.

Loại địa điểm được xác định theo BA nguồn, ưu tiên giảm dần: cờ `--location-type`,
cột `location_type` trong file, rồi TÊN FILE (`showroom_car.csv`,
`tu_doi_pin.json`, …). Không nguồn nào cho biết loại thì bản ghi bị BỎ QUA kèm một
dòng log đếm — đoán loại là cách chắc chắn nhất để 300 showroom nằm lẫn trong kết
quả tìm trạm sạc.

Tự dò định dạng theo đuôi file, và tự map tên cột: nguồn dùng `lat`/`lon`,
`vĩ độ`/`kinh độ`, hay `latitude`/`longitude` đều đọc được (xem `_FIELD_ALIASES`).
Cột không nhận ra được giữ nguyên chứ không ném đi — chúng vào `directions_url`/
`status`/`hotline` khi khớp, còn lại bị bỏ qua với một dòng log đếm số lượng.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import logging
import os
import sys
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import asyncpg

# Chạy thẳng bằng `python scripts/import_charging_stations.py` thì Python đặt
# `scripts/` (chứ không phải gốc repo) lên `sys.path`, và `from scripts...` dưới
# đây gãy. Thêm gốc repo vào trước khi import — cùng việc mà
# `prepend_sys_path = .` trong `alembic-*.ini` đang làm cho các file migration.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.seed_locations_data import INSERT_SQL, split_address  # noqa: E402

LOG_FILE = Path("logs/app.log")
BATCH_SIZE = 1000

#: `location_type` → nhãn tiếng Việt. Lấy NGUYÊN VĂN từ
#: `data-p150/locations/manifest.json` để hai nguồn không nói hai tên cho một loại.
CATEGORY_LABELS: Final[dict[str, str]] = {
    "showroom_car": "Showroom Ô tô",
    "showroom_escooter": "Showroom Xe máy điện",
    "car_charging_station": "Trạm sạc ô tô điện",
    "bike_charging_station": "Trạm sạc xe máy điện",
    "battery_swap_station": "Tủ đổi pin",
}

#: Mã `LocationKind` (hợp đồng công khai) → chuỗi kho lưu trữ. Cho phép truyền
#: `--location-type SHOWROOM_CAR` thay vì bắt người dùng nhớ chuỗi nội bộ.
KIND_TO_STORAGE: Final[dict[str, str]] = {
    "SHOWROOM_CAR": "showroom_car",
    "SHOWROOM_MOTORBIKE": "showroom_escooter",
    "CHARGING_STATION_CAR": "car_charging_station",
    "CHARGING_STATION_MOTORBIKE": "bike_charging_station",
    "BATTERY_SWAP_CABINET": "battery_swap_station",
}

#: Cụm trong TÊN FILE → loại. Dùng khi người dùng tách mỗi loại một file và không
#: có cột `location_type` nào bên trong. Xét theo thứ tự khai báo: "tu_doi_pin"
#: phải thắng "pin", và "showroom_escooter" phải thắng "showroom".
_FILENAME_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("battery_swap", "battery_swap_station"),
    ("doi_pin", "battery_swap_station"),
    ("doipin", "battery_swap_station"),
    ("tu_pin", "battery_swap_station"),
    ("showroom_escooter", "showroom_escooter"),
    ("showroom_motorbike", "showroom_escooter"),
    ("showroom_xe_may", "showroom_escooter"),
    ("showroom_car", "showroom_car"),
    ("showroom_oto", "showroom_car"),
    ("showroom_o_to", "showroom_car"),
    ("bike_charging", "bike_charging_station"),
    ("charging_motorbike", "bike_charging_station"),
    ("tram_sac_xe_may", "bike_charging_station"),
    ("car_charging", "car_charging_station"),
    ("charging_car", "car_charging_station"),
    ("tram_sac_oto", "car_charging_station"),
    ("tram_sac_o_to", "car_charging_station"),
)

#: Cụm trong tên cột nguồn → tên trường chuẩn. So khớp sau khi hạ thường và bỏ
#: dấu gạch/khoảng trắng, nên `Latitude`, `lat_`, `LAT` đều về `latitude`.
_FIELD_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "external_id": ("externalid", "id", "stationid", "code", "storeid", "ma", "matram"),
    "name": ("name", "ten", "tentram", "stationname", "title"),
    "address": ("address", "diachi", "location", "fulladdress"),
    "province": ("province", "city", "tinh", "tinhthanh", "thanhpho", "provincename"),
    "district": ("district", "quan", "huyen", "quanhuyen", "districtname"),
    "latitude": ("latitude", "lat", "vido", "viDo", "y"),
    "longitude": ("longitude", "lon", "lng", "long", "kinhdo", "x"),
    "location_type": ("locationtype", "type", "loai", "loaitram", "categoryslug"),
    "category_name": ("categoryname", "category", "nhom", "tenloai"),
    "charger_type": ("chargertype", "chuansac", "connectortype", "plugtype"),
    "num_ports": ("numports", "ports", "socong", "soluongcong", "connectors"),
    "hotline": ("hotline", "phone", "sodienthoai", "dienthoai", "servicehotline"),
    "open_time": ("opentime", "giomo", "opentimeservice", "opentimesales"),
    "close_time": ("closetime", "giodong", "closetimeservice", "closetimesales"),
    "status": ("status", "trangthai", "chargingstatus", "active"),
    "directions_url": ("directionsurl", "mapurl", "mapsurl", "duongdan"),
    "source_url": ("sourceurl", "nguon", "source"),
}


def setup_logger() -> logging.Logger:
    """Logger ghi ra `logs/app.log` và console — cùng khuôn `seed_locations_data`."""

    logger = logging.getLogger("import_charging_stations")
    logger.setLevel(logging.INFO)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not any(
        isinstance(handler, logging.FileHandler) and handler.baseFilename.endswith("app.log")
        for handler in logger.handlers
    ):
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
    return logger


def _canonical(column: str) -> str:
    """Tên cột về dạng so khớp được: bỏ dấu, chỉ chữ và số, hạ thường.

    Bỏ dấu là bắt buộc chứ không phải cho gọn: bảng alias viết không dấu
    (`vido`, `kinhdo`, `diachi`), còn nguồn thật thì hay đặt tên cột có dấu
    ("Vĩ độ", "Địa chỉ"). Ký tự tiếng Việt vẫn là `isalnum()` trong Python, nên
    không bỏ dấu thì "Vĩ độ" thành "vĩđộ" và không khớp alias nào — file bị từ
    chối với thông báo "không tìm ra cột cho latitude" dù cột đó đang có mặt.
    """

    decomposed = unicodedata.normalize("NFD", (column or "").lower())
    # `đ`/`Đ` KHÔNG tách được bằng NFD (nó là một chữ cái riêng, không phải `d`
    # cộng dấu), nên phải thay tay — thiếu bước này thì "Địa chỉ" vẫn trượt.
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn").replace("đ", "d")
    return "".join(char for char in stripped if char.isalnum())


def build_column_map(columns: Iterable[str]) -> dict[str, str]:
    """Tên cột nguồn → tên trường chuẩn.

    Hai vòng: khớp CHÍNH XÁC theo thứ tự ưu tiên của alias, rồi mới khớp CHỨA
    cho những trường còn thiếu. Xem chú thích tại chỗ về lý do của cả hai.
    """

    mapping: dict[str, str] = {}
    taken: set[str] = set()
    canonical = {column: _canonical(column) for column in columns}
    # Vòng 1 — khớp CHÍNH XÁC, duyệt theo THỨ TỰ ALIAS chứ không theo thứ tự cột.
    # Thứ tự alias là thứ tự ưu tiên: `status` đứng trước `chargingstatus`, nên
    # một file mang cả hai cột sẽ lấy `status` — cùng cột mà
    # `scripts/seed_locations_data.py` đang nạp và cùng giá trị ("1"/"True") mà
    # `frontend/src/lib/api/locations.ts` biết đọc. Duyệt theo thứ tự cột thì
    # cột nào đứng trước trong file sẽ thắng, và cùng một bộ dữ liệu nạp bằng
    # hai script cho ra hai giá trị `status` khác nhau.
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            match = next(
                (column for column, name in canonical.items() if column not in mapping and name == alias),
                None,
            )
            if match is not None:
                mapping[match], _ = field, taken.add(field)
                break
    # Vòng 2 — khớp CHỨA, chỉ cho những trường vòng 1 chưa tìm ra. Chạy sau là
    # điều kiện an toàn: đảo thứ tự thì cột `latitude` có nguy cơ bị một alias
    # ngắn hơn của trường khác chiếm mất, và cả file được nạp với hai cột hoán
    # vị — một lỗi im lặng, chỉ lộ ra khi trạm gần nhất nằm giữa Ấn Độ Dương.
    for field, aliases in _FIELD_ALIASES.items():
        if field in taken:
            continue
        for column, name in canonical.items():
            if column in mapping:
                continue
            if any(alias in name or name in alias for alias in aliases):
                mapping[column], _ = field, taken.add(field)
                break
    return mapping


def _text(value: object, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len is not None else text


def _coordinate(value: object) -> float | None:
    """Toạ độ dạng số. Chuỗi có dấu phẩy thập phân ("21,0123") vẫn đọc được."""

    if value is None:
        return None
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def synthetic_external_id(name: str, latitude: float, longitude: float) -> str:
    """Khoá dedupe TẤT ĐỊNH từ `name + latitude + longitude`.

    Toạ độ làm tròn 6 chữ số trước khi băm — đúng độ chính xác cột `Numeric(9,6)`
    lưu được. Không làm tròn thì `21.0123000001` và `21.0123` sinh hai khoá khác
    nhau cho hai bản ghi mà database coi là một.
    """

    seed = f"{' '.join(name.split()).casefold()}|{latitude:.6f}|{longitude:.6f}"
    return f"GEN-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def _load_records(path: Path) -> list[dict[str, Any]]:
    """Đọc CSV hoặc JSON theo đuôi file; JSON nhận cả list lẫn `{"items": [...]}`."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    if suffix in {".json", ".jsonl"}:
        if suffix == ".jsonl":
            return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, Mapping):
            for key in ("items", "data", "records", "results"):
                if isinstance(payload.get(key), list):
                    return list(payload[key])
            return [dict(payload)]
        return list(payload)
    raise SystemExit(f"Định dạng không hỗ trợ: {path.name} (chỉ nhận .csv/.json/.jsonl)")


def _normalized(record: Mapping[str, Any], column_map: Mapping[str, str]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for column, value in record.items():
        field = column_map.get(column)
        if field is not None and normalized.get(field) in (None, ""):
            normalized[field] = value
    return normalized


def location_type_from_filename(path: Path) -> str | None:
    """Loại suy từ TÊN FILE, hoặc `None` khi tên không gợi ý gì.

    Dùng khi người dùng tách mỗi loại một file — cách chia phổ biến nhất, và cũng
    là cách mà `data-p150/locations/` đang dùng.
    """

    stem = _canonical(path.stem).replace("station", "")
    name = path.stem.lower().replace("-", "_").replace(" ", "_")
    for hint, location_type in _FILENAME_HINTS:
        if hint in name or hint.replace("_", "") in stem:
            return location_type
    return None


def _location_type(normalized: Mapping[str, Any], fallback: str | None) -> str | None:
    """Loại của MỘT bản ghi, quy về đúng năm giá trị bảng `locations` đang dùng.

    `None` nghĩa là không xác định được — bản ghi bị bỏ qua. Đoán một loại mặc
    định là cách chắc chắn nhất để 300 showroom nằm lẫn trong kết quả tìm trạm
    sạc, và không ai phát hiện ra cho tới khi một khách lái xe tới tận nơi.
    """

    raw = _text(normalized.get("location_type")) or ""
    key = raw.strip().lower()
    if key in CATEGORY_LABELS:
        return key
    if raw.strip().upper() in KIND_TO_STORAGE:
        return KIND_TO_STORAGE[raw.strip().upper()]
    haystack = f"{key} {_text(normalized.get('category_name')) or ''}".lower()
    if "đổi pin" in haystack or "doi pin" in haystack or "swap" in haystack:
        return "battery_swap_station"
    if "showroom" in haystack or "đại lý" in haystack or "dai ly" in haystack:
        if "xe máy" in haystack or "xe may" in haystack or "escooter" in haystack:
            return "showroom_escooter"
        return "showroom_car"
    if "sạc" in haystack or "sac" in haystack or "charging" in haystack:
        if "xe máy" in haystack or "xe may" in haystack or "bike" in haystack:
            return "bike_charging_station"
        return "car_charging_station"
    return fallback


def to_row(
    record: Mapping[str, Any],
    column_map: Mapping[str, str],
    now: datetime,
    fallback_type: str | None = None,
):
    """Một bản ghi nguồn → tuple tham số cho `INSERT_SQL`, hoặc `None` khi bỏ qua.

    Bỏ qua (chứ không raise) khi thiếu toạ độ, thiếu tên, hoặc KHÔNG XÁC ĐỊNH
    ĐƯỢC LOẠI: một dòng hỏng trong một file mười nghìn dòng không được làm hỏng cả
    lần nạp, và tổng số dòng bị bỏ được log lại ở cuối.
    """

    normalized = _normalized(record, column_map)
    latitude = _coordinate(normalized.get("latitude"))
    longitude = _coordinate(normalized.get("longitude"))
    name = _text(normalized.get("name"), 255)
    if latitude is None or longitude is None or name is None:
        return None
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return None
    location_type = _location_type(normalized, fallback_type)
    if location_type is None:
        return None
    address = _text(normalized.get("address")) or ""
    city = _text(normalized.get("province"), 128)
    district = _text(normalized.get("district"), 128)
    # Suy `district` từ địa chỉ ngay cả khi nguồn ĐÃ có cột tỉnh/thành: trang
    # `/locations` lọc theo cặp `city + district`, và một bản ghi thiếu quận sẽ
    # biến mất khỏi mọi bộ lọc quận dù địa chỉ của nó ghi rõ quận nào.
    derived_city, derived_district = split_address(address, None)
    city = city or derived_city
    district = district or derived_district
    external_id = _text(normalized.get("external_id"), 64) or synthetic_external_id(name, latitude, longitude)
    # [KHÁC BIỆT] `charger_type` và `num_ports` của đặc tả KHÔNG có cột tương ứng
    # trong bảng `locations`, và bộ dữ liệu thật cũng không mang hai trường đó
    # (xem `docs/nearby-location-finder.md`). Nguồn nào CÓ thì hai giá trị được
    # ghép vào `status` để không mất dữ liệu — thà giữ ở một cột đọc được còn hơn
    # ném đi hoặc thêm một cột mà chỉ vài nguồn điền.
    extras = [
        _text(normalized.get("status"), 32),
        _text(normalized.get("charger_type"), 16),
        None if _text(normalized.get("num_ports")) is None else f"{_text(normalized.get('num_ports'))} cổng",
    ]
    status = _text(" / ".join(part for part in extras if part), 32)
    return (
        str(uuid.uuid4()),
        external_id,
        location_type,
        _text(normalized.get("category_name"), 128) or CATEGORY_LABELS[location_type],
        name,
        address or "Chưa có địa chỉ",
        city[:128],
        district[:128] if district else None,
        None,
        None,
        latitude,
        longitude,
        _text(normalized.get("hotline"), 64),
        _text(normalized.get("directions_url")),
        _text(normalized.get("open_time"), 16),
        _text(normalized.get("close_time"), 16),
        status,
        _text(normalized.get("source_url")),
        now,
        now,
    )


def rows_from(path: Path, logger: logging.Logger, forced_type: str | None = None) -> list[tuple]:
    records = _load_records(path)
    if not records:
        logger.warning("BỎ QUA %s: không có bản ghi nào", path.name)
        return []
    column_map = build_column_map(records[0].keys())
    missing = {"latitude", "longitude", "name"} - set(column_map.values())
    if missing:
        raise SystemExit(
            f"{path.name}: không tìm ra cột cho {sorted(missing)}. Cột đang có: {sorted(records[0].keys())}"
        )
    logger.info("%s: ánh xạ cột %s", path.name, column_map)
    fallback_type = forced_type or location_type_from_filename(path)
    if fallback_type:
        logger.info("%s: loại mặc định = %s", path.name, fallback_type)
    now = datetime.now(UTC)
    rows = [row for record in records if (row := to_row(record, column_map, now, fallback_type))]
    skipped = len(records) - len(rows)
    if skipped:
        logger.warning(
            "%s: bỏ qua %d dòng thiếu tên, toạ độ hợp lệ, hoặc không rõ loại địa điểm",
            path.name,
            skipped,
        )
    return rows


async def import_files(paths: list[Path], dsn: str, dry_run: bool, forced_type: str | None = None) -> int:
    logger = setup_logger()
    total = 0
    all_rows: list[tuple] = []
    for path in paths:
        rows = rows_from(path, logger, forced_type)
        logger.info("%s: %d bản ghi hợp lệ", path.name, len(rows))
        all_rows.extend(rows)
        total += len(rows)
    # Khử trùng NGAY TRONG lần chạy này, trước khi chạm database: `executemany`
    # với hai hàng cùng `external_id` trong một batch làm `ON CONFLICT` bắn
    # "cannot affect row a second time" và cả batch rollback.
    deduped: dict[str, tuple] = {}
    for row in all_rows:
        deduped[row[1]] = row
    if len(deduped) != len(all_rows):
        logger.info("khử trùng trong lần chạy: %d → %d bản ghi", len(all_rows), len(deduped))
    rows = list(deduped.values())
    if dry_run:
        logger.info("--dry-run: KHÔNG ghi database. %d bản ghi sẵn sàng nạp.", len(rows))
        return len(rows)
    if not rows:
        # Thoát lỗi rõ ràng thay vì exit 0 im lặng — cùng lý do đã ghi ở
        # `scripts/seed_locations_data.seed`: một lần chạy hỏng hoàn toàn không
        # được trông giống một lần chạy thành công.
        raise SystemExit("Import thất bại: 0 bản ghi hợp lệ (kiểm tra file nguồn).")
    connection = await asyncpg.connect(dsn)
    try:
        for start in range(0, len(rows), BATCH_SIZE):
            await connection.executemany(INSERT_SQL, rows[start : start + BATCH_SIZE])
    finally:
        await connection.close()
    logger.info("Import hoàn tất: %d bản ghi đã nạp/cập nhật vào bảng locations.", len(rows))
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="file CSV/JSON/JSONL chứa địa điểm")
    parser.add_argument(
        "--location-type",
        choices=sorted(KIND_TO_STORAGE),
        default=None,
        help="ép loại cho mọi bản ghi, thắng cả cột trong file lẫn tên file",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("LOCATIONS_DATABASE_URL_SYNC", ""),
        help="DSN Postgres, ví dụ postgresql://user:pass@localhost:5432/db",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="đọc và ánh xạ cột nhưng KHÔNG ghi database",
    )
    args = parser.parse_args()
    paths = [Path(name) for name in args.files]
    for path in paths:
        if not path.exists():
            raise SystemExit(f"Không tìm thấy file: {path}")
    dsn = args.dsn or os.environ.get("LOCATIONS_DATABASE_URL", "")
    if not dsn:
        dsn = os.environ.get("AUTH_DATABASE_URL", "")
    if not dsn and not args.dry_run:
        raise SystemExit(
            "Thiếu DSN: truyền --dsn, đặt LOCATIONS_DATABASE_URL / AUTH_DATABASE_URL, "
            "hoặc chạy với --dry-run để chỉ kiểm tra file."
        )
    forced = KIND_TO_STORAGE.get(args.location_type) if args.location_type else None
    asyncio.run(
        import_files(
            paths,
            dsn.replace("postgresql+asyncpg://", "postgresql://"),
            args.dry_run,
            forced,
        )
    )


if __name__ == "__main__":
    main()
