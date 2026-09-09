"""Safe rollout defaults for reviewed policy retrieval."""

from src.config import Settings


def test_policy_rag_is_opt_in_until_reviewed_corpus_exists() -> None:
    settings = Settings(_env_file=None)

    assert settings.policy_rag_enabled is False


def test_policy_rag_can_be_enabled_explicitly() -> None:
    settings = Settings(_env_file=None, policy_rag_enabled=True)

    assert settings.policy_rag_enabled is True
