"""Shared Auth test fixtures.

Auth settings read both `AUTH_*` environment variables and the developer's real
`.env` file. Neither may influence assertions, so every Auth test runs against a
cleared environment and constructs settings with `_env_file=None`.
"""

import os
from collections.abc import Iterator

import pytest

_MANAGED_ENV_PREFIXES = ("AUTH_", "GOOGLE_OAUTH_")
_MANAGED_ENV_NAMES = ("APP_ENV",)


@pytest.fixture(autouse=True)
def isolated_auth_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove ambient Auth configuration so settings tests are deterministic."""
    for name in list(os.environ):
        if name.startswith(_MANAGED_ENV_PREFIXES) or name in _MANAGED_ENV_NAMES:
            monkeypatch.delenv(name, raising=False)
    yield
