"""SQLAlchemy adapter for Customer Assignment and Conversation Reassignment management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import desc, func, select, update

from src.agents.models import (
    ConversationReassignmentRow,
    ConversationSessionRow,
    CustomerAdvisorAssignmentRow,
    CustomerProfileRow,
)
from src.agents.ports import ClockPort


@dataclass(frozen=True, slots=True)
class CustomerAssignmentDto:
    """Read DTO for a customer assignment record."""

    assignment_id: UUID
    customer_id: str
    advisor_id: str
    assigned_by: str
    reason: str | None
    status: str
    assigned_at: datetime
    unassigned_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AssignedCustomerSummaryDto:
    """Summary DTO of an assigned customer for the advisor view."""

    customer_id: str
    advisor_id: str
    assigned_at: datetime
    reason: str | None
    status: str
    profile_payload: dict
    active_conversations_count: int
    last_activity_at: datetime | None


class SqlAlchemyCustomerAssignmentRepository:
    """Persist and query customer assignments and conversation reassignments inside a transaction."""

    def __init__(self, session, clock: ClockPort) -> None:
        self._session = session
        self._clock = clock

    async def assign_customer(
        self,
        customer_id: str,
        advisor_id: str,
        assigned_by: str,
        reason: str | None = None,
    ) -> UUID:
        """Atomically deactivate any existing active assignment and create a new active assignment."""
        now = self._clock.now()

        # Deactivate existing active assignments for this customer
        await self._session.execute(
            update(CustomerAdvisorAssignmentRow)
            .where(
                CustomerAdvisorAssignmentRow.customer_id == customer_id,
                CustomerAdvisorAssignmentRow.status == "ACTIVE",
            )
            .values(
                status="TRANSFERRED",
                unassigned_at=now,
                updated_at=now,
            )
        )

        assignment_id = uuid4()
        new_row = CustomerAdvisorAssignmentRow(
            assignment_id=assignment_id,
            customer_id=customer_id,
            advisor_id=advisor_id,
            assigned_by=assigned_by,
            reason=reason,
            status="ACTIVE",
            assigned_at=now,
            unassigned_at=None,
            created_at=now,
            updated_at=now,
        )
        self._session.add(new_row)
        await self._session.flush()
        return assignment_id

    async def unassign_customer(
        self,
        customer_id: str,
        unassigned_by: str,
        reason: str | None = None,
    ) -> bool:
        """Mark active assignment as UNASSIGNED."""
        now = self._clock.now()
        res = await self._session.execute(
            update(CustomerAdvisorAssignmentRow)
            .where(
                CustomerAdvisorAssignmentRow.customer_id == customer_id,
                CustomerAdvisorAssignmentRow.status == "ACTIVE",
            )
            .values(
                status="UNASSIGNED",
                reason=reason,
                unassigned_at=now,
                updated_at=now,
            )
        )
        await self._session.flush()
        return (res.rowcount or 0) > 0

    async def get_customer_history(self, customer_id: str) -> list[CustomerAdvisorAssignmentRow]:
        """Return all assignment records for a customer in reverse chronological order."""
        stmt = (
            select(CustomerAdvisorAssignmentRow)
            .where(CustomerAdvisorAssignmentRow.customer_id == customer_id)
            .order_by(desc(CustomerAdvisorAssignmentRow.assigned_at))
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_assignments(
        self,
        advisor_id: str | None = None,
        status: str | None = "ACTIVE",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CustomerAdvisorAssignmentRow], int]:
        """List assignments with filtering and pagination for Admin Assignment Center."""
        stmt = select(CustomerAdvisorAssignmentRow)
        count_stmt = select(func.count()).select_from(CustomerAdvisorAssignmentRow)

        if advisor_id:
            stmt = stmt.where(CustomerAdvisorAssignmentRow.advisor_id == advisor_id)
            count_stmt = count_stmt.where(CustomerAdvisorAssignmentRow.advisor_id == advisor_id)
        if status:
            stmt = stmt.where(CustomerAdvisorAssignmentRow.status == status)
            count_stmt = count_stmt.where(CustomerAdvisorAssignmentRow.status == status)

        stmt = stmt.order_by(desc(CustomerAdvisorAssignmentRow.assigned_at)).limit(limit).offset(offset)
        total = (await self._session.scalar(count_stmt)) or 0
        items = list((await self._session.execute(stmt)).scalars().all())
        return items, total

    async def list_assigned_customers_for_advisor(
        self, advisor_id: str, advisor_email: str | None = None
    ) -> list[AssignedCustomerSummaryDto]:
        """List active assigned customers with profile data for an advisor."""
        advisor_identifiers = [advisor_id]
        if advisor_email and advisor_email != advisor_id:
            advisor_identifiers.append(advisor_email)

        assignments = list(
            (
                await self._session.execute(
                    select(CustomerAdvisorAssignmentRow)
                    .where(
                        CustomerAdvisorAssignmentRow.advisor_id.in_(advisor_identifiers),
                        CustomerAdvisorAssignmentRow.status == "ACTIVE",
                    )
                    .order_by(desc(CustomerAdvisorAssignmentRow.assigned_at))
                )
            )
            .scalars()
            .all()
        )

        # Nạp theo LÔ (plan Customer 360, Phase 3): trước đây 2 câu SQL cho MỖI khách.
        customer_ids = {assign.customer_id for assign in assignments}
        profiles = {
            row.customer_id: row
            for row in (
                await self._session.execute(
                    select(CustomerProfileRow).where(CustomerProfileRow.customer_id.in_(customer_ids))
                )
            ).scalars()
        }
        stats = {
            row.customer_id: (row.sessions, row.last_activity_at)
            for row in await self._session.execute(
                select(
                    ConversationSessionRow.customer_id,
                    func.count(ConversationSessionRow.session_id).label("sessions"),
                    func.max(ConversationSessionRow.last_activity_at).label("last_activity_at"),
                )
                .where(ConversationSessionRow.customer_id.in_(customer_ids))
                .group_by(ConversationSessionRow.customer_id)
            )
        }

        results: list[AssignedCustomerSummaryDto] = []
        for assign in assignments:
            prof = profiles.get(assign.customer_id)
            profile_dict: dict = {}
            if prof:
                profile_dict = {
                    "name": prof.display_name or prof.customer_id,
                    "phone": prof.phone or "",
                    "email": prof.email or "",
                }
            conv_count, last_activity = stats.get(assign.customer_id, (0, None))
            results.append(
                AssignedCustomerSummaryDto(
                    customer_id=assign.customer_id,
                    advisor_id=assign.advisor_id,
                    assigned_at=assign.assigned_at,
                    reason=assign.reason,
                    status=assign.status,
                    profile_payload=profile_dict,
                    active_conversations_count=conv_count or 0,
                    last_activity_at=last_activity or assign.assigned_at,
                )
            )
        return results

    async def reassign_conversation(
        self,
        session_id: UUID,
        new_advisor_id: str,
        reassigned_by: str,
        reason: str | None = None,
    ) -> tuple[str | None, str]:
        """Atomically reassign a live chat session to another advisor and log the audit record."""
        stmt = select(ConversationSessionRow).where(ConversationSessionRow.session_id == session_id).with_for_update()
        session_row = (await self._session.execute(stmt)).scalar_one_or_none()
        if session_row is None:
            raise ValueError(f"Conversation session not found: {session_id}")

        previous_advisor_id = session_row.assigned_advisor_id
        now = self._clock.now()

        # Log reassignment history
        reassign_log = ConversationReassignmentRow(
            id=uuid4(),
            session_id=session_id,
            previous_advisor_id=previous_advisor_id,
            new_advisor_id=new_advisor_id,
            reassigned_by=reassigned_by,
            reason=reason,
            created_at=now,
        )
        self._session.add(reassign_log)

        # Update session
        session_row.assigned_advisor_id = new_advisor_id
        session_row.updated_at = now
        await self._session.flush()
        return previous_advisor_id, new_advisor_id
