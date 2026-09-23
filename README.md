# VinFast AI Sales Advisor

Trợ lý bán hàng AI cho xe VinFast: **Agentic RAG dạng orchestrated workflow**, có
human-in-the-loop và multi-source retrieval. Frontend Next.js gọi REST API của
FastAPI; backend điều phối agent bằng LangGraph; toàn bộ dữ liệu nghiệp vụ và
vector nằm trên một PostgreSQL duy nhất nhờ pgvector.

> Đây là bản cá nhân, tách ra từ dự án nhóm P-150 (VinUni AI20K Build Phase).
> Phần hạ tầng riêng của lớp học (hook log AI, tài liệu phân công, slide) đã
> được gỡ bỏ; phần sản phẩm giữ nguyên.

## Kiến trúc ngắn gọn

| Layer | Công nghệ |
|---|---|
| Frontend | Next.js + Tailwind CSS (`frontend/`) |
| Backend | FastAPI + Uvicorn, Python 3.11, quản lý bằng `uv` |
| Agent | LangGraph + LangChain (`src/agents/`) |
| Database | PostgreSQL 16 + pgvector |
| ORM & migration | SQLAlchemy 2 async (asyncpg) + Alembic (5 file `alembic-*.ini`) |
| Embedding | API provider qua `langchain-openai`, sau `EmbeddingPort` |
| Object storage | MinIO (S3-compatible), bucket private |
| Testing | pytest + pytest-asyncio, ruff, mypy, pip-audit |

Truy hồi tài liệu dùng hybrid search (dense pgvector + lexical full-text) hợp
nhất bằng RRF (k=60). Chi tiết: [ARCHITECTURE.md](ARCHITECTURE.md).

## Cấu trúc thư mục

```
src/
├── main.py           # FastAPI app + lifespan + wiring
├── config.py         # Pydantic settings
├── cli.py            # CLI bootstrap (create-admin, create-staff)
├── agents/           # LangGraph agent: core, domain, ports, adapters, tools, prompts
├── api/              # Router /api/v1
├── auth/             # Module Auth (domain / application / infrastructure)
├── document/         # Ingest tài liệu, chunk, embed, hybrid search
├── products/         # Catalog xe, biến thể, giá
├── locations/        # Đại lý, xưởng dịch vụ, tìm điểm gần
├── images/           # Ảnh sản phẩm trên MinIO
├── models/           # SQLAlchemy models dùng chung
└── services/         # LLM service

frontend/             # Next.js app
migrations/           # Alembic versions cho từng module
tests/                # pytest, tách theo module
eval/                 # Bộ đánh giá agent (offline, deterministic)
crawl/                # Script thu thập dữ liệu VinFast
data-p150/            # Dữ liệu seed
scripts/              # Seed, migration helper, evaluation runner
docs/                 # Tài liệu thiết kế, ADR, runbook, hướng dẫn
```

## Quick start

```bash
# 1. Cài uv (nếu chưa có)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Cài dependency đúng theo uv.lock
uv sync --locked

# 3. Tạo .env từ mẫu rồi điền OPENAI_API_KEY và các khoá AUTH_*
cp .env.example .env

# 4. Dựng Postgres + MinIO + pgAdmin, chạy migration, seed dữ liệu
make dev-setup

# 5. Chạy API
make run        # http://localhost:8000/docs
```

Hướng dẫn từng bước cho máy mới: [STARTUP_GUIDE.md](STARTUP_GUIDE.md).

## Lệnh thường dùng

```bash
make test        # pytest toàn bộ
make lint        # ruff check src/ tests/
make typecheck   # mypy src/
make check       # lint + format + test

cd frontend && npm ci && npm test && npm run build
```

CI (GitHub Actions) chạy đúng chuỗi này trên Postgres + pgvector và MinIO thật:
[.github/workflows/ci.yml](.github/workflows/ci.yml).

## Tài liệu

