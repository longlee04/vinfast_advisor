"""[A0-3] Cưỡng chế luật phụ thuộc một chiều mục 6.5b: `domain/`/`tools/` là tầng thuần.

Cùng khuôn `tests/auth/integration/test_ci_gates.py::
test_auth_domain_and_application_imports_point_inward` — parse AST thay vì chạy
import, để bắt được cả import không dùng tới.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
AGENTS_ROOT = REPOSITORY_ROOT / "src" / "agents"

FORBIDDEN_PURE_LAYER_PREFIXES = (
    "fastapi",
    "sqlalchemy",
    "langgraph",
    "langchain",
    "openai",
    "alembic",
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def _violations(layer_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(layer_dir.glob("*.py")):
        for module in sorted(_imported_modules(path)):
            if module.startswith(FORBIDDEN_PURE_LAYER_PREFIXES):
                violations.append(f"{path.relative_to(REPOSITORY_ROOT)} imports {module}")
    return violations


def test_domain_does_not_import_framework() -> None:
    assert _violations(AGENTS_ROOT / "domain") == []


def test_tools_does_not_import_framework() -> None:
    assert _violations(AGENTS_ROOT / "tools") == []
