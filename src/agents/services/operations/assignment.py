"""Use-case operations for Customer Assignment and Live Chat Session Reassignment."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from src.agents.adapters.assignment_repository import (
    AssignedCustomerSummaryDto,
    CustomerAssignmentDto,
)
from src.agents.ports import UnitOfWorkPort


@dataclass(frozen=True, slots=True)
class AssignmentOperationResult:
    """Result of an assignment or reassignment action."""

    success: bool
    assignment_id: UUID | None = None
    previous_advisor_id: str | None = None
    new_advisor_id: str | None = None


class AssignmentOperations:
    """Operations boundary for customer assignment management."""

    def __init__(self, unit_of_work: UnitOfWorkPort) -> None:
        self._unit_of_work = unit_of_work

    async def assign_customer(
        self,
        customer_id: str,
        advisor_id: str,
        assigned_by: str,
        reason: str | None = None,
    ) -> UUID:
        """Assign a customer to an advisor with history audit."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.assignments.assign_customer(
                customer_id=customer_id,
                advisor_id=advisor_id,
                assigned_by=assigned_by,
                reason=reason,
            )

    async def unassign_customer(
        self,
        customer_id: str,
        unassigned_by: str,
        reason: str | None = None,
    ) -> bool:
        """Unassign an active customer assignment."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.assignments.unassign_customer(
                customer_id=customer_id,
                unassigned_by=unassigned_by,
                reason=reason,
            )

    async def list_assignments(
        self,
        advisor_id: str | None = None,
        status: str | None = "ACTIVE",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CustomerAssignmentDto], int]:
        """List customer assignments for Admin Assignment Center."""
        async with self._unit_of_work.transaction() as transaction:
            rows, total = await transaction.assignments.list_assignments(
                advisor_id=advisor_id,
                status=status,
                limit=limit,
                offset=offset,
            )
            items = [
                CustomerAssignmentDto(
                    assignment_id=row.assignment_id,
                    customer_id=row.customer_id,
                    advisor_id=row.advisor_id,
                    assigned_by=row.assigned_by,
                    reason=row.reason,
                    status=row.status,
                    assigned_at=row.assigned_at,
                    unassigned_at=row.unassigned_at,
                    created_at=row.created_at,
                )
                for row in rows
            ]
            return items, total

    async def get_customer_history(self, customer_id: str) -> list[CustomerAssignmentDto]:
        """Get assignment history for a customer."""
        async with self._unit_of_work.transaction() as transaction:
            rows = await transaction.assignments.get_customer_history(customer_id)
            return [
                CustomerAssignmentDto(
                    assignment_id=row.assignment_id,
                    customer_id=row.customer_id,
                    advisor_id=row.advisor_id,
                    assigned_by=row.assigned_by,
                    reason=row.reason,
                    status=row.status,
                    assigned_at=row.assigned_at,
                    unassigned_at=row.unassigned_at,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    async def list_assigned_customers(
        self, advisor_id: str, advisor_email: str | None = None
    ) -> list[AssignedCustomerSummaryDto]:
        """Get active customers assigned to an advisor."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.assignments.list_assigned_customers_for_advisor(
                advisor_id=advisor_id, advisor_email=advisor_email
            )

    async def reassign_conversation(
        self,
        session_id: UUID,
        new_advisor_id: str,
        reassigned_by: str,
        reason: str | None = None,
    ) -> tuple[str | None, str]:
        """Reassign a conversation session from one advisor to another."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.assignments.reassign_conversation(
                session_id=session_id,
                new_advisor_id=new_advisor_id,
                reassigned_by=reassigned_by,
                reason=reason,
            )
