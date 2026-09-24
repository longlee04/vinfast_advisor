"""[A7-2] Use case hàng đợi duyệt — claim bằng compare-and-set, lease 15 phút.

Service mở/đóng transaction qua unit of work (mục 6.4); repository không tự mở.
Port `claim` trả `bool` (đã đóng băng ở `ports.py`, không đổi chữ ký); service
dịch `bool` đó thành kết quả có lý do rõ ràng, để người thua biết "đã có người
nhận" chứ không nhận một lỗi chung chung.

Service không import SQLAlchemy — nó chỉ thấy các Protocol dưới đây.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from src.agents.domain.comparison import ComparisonTable
from src.agents.domain.conversation_memory import TurnOutcomeStatus
from src.agents.domain.customer_profile import OfferState, ProfileSnapshot
from src.agents.domain.offer_reply import advisor_still_looking_notice, offer_announcement
from src.agents.domain.post_pitch import (
    PostPitchStage,
    after_offer,
    after_offer_granted,
    chosen_vehicle,
    stage_of,
    vehicle_price,
)
from src.agents.domain.task_state import ActiveTask
from src.agents.logging import get_agent_logger
from src.agents.ports import BottleneckSignalRepository, OfferSuggestionPort, VehicleImageSource
from src.agents.services.operations.comparison_image import (
    ComparisonImageStore,
    render_comparison_image_or_none,
)
from src.agents.services.operations.turn_events import TurnEvent, TurnEventBroker
from src.agents.services.output_guard import customer_safe_answer
from src.agents.services.profile_snapshot import ProfileSnapshotService
from src.products.application.offer_adjustment_service import (
    OfferAdjustment,
    OfferAdjustmentAuditLog,
    OfferAdjustmentOutOfBoundsError,
    OfferAdjustmentPolicy,
    OfferAdjustmentService,
    OfferAdjustmentSource,
    OfferAdjustmentSourceKind,
)
from src.products.application.offer_adjustment_service import (
    PromotionExpiredError as OfferPromotionExpiredError,
)

__all__ = ["OfferPromotionExpiredError", "ReviewOperations"]

logger = get_agent_logger("agent.services.review")

DEFAULT_LEASE_MINUTES = 15

#: Trạng thái duy nhất được phép gửi nội dung cho khách.
DELIVERABLE_STATUSES = frozenset({"APPROVED", "EDITED"})

#: Bộ lọc màn hàng đợi → trạng thái thật trong bảng. `approved` gộp cả `EDITED`
#: vì với tư vấn viên "đã duyệt" và "sửa rồi duyệt" là một kết quả.
QUEUE_STATUS_FILTERS: dict[str, tuple[str, ...]] = {
    "pending": ("PENDING",),
    "approved": ("APPROVED", "EDITED"),
    "rejected": ("REJECTED",),
}

#: Bao lâu một bản nháp được phép nằm `PENDING` trước khi coi như lỡ hẹn.
DEFAULT_PENDING_SLA_MINUTES = 60

#: Câu khách nhận thay cho bản nháp chưa ai duyệt — không lộ nội dung nội bộ.
EXPIRED_CUSTOMER_MESSAGE = "Hệ thống xin lỗi, phản hồi đã quá hạn — anh/chị có thể hỏi lại"

_DIGITS = re.compile(r"\d")


def pending_sla_minutes(env: Mapping[str, str] | None = None) -> int:
    """Ngưỡng quá hạn đọc từ `HITL_PENDING_SLA_MINUTES`, mặc định 60 phút.

    Cấu hình hỏng (không phải số, hoặc ≤ 0) không được biến mọi mục vừa vào
    hàng đợi thành quá hạn: rơi về mặc định thay vì tin giá trị vô nghĩa.
    """
    source = os.environ if env is None else env
    try:
        minutes = int(str(source.get("HITL_PENDING_SLA_MINUTES", "")).strip())
    except ValueError:
        return DEFAULT_PENDING_SLA_MINUTES
    return minutes if minutes > 0 else DEFAULT_PENDING_SLA_MINUTES


class ReviewNotFoundError(Exception):
    """Thao tác trên một mục không tồn tại."""


class ReviewNotApprovedError(Exception):
    """Chưa `APPROVED`/`EDITED` mà đã đòi gửi khách."""


class CustomerSessionForbiddenError(Exception):
    """Khách không sở hữu phiên đang được yêu cầu."""


class ReviewClaimForbiddenError(Exception):
    """Mục này do tư vấn viên khác giữ lease hoặc người yêu cầu không phải chủ lease."""


class ReviewLeaseExpiredError(Exception):
    """Thời hạn 15 phút lease của mục này đã hết hạn."""


class EditedNumbersChangedError(Exception):
    """Bản sửa đổi con số so với bản nháp — tư vấn viên chỉ được sửa văn bản."""


class UntracedNumberError(Exception):
    """Approve nguyên trạng nhưng nội dung chứa con số không traceable (guard 1A)."""


@dataclass(frozen=True)
class ReviewItem:
    """Một mục trong hàng đợi, đọc ở mức use case cần."""

    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    edited_content: str | None
    claimed_by: str | None = None
    lease_expires_at: datetime | None = None
    profile_snapshot: dict | None = None
    handoff_requested: bool = False
    offer_suggestion_ignored: bool = False

    @property
    def offer_state(self) -> str | None:
        if not self.profile_snapshot:
            return None
        state = self.profile_snapshot.get("offer_state")
        return state if isinstance(state, str) else None

    @property
    def matched_promotions(self) -> list[dict]:
        """Ưu đãi khớp nút thắt, đọc từ snapshot bất biến lúc vào hàng chờ."""
        if not self.profile_snapshot:
            return []
        matched = self.profile_snapshot.get("matched_promotions")
        if not isinstance(matched, list):
            return []
        return [item for item in matched if isinstance(item, dict)]

    @property
    def deliverable_content(self) -> str:
        """Nội dung thật sự gửi khách: bản sửa nếu có, không thì bản nháp gốc."""
        return customer_safe_answer(self.edited_content or self.content)


@dataclass(frozen=True)
class QueueEntry:
    """Một dòng hàng đợi nhìn từ phía tư vấn viên.

    Rộng hơn `ReviewItem` vì màn hàng đợi cần biết mục đã có người giữ chưa và
    giữ tới bao giờ; hẹp hơn hàng trong bảng vì `edited_content` chỉ có nghĩa
    sau khi đã xử lý.
    """

    review_id: UUID
    session_id: UUID
    run_id: UUID
    status: str
    content: str
    claimed_by: str | None
    lease_expires_at: datetime | None
    created_at: datetime
    profile_snapshot: dict | None = None
    handoff_requested: bool = False
    offer_suggestion_ignored: bool = False
    age_minutes: int | None = None
    #: [T7b] Số lần đẩy vượt trần đã gộp vào mục này. Trần chỉ có nghĩa khi tư
    #: vấn viên NHÌN THẤY con số: gộp mà không hiện ra thì mục thứ tư trở đi biến
    #: mất lặng lẽ, và đó là mất tín hiệu chứ không phải dọn nhiễu.
    merged_count: int = 0

    @property
    def offer_state(self) -> str | None:
        if not self.profile_snapshot:
            return None
        state = self.profile_snapshot.get("offer_state")
        return state if isinstance(state, str) else None


def numbers_in(text: str) -> list[str]:
    """Mọi cụm chữ số trong văn bản, giữ nguyên thứ tự xuất hiện.

    Dấu phân cách nghìn bị bỏ qua ("1.200.000.000" và "1200000000" cùng một số),
    nên tư vấn viên đổi cách viết số vẫn qua được, còn đổi giá trị thì không.
    """
    normalized = re.sub(r"(?<=\d)[.,\s](?=\d)", "", text)
    return [match for match in re.findall(r"\d+", normalized) if _DIGITS.search(match)]


def numbers_added_illegally(content: str, edited: str, allowed: set[str]) -> list[str]:
    """Các con số MỚI trong bản sửa mà không nằm trong biên độ đã duyệt.

    Trước 2026-08-31 mọi số thêm vào đều bị chặn — tư vấn viên KHÔNG THỂ trả lời
    ưu đãi (ưu đãi nào chả có số). Số hợp lệ = số đã có trong nháp, hoặc số xuất
    hiện trong bảng biên độ điều chỉnh Admin cấu hình (`adjustment_policies`).
    """

    content_numbers = set(numbers_in(customer_safe_answer(content)))
    return [n for n in numbers_in(customer_safe_answer(edited)) if n not in content_numbers and n not in allowed]


def _verified_tokens(item: ReviewItem) -> set[str]:
    """Tập con số đã verify (guard 1A) — từ profile_snapshot.verified_number_tokens."""
    snapshot = item.profile_snapshot or {}
    tokens = snapshot.get("verified_number_tokens") or []
    return set(str(token) for token in tokens)


class ClaimableReviewQueue(Protocol):
    """Phần `review_queue` mà use case A7 cần — hẹp hơn `ReviewQueueRepository`."""

    async def claim(self, queue_id: UUID, advisor_id: str, lease_minutes: int) -> bool: ...

    async def exists(self, queue_id: UUID) -> bool: ...

    async def find(self, queue_id: UUID) -> ReviewItem | None: ...

    async def resolve(
        self,
        queue_id: UUID,
        advisor_id: str,
        status: str,
        edited_content: str | None,
        *,
        is_admin: bool = False,
        handoff_requested: bool = False,
        offer_suggestion_ignored: bool = False,
    ) -> None: ...

    async def customer_owns_session(self, session_id: UUID, customer_id: str) -> bool: ...

    async def list_for_session(self, session_id: UUID) -> list[ReviewItem]: ...

    async def list_pending(self) -> list[QueueEntry]: ...

    async def list_by_status(self, statuses: Sequence[str], *, limit: int, offset: int) -> list[QueueEntry]: ...

    async def mark_first_viewed(self, queue_id: UUID) -> None: ...


class RankedRunRepository(Protocol):
    """Phần run data dùng để dựng ảnh so sánh theo kết quả đã xếp hạng."""

    async def ranked_vehicle_ids(self, run_id: UUID) -> list[UUID]: ...


class ClaimTransaction(Protocol):
    """Bó repository nhìn từ use case claim."""

    review_queue: ClaimableReviewQueue
    runs: RankedRunRepository
    bottleneck_signals: BottleneckSignalRepository


class ReviewRecommendation(Protocol):
    """Dựng bảng so sánh từ snapshot bất biến của run."""

    async def compare(self, *, run_id: UUID, vehicle_ids: Sequence[UUID]) -> ComparisonTable: ...


class ClaimUnitOfWork(Protocol):
    """Ranh giới transaction cho use case claim."""

    def transaction(self) -> AbstractAsyncContextManager[ClaimTransaction]: ...


class ClaimRejection(StrEnum):
    """Lý do không nhận được mục — phân biệt "đã có người nhận" với "không tồn tại"."""

    ALREADY_CLAIMED = "ALREADY_CLAIMED"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class ClaimOutcome:
    """Kết quả một lần claim; `rejection` chỉ có giá trị khi không giành được."""

    granted: bool
    rejection: ClaimRejection | None = None


class ReviewOperations:
    """Use case vận hành hàng đợi duyệt (A7)."""

    def __init__(
        self,
        unit_of_work: ClaimUnitOfWork,
        *,
        image_store: ComparisonImageStore | None = None,
        image_source: VehicleImageSource | None = None,
        recommendation: ReviewRecommendation | None = None,
        broker: TurnEventBroker | None = None,
        offer_policy: OfferAdjustmentPolicy | None = None,
        offer_adjustment_log: OfferAdjustmentAuditLog | None = None,
        offer_suggestion: OfferSuggestionPort | None = None,
        profile_snapshot_service: ProfileSnapshotService | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._image_store = image_store
        self._image_source = image_source
        self._recommendation = recommendation
        self._broker = broker
        self._offer_policy = offer_policy
        self._offer_adjustment_service = (
            OfferAdjustmentService(policy=offer_policy, audit_log=offer_adjustment_log)
            if offer_policy is not None and offer_adjustment_log is not None
            else None
        )
        self._offer_suggestion = offer_suggestion
        self._profile_snapshot_service = profile_snapshot_service

    async def pending_queue(self) -> list[QueueEntry]:
        """Hàng đợi tư vấn viên nhìn thấy — chỉ mục chưa xử lý.

        Không đi qua `deliverable_for_customer`: đây là đường đọc của nhân sự
        nội bộ, chốt chặn trạng thái chỉ áp cho đường ra khách.
        """
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.review_queue.list_pending()

    async def queue_stats(self) -> dict[str, int]:
        """Thống kê số lượng hàng đợi từ bảng review_queue."""
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.review_queue.queue_stats()

    async def queue_entries(
        self, *, status_filter: str = "pending", limit: int = 50, offset: int = 0
    ) -> list[QueueEntry]:
        """Hàng đợi có lọc trạng thái + phân trang cho màn tư vấn viên.

        Cùng đường đọc nội bộ với `pending_queue`, chỉ khác ở chỗ gọi được cả
        mục đã xử lý — chốt chặn trạng thái vẫn chỉ áp cho đường ra khách.
        """
        statuses = QUEUE_STATUS_FILTERS[status_filter]
        async with self._unit_of_work.transaction() as transaction:
            return await transaction.review_queue.list_by_status(statuses, limit=limit, offset=offset)

    async def review_detail(self, review_id: UUID) -> ReviewItem:
        """Bản ghi đầy đủ cho tư vấn viên đọc trước khi quyết định.

        Không lọc trạng thái: tư vấn viên phải xem được đúng bản `PENDING`. Chốt
        chặn trạng thái nằm ở `deliverable_for_customer`, chỉ áp cho đường khách.

        Mở mục lần đầu cũng là lúc đóng dấu `first_viewed_at` — mốc đo thời gian
        phản hồi phải sinh ra ở đúng nơi tư vấn viên thật sự nhìn thấy bản nháp.
        """
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            marker = getattr(transaction.review_queue, "mark_first_viewed", None)
            if marker is not None:
                await marker(review_id)
            builder = self._profile_snapshot_service
            if builder is None:
                return item
            evidence = await transaction.bottleneck_signals.confirmed_evidence_for_session(item.session_id)
        snapshot_data = item.profile_snapshot or {}
        stored = (
            ProfileSnapshot.model_validate(snapshot_data)
            if snapshot_data.get("offer_state") is not None
            else ProfileSnapshot(offer_state=OfferState.NONE_BOTTLENECK)
        )
        # Lõi v2 ghi điểm lăn tăn NGAY trong snapshot lúc tạo mục (đọc transcript),
        # không qua bảng `bottleneck_signals`. Overlay với danh sách rỗng là xoá
        # sạch chúng — kiểm tra prod 2026-08-31: content có "Lăn tăn: giá; sạc" mà
        # màn duyệt trống. Không có tín hiệu đã xác nhận thì giữ nguyên bản lưu.
        projected = builder.overlay(stored, evidence) if evidence else stored
        if self._offer_suggestion is not None:
            suggestion = await self._offer_suggestion.suggest(projected, datetime.now(UTC))
            projected = projected.model_copy(
                update={
                    "offer_state": suggestion.offer_state,
                    "matched_promotions": [
                        {
                            "promotion_code": match.promotion.promotion_code,
                            "promotion_type": match.promotion.promotion_type.value,
                            "gift_group_unclassified": match.gift_group_unclassified,
                        }
                        for match in suggestion.matched
                    ],
                    "unmet_demand_flag": suggestion.unmet_demand_flag,
                    "unmet_bottleneck": suggestion.unmet_bottleneck,
                }
            )
        return replace(item, profile_snapshot=projected.model_dump(mode="json"))

    async def adjustment_policies(self) -> list[dict]:
        """Biên độ ADMIN cấu hình, gửi kèm mục duyệt để tư vấn viên biết trần.

        Thiếu cấu hình không được chặn màn duyệt: trả danh sách rỗng để tư vấn
        viên vẫn đọc và xử lý được nội dung.
        """
        lister = getattr(self._offer_policy, "list_policies", None)
        if lister is None:
            return []
        try:
            return [dict(policy) for policy in await lister()]
        except Exception:  # noqa: BLE001
            logger.warning("khong doc duoc bien do dieu chinh uu dai", exc_info=True)
            return []

    async def claim(self, review_id: UUID, advisor_id: str, lease_minutes: int = DEFAULT_LEASE_MINUTES) -> ClaimOutcome:
        """Nhận một mục trong hàng đợi; thua thì nói rõ vì sao thua."""
        async with self._unit_of_work.transaction() as transaction:
            granted = await transaction.review_queue.claim(review_id, advisor_id, lease_minutes)
            if granted:
                return ClaimOutcome(granted=True)
            found = await transaction.review_queue.exists(review_id)
        rejection = ClaimRejection.ALREADY_CLAIMED if found else ClaimRejection.NOT_FOUND
        return ClaimOutcome(granted=False, rejection=rejection)

    @staticmethod
    async def _resolve_ownership(transaction: ClaimTransaction, session_id: UUID, ownership: str = "AI") -> None:
        """Trả quyền sở hữu phiên sau khi TVV duyệt/từ chối — cùng transaction với resolve.

        `sessions` có thể vắng mặt ở bó repository test; bỏ qua khi thiếu.
        """
        sessions = getattr(transaction, "sessions", None)
        if sessions is not None:
            await sessions.set_ownership(str(session_id), ownership)

    @staticmethod
    async def _reopen_test_drive_stage(transaction: ClaimTransaction, session_id: UUID) -> None:
        """TVV duyệt xong ⇒ chặng sau đề xuất quay lại bước mời lái thử.

        Sếp 2026-08-26: "cấp xong thì lại quay về đăng ký lái thử". Chạy trong
        CÙNG transaction với `resolve` — mục duyệt đã xong mà chặng còn kẹt ở
        `IN_HITL` thì khách phải chờ hết hạn mới được mời, dù ưu đãi đã có.

        Bỏ qua êm khi thiếu repo (bó test) hoặc khi phiên không ở chặng đó: đây là
        tiện ích của luồng tư vấn, không được làm hỏng việc duyệt.
        """

        sessions = getattr(transaction, "sessions", None)
        loader = getattr(sessions, "load_active_task", None)
        saver = getattr(sessions, "save_active_task", None)
        if not callable(loader) or not callable(saver):
            return
        task = ActiveTask.from_payload(await loader(str(session_id)))
        if task is None or stage_of(task.form) is not PostPitchStage.IN_HITL:
            return
        await saver(
            str(session_id),
            replace(task, form=after_offer(task.form), revision=task.revision + 1).to_payload(),
        )

    async def _announce_offer(
        self,
        transaction: ClaimTransaction,
        session_id: UUID,
        offer: Mapping[str, object] | None,
        approved_by: str = "SYSTEM",
    ) -> str | None:
        """Báo khách vừa được ưu đãi gì, ghi ưu đãi vào phiên, rồi chờ khách đáp.

        Ba việc trong MỘT chỗ vì cả ba đều phải cùng thành hoặc cùng không:

        1. `session_offers` — không có nó thì `quote_gate` chặn bot nhắc lại tên
           ưu đãi ở những lượt sau, tức ta vừa cấp xong đã quên.
        2. Câu thông báo — Sếp 2026-08-27: phải NÓI ra khách nhận được gì, và nếu
           là tiền thì hiện cả mức giảm lẫn giá còn lại.
        3. Chặng `AWAITING_COST_CONSENT` — chờ khách đồng ý rồi mới tính lại chi
           phí, KHÔNG tự trừ rồi thay số.

        Thiếu repo (bó test) hay phiên không ở chặng chờ ưu đãi thì bỏ qua êm:
        đây là tiện ích của luồng tư vấn, không được làm hỏng việc duyệt.
        """

        if not offer:
            return None
        sessions = getattr(transaction, "sessions", None)
        loader = getattr(sessions, "load_active_task", None)
        saver = getattr(sessions, "save_active_task", None)
        if not callable(loader) or not callable(saver):
            return None
        task = ActiveTask.from_payload(await loader(str(session_id)))
        if task is None or stage_of(task.form) is not PostPitchStage.IN_HITL:
            return None
        offers = getattr(transaction, "session_offers", None)
        inserter = getattr(offers, "insert", None)
        if callable(inserter):
            try:
                await inserter(
                    session_id=str(session_id),
                    source_kind="CONTENT_REVIEW",
                    source_signal_id=None,
                    promotion_code=str(offer.get("promotion_code") or ""),
                    value_snapshot=dict(offer),
                    # Cột NOT NULL: trước đây truyền None nên insert luôn hỏng và bị
                    # `except` bên dưới nuốt — ưu đãi đã báo khách mà không ghi vào phiên
                    # (plan Customer 360 §2.2). Giờ ghi đúng TVV đã duyệt.
                    approved_by=approved_by,
                )
            except Exception:
                # Ghi hỏng KHÔNG chặn thông báo: khách vẫn phải biết mình được
                # ưu đãi gì. Chỉ là lượt sau bot chưa được phép nhắc lại tên nó.
                logger.warning("review: khong ghi duoc session_offers cho phien %s", session_id, exc_info=True)
        price = vehicle_price(task.form)
        announcement = offer_announcement(
            offer,
            vehicle_name=chosen_vehicle(task.form),
            base_price_vnd=Decimal(price) if price else None,
        )
        await saver(
            str(session_id),
            replace(task, form=after_offer_granted(task.form), revision=task.revision + 1).to_payload(),
        )
        return announcement

    async def _notify_no_offer(self, transaction: ClaimTransaction, session_id: UUID) -> str | None:
        """Chưa có ưu đãi → báo việc vẫn đang chạy, rồi mời tính chi phí.

        Chuyển chặng y như nhánh CÓ ưu đãi: cả hai đều kết bằng một câu hỏi về
        chi phí, nên lượt sau phải được đọc bằng cùng một bộ đọc. Để chặng kẹt ở
        `IN_HITL` thì lời đáp của khách rơi vào khoảng không.
        """

        sessions = getattr(transaction, "sessions", None)
        loader = getattr(sessions, "load_active_task", None)
        saver = getattr(sessions, "save_active_task", None)
        if not callable(loader) or not callable(saver):
            return None
        task = ActiveTask.from_payload(await loader(str(session_id)))
        if task is None or stage_of(task.form) is not PostPitchStage.IN_HITL:
            return None
        await saver(
            str(session_id),
            replace(task, form=after_offer_granted(task.form), revision=task.revision + 1).to_payload(),
        )
        return advisor_still_looking_notice()

    async def approve(
        self,
        review_id: UUID,
        advisor_id: str,
        edited_content: str | None = None,
        *,
        is_admin: bool = False,
    ) -> None:
        """Resolve and durably append final content before publishing its event."""

        message = None
        outcome = None
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            if edited_content is not None:
                # Số trong biên độ Admin đã duyệt (và mốc tháng/năm nhỏ) là số
                # tư vấn viên ĐƯỢC phép đưa vào câu trả lời ưu đãi.
                allowed: set[str] = set()
                for policy in await self.adjustment_policies():
                    for value in policy.values():
                        if value is not None:
                            allowed.update(numbers_in(str(value)))
                self._guard_edited_numbers(item, edited_content, allowed)
            else:
                self._guard_approve_as_is(item)
            review_status = "EDITED" if edited_content is not None else "APPROVED"
            try:
                await transaction.review_queue.resolve(
                    review_id, advisor_id, review_status, edited_content, is_admin=is_admin
                )
            except TypeError:
                await transaction.review_queue.resolve(review_id, advisor_id, review_status, edited_content)
            await self._reopen_test_drive_stage(transaction, item.session_id)
            delivered_content = customer_safe_answer(edited_content or item.content)
            memory = getattr(transaction, "memory", None)
            if memory is not None:
                message = await memory.append_delivery(item.session_id, delivered_content, item.review_id)
            outcomes = getattr(transaction, "outcomes", None)
            if outcomes is not None:
                outcome = await outcomes.set_review_terminal(
                    review_id,
                    status=TurnOutcomeStatus.COMPLETED,
                    message_id=message.message_id if message is not None else None,
                    delivered_content=delivered_content,
                )
            await self._resolve_ownership(transaction, item.session_id)
        if self._broker is not None:
            await self._broker.publish(
                TurnEvent(
                    session_id=item.session_id,
                    review_id=review_id,
                    kind="approved",
                    client_turn_id=(outcome.client_turn_id if outcome is not None else None),
                    message_id=(message.message_id if message is not None else None),
                )
            )

    async def reject(self, review_id: UUID, advisor_id: str, *, is_admin: bool = False) -> None:
        """Reject a draft and publish its durable terminal recovery state."""

        outcome = None
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            try:
                await transaction.review_queue.resolve(review_id, advisor_id, "REJECTED", None, is_admin=is_admin)
            except TypeError:
                await transaction.review_queue.resolve(review_id, advisor_id, "REJECTED", None)
            outcomes = getattr(transaction, "outcomes", None)
            if outcomes is not None:
                outcome = await outcomes.set_review_terminal(review_id, status=TurnOutcomeStatus.REJECTED)
            await self._resolve_ownership(transaction, item.session_id)
        if self._broker is not None:
            await self._broker.publish(
                TurnEvent(
                    session_id=item.session_id,
                    review_id=review_id,
                    kind="rejected",
                    client_turn_id=(outcome.client_turn_id if outcome is not None else None),
                )
            )

    async def resolve_with_offer(
        self,
        review_id: UUID,
        advisor_id: str,
        status: str,
        edited_content: str | None = None,
        offer_adjustment: dict | None = None,
        handoff_requested: bool = False,
    ) -> None:
        """Resolve mục kèm tuỳ chọn cấp ưu đãi + handoff.

        `offer_adjustment` OPTIONAL (D12): advisor có thể approve WITHOUT offer.
        Khi cấp ưu đãi: validate biên (422) + re-validate promotion ACTIVE (409)
        + ghi `offer_adjustment_log`. Khi approve nguyên trạng (không sửa, không
        cấp ưu đãi): guard 1A chặn nội dung chứa con số không traceable.
        """

        adjustment = self._parse_offer_adjustment(offer_adjustment) if offer_adjustment is not None else None
        offer_suggestion_ignored = self._should_mark_ignored(status, offer_adjustment, edited_content)
        message = None
        outcome = None
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            resolved_status = status
            if edited_content is not None:
                self._guard_edited_numbers(item, edited_content)
                resolved_status = "EDITED"
            elif status == "APPROVED" and offer_adjustment is None:
                self._guard_approve_as_is(item)
            if adjustment is not None:
                service = self._offer_adjustment_service
                if service is None:
                    raise OfferAdjustmentOutOfBoundsError("offer adjustment validation unavailable")
                await service.apply(
                    source=OfferAdjustmentSource(OfferAdjustmentSourceKind.CONTENT_REVIEW, item.review_id),
                    advisor_id=advisor_id,
                    adjustment=adjustment,
                    at=self._now(),
                )
            await transaction.review_queue.resolve(
                review_id,
                advisor_id,
                resolved_status,
                edited_content,
                handoff_requested=handoff_requested,
                offer_suggestion_ignored=offer_suggestion_ignored,
            )
            if adjustment is not None and resolved_status in DELIVERABLE_STATUSES:
                announcement = await self._announce_offer(
                    transaction, item.session_id, offer_adjustment, approved_by=advisor_id
                )
            elif resolved_status == "REJECTED" or (adjustment is None and resolved_status in DELIVERABLE_STATUSES):
                # Tư vấn viên xem xong mà CHƯA cấp ưu đãi (từ chối, hoặc duyệt
                # nguyên trạng). Sếp 2026-08-27: vẫn phải báo khách việc đang
                # chạy và mở tiếp một lối đi được ngay.
                #
                # Im lặng ở đây là bỏ rơi khách đúng lúc họ đang chờ: họ vừa nói
                # ra điều còn vướng, được báo đã chuyển người, rồi không nghe gì
                # nữa cho tới khi hết hạn chờ.
                announcement = await self._notify_no_offer(transaction, item.session_id)
            else:
                announcement = None
            base = customer_safe_answer(edited_content or item.content)
            # Thông báo ưu đãi đứng SAU chữ tư vấn viên gõ, không thay nó: họ có
            # thể đã viết phần giải thích riêng, và bỏ đi là bỏ mất đúng câu người
            # thật vừa soạn cho khách này.
            delivered_content = f"{base}\n\n{announcement}" if announcement else base
            memory = getattr(transaction, "memory", None)
            if memory is not None and resolved_status in DELIVERABLE_STATUSES:
                message = await memory.append_delivery(item.session_id, delivered_content, item.review_id)
            outcomes = getattr(transaction, "outcomes", None)
            if outcomes is not None:
                terminal = TurnOutcomeStatus.REJECTED if resolved_status == "REJECTED" else TurnOutcomeStatus.COMPLETED
                outcome = await outcomes.set_review_terminal(
                    review_id,
                    status=terminal,
                    message_id=message.message_id if message is not None else None,
                    delivered_content=delivered_content,
                )
            if resolved_status != "PENDING":
                await self._resolve_ownership(transaction, item.session_id, "HUMAN" if handoff_requested else "AI")
        if self._broker is not None and resolved_status != "PENDING":
            await self._broker.publish(
                TurnEvent(
                    session_id=item.session_id,
                    review_id=review_id,
                    kind=("rejected" if status == "REJECTED" else "approved"),
                    client_turn_id=(outcome.client_turn_id if outcome is not None else None),
                    message_id=(message.message_id if message is not None else None),
                )
            )

    @staticmethod
    def _parse_offer_adjustment(value: Mapping[str, object]) -> OfferAdjustment:
        return OfferAdjustment(
            promotion_code=str(value.get("promotion_code") or ""),
            promotion_type=str(value.get("promotion_type") or ""),
            adjustment_type=str(value.get("adjustment_type") or "VND"),
            old_value=(str(value["old_value"]) if value.get("old_value") is not None else None),
            new_value=(str(value["new_value"]) if value.get("new_value") is not None else None),
            reason=(str(value["reason"]) if value.get("reason") is not None else None),
            amount_vnd=(int(str(value["amount_vnd"])) if value.get("amount_vnd") is not None else None),
            percent=(str(value["percent"]) if value.get("percent") is not None else None),
            months=(int(str(value["months"])) if value.get("months") is not None else None),
            gift_code=(str(value["gift_code"]) if value.get("gift_code") is not None else None),
        )

    def _should_mark_ignored(self, status: str, offer_adjustment: dict | None, edited_content: str | None) -> bool:
        if status == "APPROVED" and offer_adjustment is None and edited_content is None:
            return False
        if status in DELIVERABLE_STATUSES and offer_adjustment is None:
            return True
        return False

    def _guard_approve_as_is(self, item: ReviewItem) -> None:
        """Guard 1A: approve nguyên trạng — chặn con số không traceable."""
        verified = _verified_tokens(item)
        if not verified:
            return
        content_numbers = set(numbers_in(customer_safe_answer(item.content)))
        untraced = content_numbers - verified
        if untraced:
            raise UntracedNumberError(f"content contains untraceable numbers: {sorted(untraced)}")

    def _guard_edited_numbers(self, item: ReviewItem, edited_content: str, allowed: set[str] | None = None) -> None:
        """Guard số khi sửa (fold #1): xoá số không traceable, THÊM số phải trong biên độ."""
        edited_numbers = numbers_in(customer_safe_answer(edited_content))
        removed = [n for n in numbers_in(customer_safe_answer(item.content)) if n not in edited_numbers]
        if numbers_added_illegally(item.content, edited_content, allowed or set()):
            raise EditedNumbersChangedError(str(item.review_id))
        if removed:
            verified = _verified_tokens(item)
            for number in removed:
                if number in verified:
                    raise EditedNumbersChangedError(str(item.review_id))

    def _now(self) -> datetime:
        from datetime import UTC

        return datetime.now(UTC)

    async def expire(self, review_id: UUID) -> None:
        """Expire a pending draft and publish its durable recovery state.

        The expiry policy or scheduler owns the decision of when to call this
        operation; this use case only guarantees the atomic state transition.
        """

        outcome = None
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            await transaction.review_queue.resolve(review_id, "system:review-expiry", "EXPIRED", None)
            outcomes = getattr(transaction, "outcomes", None)
            if outcomes is not None:
                outcome = await outcomes.set_review_terminal(review_id, status=TurnOutcomeStatus.EXPIRED)
        if self._broker is not None:
            await self._broker.publish(
                TurnEvent(
                    session_id=item.session_id,
                    review_id=review_id,
                    kind="expired",
                    client_turn_id=(outcome.client_turn_id if outcome is not None else None),
                )
            )

    async def expire_stale(self, *, sla_minutes: int | None = None) -> list[UUID]:
        """Thu hồi mọi mục `PENDING` đã quá hạn SLA; trả danh sách vừa thu hồi.

        Không có worker định kỳ: hàm này chạy nhờ chính lượt khách quay lại hỏi
        (`expire()` giữ nguyên chữ ký, đây chỉ là lớp bọc chọn mục nào tới hạn).
        `age_minutes` đã do repository tính bằng cùng một đồng hồ với dữ liệu,
        nên không có chuyện lệch múi giờ giữa `created_at` và mốc so sánh.
        """
        threshold = pending_sla_minutes() if sla_minutes is None else sla_minutes
        expired: list[UUID] = []
        for entry in await self.pending_queue():
            if entry.age_minutes is None or entry.age_minutes < threshold:
                continue
            try:
                await self.expire(entry.review_id)
            except ReviewNotFoundError:
                continue
            expired.append(entry.review_id)
        return expired

    async def _expire_stale_quietly(self) -> None:
        """Chạy lazy expire trên đường đọc của khách mà không làm hỏng đường đó.

        Khách hỏi bài là để lấy nội dung; dọn hàng đợi hỏng thì ghi nhật ký chứ
        không được biến thành lỗi 500 trước mặt khách.
        """
        try:
            await self.expire_stale()
        except Exception:  # noqa: BLE001
            logger.warning("khong thu hoi duoc muc duyet qua han", exc_info=True)

    async def deliverable_for_customer(self, review_id: UUID) -> ReviewItem:
        """[A7-3] Bản ghi được phép gửi khách — chặn cứng theo trạng thái duyệt.

        Trả cả bản ghi (không chỉ chuỗi nội dung) để đường gửi khách lấy được
        `run_id` mà tìm ảnh so sánh kèm theo, vẫn đi qua đúng một chốt chặn này.
        """
        async with self._unit_of_work.transaction() as transaction:
            item = await self._require(transaction, review_id)
            if item.status not in DELIVERABLE_STATUSES:
                raise ReviewNotApprovedError(str(review_id))
            return item

    async def image_for_review(self, review_id: UUID) -> bytes | None:
        """Render once on review access and cache the image by immutable run ID."""
        if self._image_store is None:
            return None
        try:
            async with self._unit_of_work.transaction() as transaction:
                item = await self._require(transaction, review_id)
                cached = self._image_store.load(item.run_id)
                if cached is not None:
                    return cached
                if self._image_source is None or self._recommendation is None:
                    return None
                vehicle_ids = await transaction.runs.ranked_vehicle_ids(item.run_id)
            if len(vehicle_ids) < 2:
                return None
            table = await self._recommendation.compare(run_id=item.run_id, vehicle_ids=vehicle_ids)
            photos = {
                vehicle_id: photo
                for vehicle_id in vehicle_ids
                if (photo := await self._image_source.load(vehicle_id)) is not None
            }
            image = render_comparison_image_or_none(table, photos=photos)
            if image is None:
                return None
            self._image_store.save(item.run_id, image)
            return image
        except Exception:  # noqa: BLE001
            logger.warning("khong dung duoc anh so sanh cho muc duyet %s", review_id, exc_info=True)
            return None

    async def customer_deliverables(self, session_id: UUID, customer_id: str) -> list[ReviewItem]:
        """List customer items through the single deliverable status gate.

        Lượt poll của khách cũng là nhịp thu hồi mục quá hạn: dọn trước rồi mới
        đọc, để lần hỏi này thấy ngay lời xin lỗi thay vì im lặng thêm một vòng.
        """
        await self._expire_stale_quietly()
        async with self._unit_of_work.transaction() as transaction:
            owns_session = await transaction.review_queue.customer_owns_session(session_id, customer_id)
            if not owns_session:
                raise CustomerSessionForbiddenError(str(session_id))
            items = await transaction.review_queue.list_for_session(session_id)
        deliverables: list[ReviewItem] = []
        for item in items:
            if item.status == "EXPIRED":
                deliverables.append(replace(item, content=EXPIRED_CUSTOMER_MESSAGE, edited_content=None))
                continue
            try:
                deliverables.append(await self.deliverable_for_customer(item.review_id))
            except ReviewNotApprovedError:
                continue
        return deliverables

    async def authorize_customer_session(self, session_id: UUID, customer_id: str) -> None:
        """Authorize SSE subscription before opening its broker stream.

        Cửa vào SSE cũng là một lượt khách quay lại, nên nó cũng kích hoạt lazy
        expire — mục quá hạn phát sự kiện `expired` ngay khi luồng vừa mở.
        """
        await self._expire_stale_quietly()
        async with self._unit_of_work.transaction() as transaction:
            owns_session = await transaction.review_queue.customer_owns_session(session_id, customer_id)
            if not owns_session:
                raise CustomerSessionForbiddenError(str(session_id))

    async def _require(self, transaction: ClaimTransaction, review_id: UUID) -> ReviewItem:
        item = await transaction.review_queue.find(review_id)
        if item is None:
            raise ReviewNotFoundError(str(review_id))
        return item
