#!/usr/bin/env bash
# Nap du lieu goc (auth users, locations, catalog) tu data-p150/ vao DB.
#
# Tach khoi docker-entrypoint.sh co chu dich: day la thao tac GHI DE, khong
# phai buoc khoi dong. Tren prod goi bang tay mot lan sau khi dung stack:
#   docker compose -f docker-compose.prod.yml exec backend /app/scripts/seed_all.sh
set -euo pipefail

echo "[seed] auth users..."
python scripts/seed_auth_users.py
echo "[seed] locations..."
python scripts/seed_locations_data.py
echo "[seed] catalog..."
python scripts/seed_catalog_data.py
echo "[seed] xong."
