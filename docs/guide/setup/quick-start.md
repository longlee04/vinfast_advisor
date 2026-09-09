---
title: "Quick Start"
description: "Khởi tạo project trong 5 phút"
weight: 1
---

## Quick Start Guide

### Bước 1: Clone Template

```bash
git clone https://github.com/AI20K-Build-Cohort-2/starter-code-template.git C2-App-XXX
cd C2-App-XXX
```

### Bước 2: Environment Setup

```bash
# Cài uv (nếu chưa có)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Tạo venv + cài dependencies từ uv.lock
uv sync

# Tạo .env từ template
cp .env.example .env
# → Mở .env và điền API keys
```

### Bước 3: Verify Setup

```bash
# Chạy server
uv run uvicorn src.main:app --reload

# Mở browser: http://localhost:8000/docs
# → Phải thấy Swagger UI
```

### Bước 4: Git Setup

```bash
# Đổi remote origin sang repo của team
git remote set-url origin https://github.com/AI20K-Build-Cohort-2/C2-App-XXX.git

# Tạo branch develop
git checkout -b develop

# Push lần đầu
git push -u origin develop
```

## Folder Structure

```
C2-App-XXX/
├── src/                    ← Source code chính
│   ├── agents/             ← LangGraph agents
│   │   ├── graph.py        ← Graph definition
│   │   ├── state.py        ← State schema
│   │   ├── nodes/          ← Processing nodes
│   │   └── tools/          ← Agent tools
│   ├── api/                ← FastAPI routes
│   ├── models/             ← Pydantic schemas
│   ├── services/           ← Business logic
│   ├── config.py           ← Settings
│   └── main.py             ← App entry point
├── tests/                  ← Test suite
├── docs/                   ← Documentation
├── eval/                   ← Evaluation results
├── presentation/           ← Demo materials
├── Dockerfile              ← Multi-stage build
├── docker-compose.yml      ← Full stack
└── .github/workflows/      ← CI/CD
```

## Nguyên tắc tổ chức code

1. **Một file một trách nhiệm** — `graph.py` chỉ build graph, `state.py` chỉ định nghĩa state
2. **Nodes vào folder `nodes/`** — Mỗi node là một file riêng
3. **Tools vào folder `tools/`** — Mỗi tool là một file riêng
4. **API routes tách riêng** — Không trộn logic vào main.py
5. **Config centralized** — Tất cả settings trong `config.py`
