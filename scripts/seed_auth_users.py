"""Seed bảng `auth_users` với 3 tài khoản tương ứng 3 role: admin, customer, advisor.

Usage:
    uv run python scripts/seed_auth_users.py [--dsn postgresql://...] [--truncate]

Tài khoản tạo sẵn:
  - Admin: admin@vinfast.local / Admin@123456 (role: admin)
  - Customer: customer@vinfast.local / Customer@123456 (role: customer)
  - Advisor (Tư vấn viên): advisor@vinfast.local / Advisor@123456 (role: advisor)

Idempotent theo `email`: chạy lại không nhân đôi bản ghi. Dùng `ON CONFLICT (email) DO UPDATE`.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from src.auth.domain.values import PlaintextPassword
from src.auth.infrastructure.argon2_hasher import Argon2idHasher

LOG_FILE = Path("logs/app.log")

DEFAULT_USERS = [
    {
        "email": "admin@gmail.com",
        "password": "Admin@123456",
        "role": "admin",
        "name": "Quản trị viên (Admin)",
    },
    {
        "email": "admin@vinfast.vn",
        "password": "Admin@123456",
        "role": "admin",
        "name": "Quản trị viên (Admin)",
    },
    {
        "email": "admin@vinfast.local",
        "password": "Admin@123456",
        "role": "admin",
        "name": "Quản trị viên (Admin)",
    },
    {
        "email": "advisor@gmail.com",
        "password": "Advisor@123456",
        "role": "advisor",
        "name": "Tư vấn viên (Advisor)",
    },
    {
        "email": "advisor@vinfast.vn",
        "password": "Advisor@123456",
        "role": "advisor",
        "name": "Tư vấn viên (Advisor)",
    },
    {
        "email": "advisor@vinfast.local",
        "password": "Advisor@123456",
        "role": "advisor",
        "name": "Tư vấn viên (Advisor)",
    },
    {
        "email": "customer@gmail.com",
        "password": "Customer@123456",
        "role": "customer",
        "name": "Khách hàng (Customer)",
    },
]

INSERT_SQL = """
INSERT INTO auth_users (
    id, email, role, state, password_hash, temporary_password_expires_at, created_at, updated_at
) VALUES (
    $1, $2, $3, $4, $5, $6, $7, $8
)
ON CONFLICT (email) DO UPDATE SET
    role = EXCLUDED.role,
    state = EXCLUDED.state,
    password_hash = EXCLUDED.password_hash,
    updated_at = EXCLUDED.updated_at
"""


def setup_logger() -> logging.Logger:
    """Get or configure a logger that writes to logs/app.log and console."""
    logger = logging.getLogger("seed_auth_users")
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


async def seed(dsn: str, truncate: bool) -> None:
    logger = setup_logger()
    logger.info("Connecting to database for seeding auth_users...")

    hasher = Argon2idHasher()
    now = datetime.now(UTC)

    connection = await asyncpg.connect(dsn)
    try:
        if truncate:
            # Xoá bảng phụ thuộc trước để tránh lỗi FK
            await connection.execute("DELETE FROM auth_refresh_tokens")
            await connection.execute("DELETE FROM auth_one_time_tokens")
            await connection.execute("DELETE FROM auth_security_events")
            await connection.execute("DELETE FROM auth_bootstrap_admin_claims")
            await connection.execute("DELETE FROM auth_users")
            logger.info("auth_users: cleared user table and dependent tokens")

        rows: list[tuple] = []
        for user_info in DEFAULT_USERS:
            user_id = str(uuid.uuid4())
            email = user_info["email"].lower().strip()
            role = user_info["role"]
            password_hash = hasher.hash(PlaintextPassword(user_info["password"]))

            rows.append(
                (
                    user_id,
                    email,
                    role,
                    "active",
                    password_hash,
                    None,
                    now,
                    now,
                )
            )

        for row in rows:
            await connection.execute(INSERT_SQL, *row)

        logger.info(f"Seed auth_users completed. Total users processed: {len(rows)}")
        logger.info("Created accounts summary:")
        for user in DEFAULT_USERS:
            logger.info(f"  - [{user['role'].upper()}] {user['email']} | Pass: {user['password']} ({user['name']})")
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=os.environ.get("AUTH_DATABASE_URL_SYNC", ""),
        help="DSN Postgres, ví dụ postgresql://user:pass@localhost:5432/db",
    )
    parser.add_argument("--truncate", action="store_true", help="xoá sạch bảng trước khi nạp")
    args = parser.parse_args()
    dsn = args.dsn or os.environ.get("AUTH_DATABASE_URL", "") or os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise SystemExit("Thiếu DSN: truyền --dsn hoặc đặt AUTH_DATABASE_URL / DATABASE_URL")
    asyncio.run(seed(dsn.replace("postgresql+asyncpg://", "postgresql://"), args.truncate))


if __name__ == "__main__":
    main()
