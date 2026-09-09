"""Executable contracts for Auth CI, architecture, and container gates."""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CI_WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml"
DOCKERFILE = REPOSITORY_ROOT / "Dockerfile"
AUTH_ROOT = REPOSITORY_ROOT / "src" / "auth"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_ci_uses_locked_install_and_pinned_postgresql_major() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    # Ghim ĐÚNG major 16, nhưng không ghim đúng một image.
    #
    # CI đổi sang `pgvector/pgvector:pg16` vì migration của `document`/`images`
    # tạo cột vector, mà Postgres trần trả `extension "vector" is not available`
    # — 262 lỗi thu hồi hết chỉ vì đổi image. Cái cần gác là SỐ MAJOR: nâng lên
    # 17 sau lưng thì test phải đỏ.
    assert "image: postgres:16" in workflow or "image: pgvector/pgvector:pg16" in workflow
    assert "uv sync --locked" in workflow
    assert "uv lock --check" in workflow


def test_ci_runs_auth_migration_enabled_and_legacy_disabled_suites() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "alembic -c alembic-auth.ini upgrade head" in workflow
    # Bốn migration còn lại. Thiếu chúng thì bước full suite chạy trên một CSDL
    # không có bảng `vehicles`, hàng loạt test integration đỏ vì cấu hình chứ
    # không phải vì code — và một cổng gác báo động giả thì người ta bỏ qua nó.
    for ini in ("alembic-products.ini", "alembic-locations.ini", "alembic-document.ini", "alembic-agent.ini"):
        assert ini in workflow
    assert "AGENT_DATABASE_URL" in workflow
    assert 'AUTH_ENABLED: "true"' in workflow
    assert "uv run pytest tests/auth" in workflow
    assert "AUTH_ENABLED=false uv run pytest tests/test_api/test_routes.py" in workflow


def test_ci_gates_pull_requests_into_develop_as_well_as_main() -> None:
    """Git flow là `feature/* -> develop -> main`, nên `develop` là nơi code lạ
    vào ĐẦU TIÊN. Chỉ gác `main` nghĩa là regression đã nằm trong `develop` rồi
    CI mới chạy — lúc đó nó không chặn được gì nữa, chỉ báo tin."""

    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "branches: [main, develop]" in workflow


def test_ci_runs_architecture_audit_and_container_smoke() -> None:
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "test_ci_gates.py" in workflow
    assert "uv run pip-audit" in workflow
    assert "docker build --no-cache -t p150-auth-mvp ." in workflow
    assert "import sqlalchemy, asyncpg, alembic, argon2, jwt" in workflow
    assert "from src.auth.infrastructure.email import SendGridEmailSender" in workflow
    assert "import src.main" in workflow


def test_docker_runtime_installs_from_the_locked_project() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "COPY pyproject.toml uv.lock ./" in dockerfile
    assert "uv sync --locked --no-dev" in dockerfile
    assert "requirements.txt" not in dockerfile


def test_auth_domain_and_application_imports_point_inward() -> None:
    forbidden_domain_prefixes = (
        "fastapi",
        "sqlalchemy",
        "alembic",
        "sendgrid",
        "src.auth.application",
        "src.auth.infrastructure",
        "src.auth.presentation",
    )
    forbidden_application_prefixes = (
        "fastapi",
        "sqlalchemy",
        "alembic",
        "sendgrid",
        "src.auth.infrastructure",
        "src.auth.presentation",
    )

    violations: list[str] = []
    for layer, forbidden in (
        ("domain", forbidden_domain_prefixes),
        ("application", forbidden_application_prefixes),
    ):
        for path in sorted((AUTH_ROOT / layer).glob("*.py")):
            for module in sorted(_imported_modules(path)):
                if module.startswith(forbidden):
                    violations.append(f"{path.relative_to(REPOSITORY_ROOT)} imports {module}")

    assert violations == []
