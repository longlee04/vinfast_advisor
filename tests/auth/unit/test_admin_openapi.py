"""OpenAPI contract tests for administrative Auth routes."""

from src.main import app


def test_admin_routes_publish_exact_method_map_without_legacy_paths() -> None:
    """Given app routes, when OpenAPI is generated, then only current admin methods exist."""
    paths = app.openapi()["paths"]
    expected_methods = {
        "/api/v1/auth/admin/users": {"get"},
        "/api/v1/auth/admin/users/{user_id}/role": {"patch"},
        "/api/v1/auth/admin/users/{user_id}/disable": {"post"},
        "/api/v1/auth/admin/users/{user_id}/enable": {"post"},
    }

    assert {
        path: {method for method in paths[path] if method in {"get", "post", "patch", "delete"}}
        for path in expected_methods
    } == expected_methods
    assert "/api/v1/admin/users" not in paths
    assert "/api/v1/admin/users/{user_id}" not in paths
    assert "delete" not in paths["/api/v1/auth/admin/users/{user_id}/disable"]
