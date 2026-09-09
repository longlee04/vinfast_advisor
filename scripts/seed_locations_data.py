"""Seed bảng `locations` từ data-p150/locations/*.json vào Postgres.

Usage:
    uv run python scripts/seed_locations_data.py [--dsn postgresql://...] [--truncate]

Idempotent theo `external_id`: chạy lại không nhân đôi bản ghi. Dùng
`ON CONFLICT (external_id) DO UPDATE` để lần chạy sau cập nhật bản ghi cũ.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import asyncpg

DATA_DIR = Path(__file__).resolve().parent.parent / "data-p150" / "locations"
MANIFEST = DATA_DIR / "manifest.json"
LOG_FILE = Path("logs/app.log")
BATCH_SIZE = 1000

INSERT_SQL = """
INSERT INTO locations (
    location_id, external_id, location_type, category_name, name, address,
    city, district, province_id, district_id, latitude, longitude,
    hotline, directions_url, open_time, close_time, status, source_url,
    created_at, updated_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
    $13, $14, $15, $16, $17, $18, $19, $20
)
ON CONFLICT (external_id) DO UPDATE SET
    location_type = EXCLUDED.location_type,
    category_name = EXCLUDED.category_name,
    name = EXCLUDED.name,
    address = EXCLUDED.address,
    city = EXCLUDED.city,
    district = EXCLUDED.district,
    province_id = EXCLUDED.province_id,
    district_id = EXCLUDED.district_id,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    hotline = EXCLUDED.hotline,
    directions_url = EXCLUDED.directions_url,
    open_time = EXCLUDED.open_time,
    close_time = EXCLUDED.close_time,
    status = EXCLUDED.status,
    source_url = EXCLUDED.source_url,
    updated_at = EXCLUDED.updated_at
"""


def setup_logger() -> logging.Logger:
    """Get or configure a logger that writes to logs/app.log and console."""
    logger = logging.getLogger("seed_locations")
    logger.setLevel(logging.INFO)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    has_file_handler = any(
        isinstance(h, logging.FileHandler) and h.baseFilename.endswith("app.log") for h in logger.handlers
    )

    if not has_file_handler:
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def split_address(address: str, province_id: str | None) -> tuple[str, str | None]:
    """Tách `city` và `district` từ chuỗi địa chỉ.

    Giữ đúng quy tắc frontend đang dùng ở `lib/mobility-location-data.ts`:
    phần cuối là city, phần áp cuối là district.
    """
    parts = [part.strip() for part in (address or "").split(",") if part.strip()]
    if not parts:
        label = province_id if province_id else "chưa xác định"
        return f"Mã tỉnh/thành {label}", None
    city = parts[-1]
    district = parts[-2] if len(parts) >= 2 else None
    return city, district


def _text(value: object, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len] if max_len is not None else text


def _rows_from(path: Path) -> list[tuple]:
    records = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(UTC)
    rows: list[tuple] = []
    for record in records:
        external_id = _text(record.get("external_id"), 64)
        if external_id is None:
            continue
        latitude = record.get("latitude")
        longitude = record.get("longitude")
        if latitude is None or longitude is None:
            continue
        address = _text(record.get("address")) or ""
        province_id = _text(record.get("province_id"), 16)
        city, district = split_address(address, province_id)
        hotline = _text(record.get("hotline"), 64) or _text(record.get("service_hotline"), 64)
        open_time = _text(record.get("open_time_service"), 16) or _text(record.get("open_time_sales"), 16)
        close_time = _text(record.get("close_time_service"), 16) or _text(record.get("close_time_sales"), 16)
        rows.append(
            (
                str(uuid.uuid4()),
                external_id,
                _text(record.get("location_type"), 64) or "unknown",
                _text(record.get("category_name"), 128) or "Chưa phân loại",
                _text(record.get("name"), 255) or "Chưa có tên",
                address or "Chưa có địa chỉ",
                city[:128],
                district[:128] if district else None,
                province_id,
                _text(record.get("district_id"), 16),
                float(latitude),
                float(longitude),
                hotline,
                _text(record.get("directions_url")),
                open_time,
                close_time,
                _text(record.get("status"), 32),
                _text(record.get("source_url")),
                now,
                now,
            )
        )
    return rows


async def seed(dsn: str, truncate: bool) -> None:
    logger = setup_logger()
    logger.info("Connecting to database for seeding locations...")
    connection = await asyncpg.connect(dsn)
    try:
        if truncate:
            await connection.execute("TRUNCATE TABLE locations")
            logger.info("locations: truncated table")
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        total = 0
        for category in manifest["categories"]:
            file_name = Path(category["file"]).name
            path = DATA_DIR / file_name
            if not path.exists():
                logger.warning(f"BỎ QUA {path.name}: không tìm thấy file")
                continue
            rows = _rows_from(path)
            for start in range(0, len(rows), BATCH_SIZE):
                await connection.executemany(INSERT_SQL, rows[start : start + BATCH_SIZE])
            total += len(rows)
            logger.info(f"Category '{category['id']}': inserted/updated {len(rows)} records")
        logger.info(f"Seed locations completed. Total records processed: {total}")
        if total == 0:
            # Bảng locations là nguồn duy nhất nạp dữ liệu cho 60k+ bản ghi —
            # manifest rỗng, toàn bộ file bị BỎ QUA, hoặc dữ liệu nguồn hỏng
            # đều dẫn tới total=0. Trước đây trường hợp này vẫn log rồi thoát
            # exit code 0, khiến một lần chạy hỏng hoàn toàn trông như thành
            # công. Thoát lỗi rõ ràng để CI/vận hành phát hiện ngay.
            msg = "Seed locations thất bại: 0 bản ghi được xử lý (kiểm tra manifest.json và các file dữ liệu nguồn)."
            logger.error(msg)
            raise SystemExit(msg)
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("LOCATIONS_DATABASE_URL_SYNC", ""),
        help="DSN Postgres, ví dụ postgresql://user:pass@localhost:5432/db",
    )
    parser.add_argument("--truncate", action="store_true", help="xoá sạch bảng trước khi nạp")
    args = parser.parse_args()
    dsn = args.dsn or os.environ.get("LOCATIONS_DATABASE_URL", "")
    if not dsn:
        dsn = os.environ.get("AUTH_DATABASE_URL", "")
    if not dsn:
        raise SystemExit("Thiếu DSN: truyền --dsn hoặc đặt LOCATIONS_DATABASE_URL / AUTH_DATABASE_URL")
    asyncio.run(seed(dsn.replace("postgresql+asyncpg://", "postgresql://"), args.truncate))


if __name__ == "__main__":
    main()
