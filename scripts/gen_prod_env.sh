#!/usr/bin/env bash
# Sinh khung .env cho prod hoac staging, voi cac secret ngau nhien da dien san.
# Chay TREN VPS:
#   bash gen_prod_env.sh prod    > ~/p150-prod/.env
#   bash gen_prod_env.sh staging > ~/p150-staging/.env
#
# Cac gia tri con de trong (OPENAI_API_KEY, SendGrid) phai dien tay sau.
set -euo pipefail

ENV_KIND="${1:-prod}"
case "$ENV_KIND" in
  prod)
    PROJECT=p150prod; BE_PORT=8000; FE_PORT=3000
    DOMAIN=evadvisor150.id.vn
    MEM_BE=1536m; MEM_FE=512m; MEM_PG=1g; MEM_MINIO=512m ;;
  staging)
    PROJECT=p150stg;  BE_PORT=8001; FE_PORT=3001
    DOMAIN=dev.evadvisor150.id.vn
    # Khau phan hep hon prod co chu dich: hai moi truong chung mot VPS, va khi
    # bo nho cang thi prod la ben phai song.
    MEM_BE=1g; MEM_FE=384m; MEM_PG=512m; MEM_MINIO=256m ;;
  *)
    echo "dung: $0 [prod|staging]" >&2; exit 1 ;;
esac

cat <<EOF
# Sinh boi scripts/gen_prod_env.sh ($ENV_KIND) — $(date +%F)
# KHONG commit file nay.

# Tach stack: prod va staging chay cung VPS nen phai khac project name va cong.
COMPOSE_PROJECT_NAME=$PROJECT
BACKEND_PORT=$BE_PORT
FRONTEND_PORT=$FE_PORT

# Tran bo nho tung container (xem dau docker-compose.prod.yml).
MEM_BACKEND=$MEM_BE
MEM_FRONTEND=$MEM_FE
MEM_POSTGRES=$MEM_PG
MEM_MINIO=$MEM_MINIO

APP_ENV=production
LOG_LEVEL=INFO

# ---- PHAI DIEN TAY ----
OPENAI_API_KEY=
FALLBACK_MODEL_NAME=gpt-4o
MODERATION_MODEL_NAME=omni-moderation-latest

POSTGRES_USER=p150
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
POSTGRES_DB=p150

AUTH_ENABLED=true
AUTH_JWT_SIGNING_KEY=$(openssl rand -base64 48)
AUTH_CSRF_SECRET=$(openssl rand -base64 48)
AUTH_COOKIE_SECURE=true
AUTH_CORS_ORIGINS=https://$DOMAIN
AUTH_FRONTEND_ORIGIN=https://$DOMAIN
CORS_ORIGINS=https://$DOMAIN
# ---- PHAI DIEN TAY (email khoi phuc mat khau) ----
AUTH_SENDGRID_API_KEY=
AUTH_SENDGRID_FROM_EMAIL=

DOCUMENT_ENABLED=true
DOCUMENT_ACCESS_KEY=$(openssl rand -hex 16)
DOCUMENT_SECRET_KEY=$(openssl rand -base64 32 | tr -d '/+=' | head -c 32)
DOCUMENT_BUCKET_NAME=p150-documents
DOCUMENT_BUCKET_PRIVATE=true

LOCATIONS_ENABLED=true
EOF
