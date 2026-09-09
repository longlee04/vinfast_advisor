#!/usr/bin/env bash
set -euo pipefail

# Migration LUON chay: mot instance backend duy nhat (TurnEventBroker in-memory)
# nen khong co canh tranh giua nhieu container.
#
# `MIGRATE_LENIENT=true` nuot loi migration — chi dung cho may dev, noi mot module
# chua cau hinh xong khong duoc phep chan ca stack. Tren prod de mac dinh
# ("false"): schema hong ma van len app la cach hong am tham nhat.
MIGRATE_LENIENT="${MIGRATE_LENIENT:-false}"

# Seed MAC DINH TAT. Cac script seed ghi de du lieu tu file trong data-p150/,
# nen chay lai moi lan container restart se dam len du lieu that tren prod.
# Dev bat bang SEED_ON_START=true (xem docker-compose.yml); prod seed mot lan
# bang tay: `docker compose exec backend /app/scripts/seed_all.sh`.
SEED_ON_START="${SEED_ON_START:-false}"

MODULES=(auth document products agent locations)

echo "[BE Docker] Running Alembic migrations..."
for cfg in "${MODULES[@]}"; do
  if python -m alembic -c "alembic-${cfg}.ini" upgrade head; then
    echo "[BE Docker] migration ${cfg}: ok"
  elif [ "${MIGRATE_LENIENT}" = "true" ]; then
    echo "[WARNING] migration ${cfg} failed, bo qua vi MIGRATE_LENIENT=true"
  else
    echo "[FATAL] migration ${cfg} that bai. Dat MIGRATE_LENIENT=true neu co y bo qua." >&2
    exit 1
  fi
done

if [ "${SEED_ON_START}" = "true" ]; then
  echo "[BE Docker] SEED_ON_START=true — seeding database..."
  /app/scripts/seed_all.sh
else
  echo "[BE Docker] Bo qua seed (SEED_ON_START=${SEED_ON_START})."
fi

echo "[BE Docker] Starting FastAPI backend..."
exec "$@"