- [ARCHITECTURE.md](ARCHITECTURE.md) — kiến trúc hệ thống, sơ đồ, ranh giới module
- [AGENT_FEATURE.md](AGENT_FEATURE.md) — đặc tả tính năng của agent
- [FE.md](FE.md) — quy ước frontend
- [docs/vinfast-agent-mvp.md](docs/vinfast-agent-mvp.md) — phạm vi MVP
- [docs/vehicle-catalog-schema.md](docs/vehicle-catalog-schema.md) — thiết kế dữ liệu catalog
- [docs/runbooks/](docs/runbooks/) — runbook vận hành
- [notes/architecture-learning/](notes/architecture-learning/) — ghi chú đọc mã nguồn

## Authentication MVP

Auth is opt-in and PostgreSQL-only. With `AUTH_ENABLED=false`, the existing health, chat, and agent-status routes keep their legacy behavior and no Auth resources are created.

### Local setup and bootstrap

```bash
cp .env.example .env
uv sync --locked
docker compose up -d postgres
uv run alembic -c alembic-auth.ini upgrade head
uv run python -m src.cli create-admin --email admin@example.com
uv run python -m src.cli create-staff --email advisor@example.com --actor-id <admin-id> --role advisor
uv run uvicorn src.main:app --reload --port 8000
```

The `create-admin` command reads the password and confirmation through secure terminal prompts; there is no password command-line option. Only the first active Admin can be bootstrapped.

### Environment reference

Set `APP_ENV` plus the following `AUTH_*` variables in `.env`. Generate `AUTH_JWT_SIGNING_KEY` and `AUTH_CSRF_SECRET` independently; never commit their values.

| Variable | Purpose |
|---|---|
| `AUTH_ENABLED` | Enables Auth composition and routes. |
| `AUTH_DATABASE_URL` | PostgreSQL async URL using `postgresql+asyncpg://`; SQLite is rejected. |
| `AUTH_JWT_SIGNING_KEY` | High-entropy JWT signing secret. |
| `AUTH_JWT_ALGORITHM` | JWT algorithm: `HS256`, `HS384`, or `HS512`; default `HS256`. |
| `AUTH_JWT_ISSUER` | Required JWT issuer; default `p150-auth`. |
| `AUTH_JWT_AUDIENCE` | Required JWT audience; default `p150-app`. |
| `AUTH_CSRF_SECRET` | High-entropy CSRF secret distinct from the JWT key. |
| `AUTH_CORS_ORIGINS` | Comma-separated exact credentialed origins; no wildcard. |
| `AUTH_FRONTEND_ORIGIN` | Exact frontend origin accepted by mutation endpoints. |
| `AUTH_COOKIE_SECURE` | Must remain `true` in production; local HTTP tests may override it. |
| `AUTH_SENDGRID_API_KEY` | SendGrid credential for verification and recovery email. |
| `AUTH_SENDGRID_FROM_EMAIL` | Verified sender address. |
| `AUTH_REQUIRE_EMAIL_VERIFICATION` | `true` (default) makes customers confirm their mailbox before signing in. Set `false` only while email delivery is unavailable: requiring a link nobody can receive blocks every registration, and an abuse control protects nothing on a product no one can use. While off, anyone can register with someone else's address. |
| `AUTH_CUSTOMER_EMAIL_DOMAINS` | Comma-separated mail domains customers may register with. Empty falls back to the built-in list (`gmail.com`, `outlook.com`, `hotmail.com`, `yahoo.com`, `icloud.com`), so a typo cannot silently open registration to every domain. The same list gates login, so widen it freely but never narrow it: dropping a domain locks out existing customers who use it. |
| `AUTH_LOGIN_RATE_LIMIT_ATTEMPTS` | Login attempts per bounded window; default `5`. |
| `AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS` | Login window; default `900`. |
| `AUTH_RECOVERY_RATE_LIMIT_ATTEMPTS` | Recovery attempts per bounded window; default `3`. |
| `AUTH_RECOVERY_RATE_LIMIT_WINDOW_SECONDS` | Recovery window; default `3600`. |

