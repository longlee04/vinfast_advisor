"""Cấu hình Google OAuth: bật/tắt theo đủ bộ ba biến, không lộ secret.

Ba biến `GOOGLE_OAUTH_*` cố ý KHÔNG mang tiền tố `AUTH_`: tên do Google Cloud
Console cấp và đã nằm sẵn trong `.env` triển khai. Thiếu bất kỳ biến nào thì
tính năng tắt — endpoint trả 404 thay vì chạy nửa vời với cấu hình cụt.
"""

from pathlib import Path

import pytest

from src.auth.settings import AuthSettings

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO_ROOT / ".env.example"

FULL_CONFIG = {
    "google_oauth_client_id": "test-client.apps.googleusercontent.com",
    "google_oauth_client_secret": "GOCSPX-test-secret-value",
    "google_oauth_redirect_url": "https://example.test/api/v1/auth/google/callback",
}


def build(**overrides: object) -> AuthSettings:
    return AuthSettings(_env_file=None, **overrides)


class TestGoogleOAuthToggle:
    def test_disabled_by_default(self) -> None:
        assert build().google_oauth_enabled is False

    def test_enabled_with_full_config(self) -> None:
        assert build(**FULL_CONFIG).google_oauth_enabled is True

    @pytest.mark.parametrize("missing", sorted(FULL_CONFIG))
    def test_partial_config_stays_disabled(self, missing: str) -> None:
        config = {name: value for name, value in FULL_CONFIG.items() if name != missing}
        assert build(**config).google_oauth_enabled is False

    def test_reads_google_environment_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", FULL_CONFIG["google_oauth_client_id"])
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", FULL_CONFIG["google_oauth_client_secret"])
        monkeypatch.setenv("GOOGLE_OAUTH_REDIRECT_URL", FULL_CONFIG["google_oauth_redirect_url"])
        settings = AuthSettings(_env_file=None)
        assert settings.google_oauth_client_id == FULL_CONFIG["google_oauth_client_id"]
        assert settings.google_oauth_redirect_url == FULL_CONFIG["google_oauth_redirect_url"]
        assert settings.google_oauth_enabled is True


class TestGoogleOAuthHygiene:
    def test_secret_never_renders_in_repr(self) -> None:
        settings = build(**FULL_CONFIG)
        assert FULL_CONFIG["google_oauth_client_secret"] not in repr(settings)

    def test_google_fields_stay_out_of_auth_prefixed_parity(self) -> None:
        """`env_configurable_fields` nuôi bài kiểm tra parity `AUTH_*`; ba biến
        Google mang tên riêng nên phải đứng ngoài, kẻo parity đòi một biến
        `AUTH_GOOGLE_...` không tồn tại."""
        for name in AuthSettings.env_configurable_fields():
            assert not name.startswith("google_oauth")

    def test_env_example_documents_google_names(self) -> None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        for name in ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_OAUTH_REDIRECT_URL"):
            assert f"{name}=" in text

    def test_env_example_holds_no_real_google_secret(self) -> None:
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("GOOGLE_OAUTH_CLIENT_SECRET="):
                assert line.split("=", 1)[1] == ""
