import pytest

from src.document.application.authorization import DocumentAction, DocumentAuthorization


def test_unauthorized_actor_action_is_rejected_by_application_policy() -> None:
    policy = DocumentAuthorization(allowed_actor_ids=frozenset({"admin"}))

    with pytest.raises(PermissionError):
        policy.require(actor_id="advisor", action=DocumentAction.CREATE)
