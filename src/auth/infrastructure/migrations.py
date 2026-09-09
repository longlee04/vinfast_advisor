"""Alembic head resolution for the Auth schema.

Startup needs to know which revision the code expects, not merely that *some*
revision was applied. Todo 1 could only check the latter because no Auth history
existed yet; with the history in place, a database sitting on an older but valid
revision must fail startup too — its schema does not match the models the code
was written against.

The head is read from `alembic-auth.ini` rather than hardcoded, so adding a
revision cannot leave a stale constant behind.
"""

from functools import lru_cache
from pathlib import Path
from typing import Final

from alembic.config import Config
from alembic.script import ScriptDirectory

AUTH_ALEMBIC_INI: Final[str] = "alembic-auth.ini"


def _repository_root() -> Path:
    # src/auth/infrastructure/migrations.py -> repository root
    return Path(__file__).resolve().parents[3]


@lru_cache
def expected_auth_head() -> str:
    """Return the single expected Auth head revision.

    Raises if the history has branched. A branched Auth history would make
    "migrated" ambiguous, and resolving that ambiguity silently is worse than
    refusing to start.
    """
    config_path = _repository_root() / AUTH_ALEMBIC_INI
    if not config_path.is_file():
        raise RuntimeError(f"Auth Alembic configuration not found at {AUTH_ALEMBIC_INI}")

    config = Config(str(config_path))
    script_location = config.get_main_option("script_location")
    if script_location and not Path(script_location).is_absolute():
        config.set_main_option("script_location", str(_repository_root() / script_location))

    heads = ScriptDirectory.from_config(config).get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"Auth migration history must have exactly one head, found {len(heads)}: "
            f"{', '.join(sorted(heads)) or '(none)'}"
        )
    return heads[0]
