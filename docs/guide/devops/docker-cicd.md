---
title: "Docker & CI/CD"
description: "Setup Docker và GitHub Actions"
weight: 1
---

## Docker

### Multi-stage Dockerfile

```dockerfile
# Stage 1: Build
FROM python:3.11-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# Stage 2: Production
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH
COPY . .
RUN mkdir -p /app/data
EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Commands

```bash
docker build -t ai20k-app .
docker compose up -d
docker compose logs -f backend
docker compose down
```

## CI/CD (GitHub Actions)

CI tự chạy khi push lên GitHub:

1. **Lint** — `ruff check` đảm bảo code style
2. **Test** — `pytest` chạy tất cả tests
3. Pass → merge được. Fail → fix trước.

### Setup CI

File `.github/workflows/ci.yml` đã có sẵn trong template.

### Yêu cầu minimum

- ✅ CI pipeline phải chạy được
- ✅ Ruff lint pass
- ✅ Tất cả tests pass

## Environment Variables

```bash
# .env.example — commit được (template)
# .env — KHÔNG BAO GIỜ commit (actual values)
```

## Git Workflow

```
main (production)
  └── develop (daily work)
       ├── feature/agent-flow
       ├── feature/api-routes
       └── feature/ui
```

### Commit Messages

```
feat: thêm agent graph với nodes analyze + respond
fix: sửa lỗi CORS blocked trên frontend
docs: cập nhật architecture diagram
test: thêm test cho chat endpoint
refactor: tách analyze node thành file riêng
```
