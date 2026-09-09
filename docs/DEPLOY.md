# Deploy

Build image tren GitHub Actions -> day len GHCR -> SSH vao VPS keo ve va doi
container. VPS **khong build**: `npm run build` cua Next an ~2GB RAM, tren VPS
4GB dang chay Postgres + MinIO thi de OOM giua chung.

```
develop --push--> CI test --> build image --> ghcr.io --> VPS (staging)
main    --push--> CI test --> build image --> ghcr.io --> VPS (production)
```

Staging va production chay **cung mot VPS**, tach nhau bang
`COMPOSE_PROJECT_NAME` va thu muc deploy rieng, nen volume va network khong
dung nhau.

## 1. Chuan bi VPS

Chep `scripts/vps_bootstrap.sh` len VPS va chay mot lan:

```bash
scp scripts/vps_bootstrap.sh <user>@<ip>:~/
ssh <user>@<ip> 'bash ~/vps_bootstrap.sh'
```

No lo: docker, swap 2GB, ufw (chi mo 22/80/443), nginx + certbot, thu muc
`~/p150-prod` va `~/p150-staging`, va khoa SSH rieng cho GitHub Actions. Cuoi
cung no in ra khoa rieng va cac gia tri can dien vao GitHub o muc 3.

Swap khong phai thua tren goi 4GB: Python phinh dot ngot luc parse PDF hay batch
embedding, va OOM kill giua mot luot chat la mat luon luot do
(`TurnEventBroker` giu trong bo nho).

Dang xuat/dang nhap lai sau khi chay, de tu cach thanh vien group `docker` co hieu luc.

## 2. `.env` tren VPS

Dat trong `~/p150-prod/.env` (va ban staging tuong ung). **Khong bao gio commit.**
Workflow khong ghi de file nay — no chi truyen `BACKEND_IMAGE`/`FRONTEND_IMAGE`
qua bien moi truong.

Sinh khung san, secret ngau nhien da dien:

```bash
bash scripts/gen_prod_env.sh prod    > ~/p150-prod/.env
bash scripts/gen_prod_env.sh staging > ~/p150-staging/.env
```

Con lai phai dien tay: `OPENAI_API_KEY`, `AUTH_SENDGRID_API_KEY`,
`AUTH_SENDGRID_FROM_EMAIL`.

Script cung dien luon tran bo nho (`MEM_*`) theo tung moi truong: prod ~3.5G,
staging ~2.2G. Hai moi truong chay song song tren cung VPS, va khi bo nho cang
thi prod la ben phai song. Duoi day la day du cac khoa de doi chieu:

```bash
# Tach stack: prod va staging phai khac nhau
COMPOSE_PROJECT_NAME=p150prod        # staging: p150stg
BACKEND_PORT=8000                    # staging: 8001
FRONTEND_PORT=3000                   # staging: 3001

APP_ENV=production
LOG_LEVEL=INFO

OPENAI_API_KEY=sk-...
FALLBACK_MODEL_NAME=gpt-4o
MODERATION_MODEL_NAME=omni-moderation-latest

POSTGRES_USER=p150
POSTGRES_PASSWORD=<openssl rand -base64 32>
POSTGRES_DB=p150

# Bat buoc doi voi prod. Sinh moi, KHONG bung lai gia tri trong .env.example.
AUTH_ENABLED=true
AUTH_JWT_SIGNING_KEY=<openssl rand -base64 48>
AUTH_CSRF_SECRET=<openssl rand -base64 48>
AUTH_COOKIE_SECURE=true
AUTH_CORS_ORIGINS=https://evadvisor150.id.vn
AUTH_FRONTEND_ORIGIN=https://evadvisor150.id.vn
CORS_ORIGINS=https://evadvisor150.id.vn
AUTH_SENDGRID_API_KEY=...
AUTH_SENDGRID_FROM_EMAIL=...

DOCUMENT_ENABLED=true
DOCUMENT_ACCESS_KEY=<openssl rand -hex 16>
DOCUMENT_SECRET_KEY=<openssl rand -base64 32>
DOCUMENT_BUCKET_NAME=p150-documents
DOCUMENT_BUCKET_PRIVATE=true

LOCATIONS_ENABLED=true
```

`DATABASE_URL` va cac `*_DATABASE_URL` **khong can dat**:
`docker-compose.prod.yml` tu dung ten service `postgres` de dung chung.

## 3. Secrets & vars tren GitHub

Dat o **repo-level** (`Settings > Secrets and variables > Actions`), khong dung
GitHub Environments: tao Environment doi quyen admin tren repo, ma repo nay do
BTC so huu. Workflow chon cau hinh theo nhanh trong job `config`.

Hai moi truong dung chung mot VPS nen ba secret giong nhau ca hai ben:

| Loai | Ten | Gia tri |
|---|---|---|
| secret | `VPS_HOST` | `116.118.6.90` |
| secret | `VPS_USER` | `root` |
| secret | `VPS_SSH_KEY` | noi dung `~/.ssh/gh_deploy` tren VPS |

Chi duong dan va URL la khac:

| Loai | Ten | Gia tri |
|---|---|---|
| var | `VPS_PORT` | `22` |
| var | `PROD_DEPLOY_PATH` | `/root/p150-prod` |
| var | `STAGING_DEPLOY_PATH` | `/root/p150-staging` |
| var | `PROD_API_BASE_URL` | `https://evadvisor150.id.vn/api/v1` |
| var | `STAGING_API_BASE_URL` | `https://dev.evadvisor150.id.vn/api/v1` |
| var | `PROD_HEALTHCHECK_URL` | `http://127.0.0.1:8000/health` |
| var | `STAGING_HEALTHCHECK_URL` | `http://127.0.0.1:8001/health` |

