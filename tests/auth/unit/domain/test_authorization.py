"""Authorization matrix tests.

Every declared `(role, action)` pair is asserted explicitly, and every undeclared
pair must be denied. The exhaustive sweep is the point: it is what catches a new
action silently becoming reachable.
"""

from typing import cast

import pytest

from src.auth.domain.authorization import (
    PERMISSIONS,
    Action,
    Role,
    assert_not_last_active_admin,
    authorize,
    is_allowed,
)
from src.auth.domain.errors import AuthorizationError, LastAdminProtectedError

SELF_SERVICE = (
    Action.READ_OWN_PROFILE,
    Action.CHANGE_OWN_PASSWORD,
    Action.LIST_OWN_SESSIONS,
    Action.REVOKE_OWN_SESSIONS,
)
ADMIN_ONLY = (
    Action.CREATE_ADVISOR,
    Action.CREATE_ADMIN,
    Action.DISABLE_USER,
    Action.ENABLE_USER,
    Action.REVOKE_OTHER_SESSIONS,
    Action.RESET_OTHER_PASSWORD,
)

DOCUMENT_READERS = (Role.ADMIN, Role.ADVISOR, Role.CUSTOMER)
DOCUMENT_ADMIN_ONLY = (Action.CREATE_DOCUMENT, Action.ARCHIVE_DOCUMENT)


class TestSelfServiceIsAllowedForEveryRole:
    @pytest.mark.parametrize("role", list(Role))
    @pytest.mark.parametrize("action", SELF_SERVICE)
    def test_allowed(self, role: Role, action: Action) -> None:
        assert is_allowed(role, action) is True


class TestAdminOnlyActions:
    @pytest.mark.parametrize("action", ADMIN_ONLY)
    def test_admin_is_allowed(self, action: Action) -> None:
        assert is_allowed(Role.ADMIN, action) is True

    @pytest.mark.parametrize("role", [Role.CUSTOMER, Role.ADVISOR])
    @pytest.mark.parametrize("action", ADMIN_ONLY)
    def test_non_admin_is_denied(self, role: Role, action: Action) -> None:
        assert is_allowed(role, action) is False

    def test_advisor_cannot_create_staff(self) -> None:
        """Advisor is not a junior Admin; it holds no administrative action."""
        assert is_allowed(Role.ADVISOR, Action.CREATE_ADVISOR) is False
        assert is_allowed(Role.ADVISOR, Action.CREATE_ADMIN) is False


class TestDocumentActions:
    def test_all_document_readers_may_read_documents(self) -> None:
        assert all(is_allowed(role, Action.READ_DOCUMENT) for role in DOCUMENT_READERS)

    @pytest.mark.parametrize("action", DOCUMENT_ADMIN_ONLY)
    def test_only_admin_may_create_or_archive_documents(self, action: Action) -> None:
        assert is_allowed(Role.ADMIN, action) is True
        assert is_allowed(Role.ADVISOR, action) is False
        assert is_allowed(Role.CUSTOMER, action) is False

    @pytest.mark.parametrize("action", DOCUMENT_ADMIN_ONLY)
    def test_customer_is_denied_document_mutations(self, action: Action) -> None:
        assert is_allowed(Role.CUSTOMER, action) is False


class TestExhaustiveMatrix:
    @pytest.mark.parametrize("role", list(Role))
    @pytest.mark.parametrize("action", list(Action))
    def test_every_pair_matches_the_declared_table(self, role: Role, action: Action) -> None:
        assert is_allowed(role, action) is (action in PERMISSIONS[role])

    def test_every_role_appears_in_the_table(self) -> None:
        assert set(PERMISSIONS) == set(Role)

    def test_every_action_is_granted_to_at_least_one_role(self) -> None:
        """An action nobody can perform is dead code or a missing grant."""
        granted = set().union(*PERMISSIONS.values())
        assert granted == set(Action)


class TestDefaultDeny:
    def test_undeclared_role_is_denied(self) -> None:
        assert is_allowed(cast(Role, "auditor"), Action.READ_OWN_PROFILE) is False

    def test_undeclared_action_is_denied(self) -> None:
        assert is_allowed(Role.ADMIN, cast(Action, "delete_everything")) is False

    def test_authorize_raises_for_undeclared_pair(self) -> None:
        with pytest.raises(AuthorizationError):
            authorize(Role.CUSTOMER, Action.CREATE_ADMIN)


class TestActorTargetRules:
    def test_admin_may_act_on_another_account(self) -> None:
        authorize(Role.ADMIN, Action.DISABLE_USER, actor_id="admin-1", target_id="user-2")

    @pytest.mark.parametrize(
        "action",
        [Action.DISABLE_USER, Action.ENABLE_USER, Action.REVOKE_OTHER_SESSIONS, Action.RESET_OTHER_PASSWORD],
    )
    def test_admin_may_not_target_itself_with_admin_actions(self, action: Action) -> None:
        with pytest.raises(AuthorizationError, match="target other than the actor"):
            authorize(Role.ADMIN, action, actor_id="admin-1", target_id="admin-1")

    def test_self_service_action_ignores_target_identity(self) -> None:
        authorize(Role.CUSTOMER, Action.CHANGE_OWN_PASSWORD, actor_id="u-1", target_id="u-1")

    def test_denial_message_never_names_the_target(self) -> None:
        """An authorization error must not double as an account-existence oracle."""
        with pytest.raises(AuthorizationError) as exc:
            authorize(Role.CUSTOMER, Action.DISABLE_USER, actor_id="u-1", target_id="victim@gmail.com")
        assert "victim@gmail.com" not in str(exc.value)


class TestLastAdminProtection:
    def test_disabling_the_last_admin_is_refused(self) -> None:
        with pytest.raises(LastAdminProtectedError):
            assert_not_last_active_admin(Action.DISABLE_USER, remaining_active_admins=0)

    def test_disabling_is_allowed_when_another_admin_remains(self) -> None:
        assert_not_last_active_admin(Action.DISABLE_USER, remaining_active_admins=1)

    def test_negative_count_is_also_refused(self) -> None:
        with pytest.raises(LastAdminProtectedError):
            assert_not_last_active_admin(Action.DISABLE_USER, remaining_active_admins=-1)

    def test_unrelated_action_is_unaffected(self) -> None:
        assert_not_last_active_admin(Action.READ_OWN_PROFILE, remaining_active_admins=0)


class TestRoleAndActionAreStrictEnums:
    def test_roles_have_stable_wire_values(self) -> None:
        assert [role.value for role in Role] == ["customer", "advisor", "admin"]

    def test_action_values_are_unique(self) -> None:
        values = [action.value for action in Action]
        assert len(values) == len(set(values))

    def test_no_rank_ordering_is_exposed(self) -> None:
        """Permission must come from the table, never from comparing roles."""
        assert not hasattr(Role, "rank")


def test_only_admin_may_list_users() -> None:
    assert is_allowed(Role.ADMIN, Action.LIST_USERS) is True
    assert is_allowed(Role.ADVISOR, Action.LIST_USERS) is False
    assert is_allowed(Role.CUSTOMER, Action.LIST_USERS) is False