### HTTP endpoints

All endpoints are under `/api/v1/auth` and return `Cache-Control: no-store`.

| Method | Endpoint | Shipped behavior |
|---|---|---|
| POST | `/api/v1/auth/register` | Register a Gmail CUSTOMER with a generic response. |
| POST | `/api/v1/auth/login` | Authenticate and set session cookies. |
| POST | `/api/v1/auth/verify` | Consume an email-verification token; verification is POST-only. |
| POST | `/api/v1/auth/resend-verification` | Send the latest verification token with a generic response. |
| POST | `/api/v1/auth/refresh` | Rotate the refresh token and session cookies. |
| POST | `/api/v1/auth/logout` | Revoke the current session. |
| POST | `/api/v1/auth/logout-all` | Revoke every session for the current user. |
| GET | `/api/v1/auth/me` | Return the current authenticated account. |
| POST | `/api/v1/auth/change-password` | Change the current password and revoke sessions. |
| POST | `/api/v1/auth/forgot-password` | Start recovery with equivalent known/unknown-account responses. |
| POST | `/api/v1/auth/reset-password` | Consume the latest reset token and revoke all sessions. |
| POST | `/api/v1/auth/staff` | ADMIN-only creation of an ADVISOR or ADMIN with a server-generated temporary password sent through the configured email sender; requests accept only `email` and `role`. |
| POST | `/api/v1/auth/staff/login` | Authenticate a staff account and set session cookies. |
| POST | `/api/v1/auth/staff/complete-password` | Replace a temporary password and issue a session. |
| GET | `/api/v1/auth/admin/users` | ADMIN-only paginated account listing. |
| PATCH | `/api/v1/auth/admin/users/{user_id}/role` | ADMIN-only role change. |
| POST | `/api/v1/auth/admin/users/{user_id}/disable` | ADMIN-only account disable. |
| POST | `/api/v1/auth/admin/users/{user_id}/enable` | ADMIN-only account re-enable. |

Staff accounts with an expired temporary password remain recoverable through the
enumeration-safe `forgot-password` and `reset-password` endpoints. A successful
reset transitions `TEMPORARY_PASSWORD` to `ACTIVE`, revokes all refresh sessions,
and requires a fresh login; disabled accounts remain ineligible.

### Token, cookie, CSRF, role, and state contracts

Token lifetimes are fixed in seconds: access `900`, refresh-family absolute expiry `2592000`, email verification `86400`, password reset `3600`, and temporary password `86400`.

| Cookie | Path | Attributes |
|---|---|---|
| `__Host-p150_access` | `/` | Secure, HttpOnly, SameSite=Lax, host-only with no Domain attribute. |
| `__Secure-p150_refresh` | `/api/v1/auth` | Secure, HttpOnly, SameSite=Lax, host-only with no Domain attribute. |
| `__Host-p150_csrf` | `/` | Secure, readable by the client, SameSite=Lax, host-only with no Domain attribute. |

Cookie-authenticated mutations require the CSRF cookie value in the `X-CSRF-Token` header. Missing or mismatched values are rejected before mutation.

Roles are `CUSTOMER`, `ADVISOR`, and `ADMIN`. Account states are `PENDING_VERIFICATION`, `TEMPORARY_PASSWORD`, `ACTIVE`, and `DISABLED`. Authorization is default-deny; ADMIN-only account management cannot disable the last active Admin.

### Deferred hardening

The MVP does not ship OAuth, MFA, backup/restore or RPO/RTO automation, multi-replica key rotation and rollout, previous-key grace, frontend flows, fuzz/performance suites, or production deployment guarantees. These remain separate hardening work and are not implied by the commands above.

## License

MIT.
