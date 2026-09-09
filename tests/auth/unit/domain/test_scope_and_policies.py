"""Unit tests for Role × Permission × Scope evaluation and domain policies."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from src.auth.domain.audit import (
    log_admin_override,
    log_authorization_denied,
    log_hitl_claim_conflict,
    log_hitl_lease_expired,
    log_websocket_auth_denied,
)
from src.auth.domain.authorization import (
    AdvisorAssignmentPolicy,
    CustomerOwnershipPolicy,
    HITLClaimPolicy,
    Permission,
    Role,
    Scope,
    evaluate_authorization,
)


class TestCustomerOwnershipPolicy:
    def test_customer_allowed_own_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.CUSTOMER,
            permission=Permission.CONVERSATION_VIEW_OWN,
            scope=Scope.OWN,
            actor_id="cust-1",
            resource_owner_id="cust-1",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.OWN

    def test_customer_denied_other_customer_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.CUSTOMER,
            permission=Permission.CONVERSATION_VIEW_OWN,
            scope=Scope.OWN,
            actor_id="cust-1",
            resource_owner_id="cust-2",
        )
        assert decision.allowed is False
        assert decision.reason == "RESOURCE_OWNED_BY_ANOTHER_CUSTOMER"

    def test_customer_denied_missing_actor_or_resource_owner(self) -> None:
        decision = evaluate_authorization(
            role=Role.CUSTOMER,
            permission=Permission.CONVERSATION_VIEW_OWN,
            scope=Scope.OWN,
            actor_id=None,
            resource_owner_id="cust-1",
        )
        assert decision.allowed is False
        assert decision.reason == "MISSING_IDENTITY_OR_OWNER"

    def test_admin_has_global_access_to_customer_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.ADMIN,
            permission=Permission.CONVERSATION_VIEW_OWN,
            scope=Scope.OWN,
            actor_id="admin-1",
            resource_owner_id="cust-2",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.GLOBAL


class TestAdvisorAssignmentPolicy:
    def test_advisor_allowed_assigned_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.CONVERSATION_VIEW_ASSIGNED,
            scope=Scope.ASSIGNED,
            actor_id="adv-1",
            assigned_advisor_id="adv-1",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.ASSIGNED

    def test_advisor_denied_other_advisor_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.CONVERSATION_VIEW_ASSIGNED,
            scope=Scope.ASSIGNED,
            actor_id="adv-1",
            assigned_advisor_id="adv-2",
        )
        assert decision.allowed is False
        assert decision.reason == "RESOURCE_ASSIGNED_TO_ANOTHER_ADVISOR"

    def test_advisor_denied_missing_actor_id(self) -> None:
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.CONVERSATION_VIEW_ASSIGNED,
            scope=Scope.ASSIGNED,
            actor_id=None,
            assigned_advisor_id="adv-1",
        )
        assert decision.allowed is False
        assert decision.reason == "MISSING_STAFF_IDENTITY"

    def test_admin_has_global_access_to_advisor_resource(self) -> None:
        decision = evaluate_authorization(
            role=Role.ADMIN,
            permission=Permission.CONVERSATION_VIEW_ASSIGNED,
            scope=Scope.ASSIGNED,
            actor_id="admin-1",
            assigned_advisor_id="adv-2",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.GLOBAL


class TestHITLClaimPolicy:
    def test_advisor_allowed_valid_claim_and_lease(self) -> None:
        now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
        lease_expires = now + timedelta(minutes=15)
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.HITL_RESOLVE,
            scope=Scope.CLAIMED,
            actor_id="adv-1",
            claimed_by="adv-1",
            lease_expires_at=lease_expires,
            now=now,
            ticket_status="PENDING",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.CLAIMED

    def test_advisor_denied_when_claimed_by_other(self) -> None:
        now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
        lease_expires = now + timedelta(minutes=15)
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.HITL_RESOLVE,
            scope=Scope.CLAIMED,
            actor_id="adv-1",
            claimed_by="adv-2",
            lease_expires_at=lease_expires,
            now=now,
            ticket_status="PENDING",
        )
        assert decision.allowed is False
        assert decision.reason == "TICKET_CLAIMED_BY_ANOTHER_ADVISOR"

    def test_advisor_denied_when_lease_expired(self) -> None:
        now = datetime(2026, 8, 23, 10, 20, tzinfo=UTC)
        lease_expires = now - timedelta(minutes=5)
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.HITL_RESOLVE,
            scope=Scope.CLAIMED,
            actor_id="adv-1",
            claimed_by="adv-1",
            lease_expires_at=lease_expires,
            now=now,
            ticket_status="PENDING",
        )
        assert decision.allowed is False
        assert decision.reason == "TICKET_LEASE_EXPIRED"

    def test_advisor_denied_when_ticket_not_pending(self) -> None:
        now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
        decision = evaluate_authorization(
            role=Role.ADVISOR,
            permission=Permission.HITL_RESOLVE,
            scope=Scope.CLAIMED,
            actor_id="adv-1",
            claimed_by="adv-1",
            lease_expires_at=now + timedelta(minutes=15),
            now=now,
            ticket_status="APPROVED",
        )
        assert decision.allowed is False
        assert decision.reason == "TICKET_NOT_IN_PENDING_STATE"

    def test_admin_can_override_hitl(self) -> None:
        now = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
        decision = evaluate_authorization(
            role=Role.ADMIN,
            permission=Permission.HITL_RESOLVE,
            scope=Scope.CLAIMED,
            actor_id="admin-1",
            claimed_by="adv-2",
            lease_expires_at=now - timedelta(minutes=5),
            now=now,
            ticket_status="PENDING",
        )
        assert decision.allowed is True
        assert decision.scope == Scope.GLOBAL


class TestSecurityAuditLogging:
    def test_log_authorization_denied_formats_json(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="auth.security.audit"):
            log_authorization_denied(
                actor_id="cust-1",
                role=Role.CUSTOMER,
                permission=Permission.HITL_RESOLVE,
                resource_type="review_queue",
                resource_id="123",
                scope=Scope.CLAIMED,
                reason="ROLE_NOT_PERMITTED",
            )
        assert len(caplog.records) == 1
        assert "AUTHORIZATION_DENIED" in caplog.text
        assert "cust-1" in caplog.text
        assert "ROLE_NOT_PERMITTED" in caplog.text

    def test_direct_policy_invocations(self) -> None:
        dec1 = CustomerOwnershipPolicy.evaluate(
            Role.CUSTOMER, Permission.CONVERSATION_VIEW_OWN, actor_id="c1", resource_customer_id="c1"
        )
        assert dec1.allowed is True
        dec2 = AdvisorAssignmentPolicy.evaluate(
            Role.ADVISOR, Permission.CONVERSATION_VIEW_ASSIGNED, actor_id="a1", assigned_advisor_id="a1"
        )
        assert dec2.allowed is True
        now = datetime.now(UTC)
        dec3 = HITLClaimPolicy.evaluate(
            Role.ADVISOR,
            Permission.HITL_RESOLVE,
            actor_id="a1",
            claimed_by="a1",
            lease_expires_at=now + timedelta(minutes=15),
            now=now,
            status="PENDING",
        )
        assert dec3.allowed is True

    def test_log_audit_helpers(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="auth.security.audit"):
            log_hitl_claim_conflict(
                actor_id="adv-1", review_id="rev-1", claimed_by="adv-2", lease_expires_at=datetime.now(UTC)
            )
            log_hitl_lease_expired(actor_id="adv-1", review_id="rev-1", lease_expires_at=datetime.now(UTC))
            log_websocket_auth_denied(
                actor_id="adv-1", role=Role.ADVISOR, conversation_id="conv-1", reason="UNAUTHORIZED"
            )
        with caplog.at_level(logging.INFO, logger="auth.security.audit"):
            log_admin_override(
                actor_id="admin-1", action="APPROVE_REVIEW", resource_type="review_queue", resource_id="rev-1"
            )
        assert "HITL_CLAIM_CONFLICT" in caplog.text
        assert "HITL_LEASE_EXPIRED" in caplog.text
        assert "WEBSOCKET_AUTH_DENIED" in caplog.text
        assert "ADMIN_OVERRIDE" in caplog.text