Khong can PAT: VPS dang nhap GHCR bang `GITHUB_TOKEN` cua chinh lan chay, va
token do chet ngay khi job ket thuc.

`VPS_SSH_KEY` nap thang tu VPS, khong qua clipboard:

```bash
ssh root@116.118.6.90 'cat ~/.ssh/gh_deploy' \
  | gh secret set VPS_SSH_KEY --repo AI20K-Build-Phase-Cohort-3/P-150
```

`*_API_BASE_URL` **bake vao bundle luc build**. Doi gia tri nay phai chay lai
workflow, restart container khong an thua.

Khi nao co quyen admin: chuyen sang GitHub Environments de them cong "Required
reviewers" truoc khi ban vao prod.

## 4. Nginx + HTTPS

Cau hinh nam san trong `deploy/nginx/`. Chep len VPS va bat:

```bash
scp -r deploy/nginx/* <user>@<ip>:/tmp/
ssh <user>@<ip>
sudo cp /tmp/*.conf /tmp/p150-proxy.inc /etc/nginx/conf.d/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

Ba file:

| File | Viec |
|---|---|
| `evadvisor150.conf` | vhost prod (8000/3000) va staging (8001/3001) |
| `p150-proxy.inc` | phan proxy dung chung — sua mot cho, ca bon location doi theo |
| `00-default-deny.conf` | `default_server` tra 444 |

`00-default-deny.conf` bit lo cua ban ghi wildcard `*` tren DNS: moi subdomain
deu tro ve IP nay, nen khong co no thi mot ten bat ky (`admin.`, `abc.`) se roi
vao vhost dau tien nginx tim thay — tuc la prod.

Frontend va backend dung CHUNG mot domain, backend nam duoi `/api/`. Khong tach
`api.evadvisor150.id.vn` rieng: cung origin thi cookie phien cua Auth khong phai
vuot qua rang buoc `SameSite`, va CORS thanh chuyen khong ton tai.

Hai thu trong `p150-proxy.inc` de mac dinh la hong: `proxy_buffering off` (khong
thi SSE bi gom lai, man chat dung im vai chuc giay roi hien tron ven — nhin nhu
treo) va `proxy_read_timeout 300s` (mot luot co nhieu lan goi LLM, mac dinh 60s
cat ngang giua chung).

Chung chi — chay SAU khi cac file tren da vao cho, vi certbot doc `server_name`
de biet xin cho ten nao:

```bash
sudo certbot --nginx \
  -d evadvisor150.id.vn \
  -d www.evadvisor150.id.vn \
  -d dev.evadvisor150.id.vn
```

**Tro A record ve IP VPS TRUOC khi chay certbot.** Certbot xac thuc bang cach
goi nguoc lai domain; DNS chua lan thi no do, va `.id.vn` co khi lan cham vai
tieng. Kiem bang `dig +short evadvisor150.id.vn` truoc.

Tuong lua: chi mo 22, 80, 443 (`vps_bootstrap.sh` da dat). Postgres va MinIO
khong publish cong ra host, con backend/frontend chi bind `127.0.0.1`.

## 5. Lan deploy dau

Push vao `develop` (hoac bam `Run workflow`) la workflow tu chay. Sau khi
container len, **seed mot lan bang tay**:

```bash
cd ~/p150-prod
docker compose --env-file .env -f docker-compose.prod.yml \
  exec backend /app/scripts/seed_all.sh
```

Seed **khong** chay tu dong luc khoi dong (`SEED_ON_START` mac dinh `false`):
cac script seed ghi de tu file trong `data-p150/`, nen chay lai moi lan restart
se dam len du lieu that. May dev van seed tu dong — `docker-compose.yml` bat co
do.

Migration thi nguoc lai: chay moi lan khoi dong, va **do la fail cung**
(`MIGRATE_LENIENT=false`). Schema hong ma app van len la kieu hong am tham nhat.

## 6. Backup

```bash
# crontab -e
0 3 * * * cd ~/p150-prod && docker compose --env-file .env -f docker-compose.prod.yml \
  exec -T postgres pg_dump -U p150 p150 | gzip > ~/backups/p150-$(date +\%F).sql.gz
0 4 * * 0 find ~/backups -name 'p150-*.sql.gz' -mtime +30 -delete
```

Volume `minio_data` backup rieng (`docker run --rm -v p150prod_minio_data:/d ...`).

## 7. Rollback

Image tag theo commit SHA, nen quay lai la doi tag:

```bash
cd ~/p150-prod
BACKEND_IMAGE=ghcr.io/ai20k-build-phase-cohort-3/p150-backend:<sha-cu> \
FRONTEND_IMAGE=ghcr.io/ai20k-build-phase-cohort-3/p150-frontend:<sha-cu> \
docker compose --env-file .env -f docker-compose.prod.yml up -d
```

Migration **khong tu rollback**. Neu ban loi co migration, phai `alembic
downgrade` bang tay truoc.

## Rang buoc phai nho

- **Chi mot container backend.** `TurnEventBroker` la ban in-memory
  (`src/agents/services/operations/turn_events.py`), nen khong `--workers`,
  khong `--scale backend=2`. Muon scale ngang phai doi sang Redis pub/sub truoc.
- **`NEXT_PUBLIC_DEMO_MODE` phai la `false` tren prod.** Mac dinh cua
  `role-guard.tsx` la BAT khi bien nay khac chuoi `"false"`, va khi bat thi moi
  chan quyen deu di qua. Workflow da ghim cung `false` luc build.
