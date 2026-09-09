"""Deterministic reconciliation for one structured customer-turn interpretation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.comparative_revision import detect_comparative_revision
from src.agents.domain.intent_reconciliation import (
    is_catalog_browse_request,
    is_named_model_listing_request,
    is_test_drive_request,
)
from src.agents.domain.nearby_location import is_nearby_location_request
from src.agents.domain.offer_reply import asks_for_cost_estimate
from src.agents.domain.task_state import ActiveTask, TaskStatus, TaskType
from src.agents.domain.values import Intent, ScopeLabel, SlotValue, TaskAction

_OTHER_RESULTS_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:xe|mau|phuong\s+an|lua\s+chon)\s+khac\b|"
    r"\b(?:con|co)\s+(?:xe|mau|phuong\s+an)\s+nao\s+khac\b|"
    r"\bkhong\s+ung\s+(?:may|nhung)\s+(?:xe|mau).*(?:khac|them)\b",
    re.IGNORECASE,
)
_RESTART_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tu\s+van|chon\s+xe|tim\s+xe)\s+lai\s+tu\s+dau\b|"
    r"\blam\s+lai\s+(?:tu|ngay)\s+dau\b|"
    # "bắt đầu lại" / "làm lại" trơ trọi — đo 2026-08-28: sau đề xuất, khách gõ
    # "bắt đầu lại" bị đọc thành lời đáp chặng sau đề xuất ("Em có thể đặt lịch
    # lái thử…") vì không cụm nào ở đây khớp.
    r"^(?:bat\s+dau\s+lai|lam\s+lai|reset)(?:\s+(?:di|nhe|nha|a|nao))?[.!]?$",
    re.IGNORECASE,
)
_RESUME_CUE: Final[re.Pattern[str]] = re.compile(
    r"^(?:quay\s+lai|tiep\s+tuc)\s*[.!]?$|"
    r"\b(?:quay\s+lai|tiep\s+tuc)\b.*\b(?:tu\s+van|nhu\s+cau|luc\s+nay)\b",
    re.IGNORECASE,
)
#: Cụm định giá đứng CÙNG nhóm ngân sách: cả hai đều là câu hỏi về tiền của một
#: chiếc xe, tức nằm trong phạm vi theo định nghĩa.
#:
#: Đo trên prod 2026-08-27: *"tính giá lăn bánh"* nhận `scope_label:
#: OUT_OF_SCOPE`. Cue cũ chỉ có "chi phí" — mà khách nói "giá lăn bánh", "giá ra
#: biển", "phí trước bạ", không ai nói "chi phí lăn bánh". Viết cả bản CÓ DẤU và
#: bản KHÔNG DẤU vì cue này so trên câu gốc, không so trên bản đã gấp dấu.
_BUDGET_OR_PURCHASE_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:ngân\s*sách|ngan\s*sach|tài\s*chính|tai\s*chinh|tỷ|ty|triệu|trieu|tr|"
    r"mua\s+(?:được|duoc)?\s*(?:mấy|may|bao\s+nhiêu|bao\s+nhieu)?|"
    r"bao\s+nhiêu\s+tiền|bao\s+nhieu\s+tien|chi\s+phí|chi\s+phi|"
    r"lăn\s*bánh|lan\s*banh|ra\s*biển|ra\s*bien|"
    r"trước\s*bạ|truoc\s*ba|biển\s*số|bien\s*so|tco)\b",
    re.IGNORECASE,
)


def reconcile_scope(
    *,
    raw_scope: ScopeLabel | None,
    intents: Sequence[Intent],
    user_message: str,
    vehicle_mentions: Sequence[str],
) -> ScopeLabel:
    """Recover missing labels without overriding a deliberate semantic rejection."""

    if Intent.FIND_NEARBY_LOCATION in intents and is_nearby_location_request(user_message):
        return ScopeLabel.IN_SCOPE

    # A model name is an entity, not proof that the requested action is supported.
    # Therefore an explicit SOCIAL/OUT_OF_SCOPE decision always wins (for example,
    # "tôi muốn đi tù bằng VF8"). Deterministic evidence only repairs an absent or
    # legacy MISSING_DATA label.
    if raw_scope in {ScopeLabel.SOCIAL, ScopeLabel.OUT_OF_SCOPE}:
        if _BUDGET_OR_PURCHASE_CUE.search(user_message) or is_catalog_browse_request(user_message):
            return ScopeLabel.IN_SCOPE
        # Xin LÁI THỬ là dịch vụ hệ thống CÓ — `services/test_drive` đặt lịch
        # thật. Nói nó nằm ngoài phạm vi là nói sai về chính mình.
        #
        # Đo trên prod 2026-08-27: *"đăng ký lái thử"* nhận `scope_label:
        # OUT_OF_SCOPE` + `intents: []`. Lượt đó sống sót nhờ cửa
        # `in_post_pitch_stage` ở `nodes/classify_scope`, nhưng cùng câu ấy gõ
        # NGOÀI chặng sau đề xuất thì không cửa nào đỡ. Bằng chứng tất định đã
        # tính sẵn (`is_test_drive_request`) — chỉ thiếu chỗ nối vào quyết định,
        # đúng hình dạng lỗi của nhánh giá lăn bánh.
        if is_test_drive_request(user_message):
            return ScopeLabel.IN_SCOPE
        return raw_scope

    strong_catalog_request = (Intent.CATALOG_BROWSE in intents and is_catalog_browse_request(user_message)) or (
        Intent.CATALOG_LOOKUP in intents and bool(vehicle_mentions) and is_named_model_listing_request(user_message)
    )
    if strong_catalog_request or raw_scope in {None, ScopeLabel.MISSING_DATA}:
        return ScopeLabel.IN_SCOPE
    return raw_scope


def reconcile_task_action(
    *,
    user_message: str,
    raw_action: TaskAction,
    intents: Sequence[Intent],
    active_task_payload: Mapping[str, object] | None,
    current_slots: Mapping[str, SlotValue] | None = None,
    known_slots: Mapping[str, SlotValue] | None = None,
    vehicle_mentions: Sequence[str] = (),
    canonical: CanonicalText | None = None,
) -> tuple[TaskAction, tuple[str, ...]]:
    """Resolve task focus and recommendation exclusions using explicit precedence.

    So khớp cue trên `canonical.folded` sinh tại chain (ENG REVIEW AMENDMENT 2)
    — gate không tự normalize. Vắng mặt thì tự dựng từ `user_message` (đường
    tương thích cho test double).
    """

    canonical = canonical or build_canonical_text(user_message)
    normalized = canonical.folded
    active_task = ActiveTask.from_payload(active_task_payload)
    intent_set = set(intents)

    if _RESTART_CUE.search(normalized):
        return TaskAction.RESTART_TASK, ()
    if _RESUME_CUE.search(normalized):
        return TaskAction.RESUME_TASK, ()
    if intent_set and Intent.ADVISORY not in intent_set:
        action = TaskAction.INTERRUPT_WITH_LOOKUP if active_task is not None else TaskAction.START_NEW_TASK
        return action, ()
    if Intent.ADVISORY in intent_set and _OTHER_RESULTS_CUE.search(normalized):
        return TaskAction.REVISE_RESULTS, _seen_recommendation_ids(active_task)
    # Lối SO SÁNH là cách nói phổ biến hơn hẳn "còn mẫu nào khác": khách đã xem
    # một chiếc rồi thì họ nói nó to quá / đắt quá bằng chữ "hơn", không kể lại
    # rằng họ muốn "phương án khác". `_OTHER_RESULTS_CUE` không phủ nổi lối này,
    # nên câu *"nếu anh muốn 1 chiếc nhỏ hơn thì sao"* rơi xuống tận nhánh
    # `CLARIFY_TASK`/`START_NEW_TASK` và chạy lại đúng bộ lọc cũ.
    if (
        Intent.ADVISORY in intent_set
        and detect_comparative_revision(canonical, vehicle_mentions=bool(vehicle_mentions)) is not None
    ):
        return TaskAction.REVISE_RESULTS, _seen_recommendation_ids(active_task)
    if raw_action is TaskAction.REVISE_RESULTS and Intent.ADVISORY in intent_set:
        return TaskAction.REVISE_RESULTS, _seen_recommendation_ids(active_task)
    # Xin LÁI THỬ không phải một lượt "muốn tư vấn" mơ hồ — đó là bước cuối của
    # chính cuộc tư vấn vừa xong, và việc của nó nằm ở chặng sau đề xuất.
    #
    # Đọc từ log thật 2026-08-27: khách gõ *"cho anh đặt lịch"* sau khi đã xem xe
    # và xem chi phí, rồi nhận về *"cho em biết ngân sách hoặc số chỗ ngồi mong
    # muốn"* — hỏi lại ngân sách họ đã nói, và hỏi số chỗ vốn đã bỏ không hỏi.
    #
    # Bản vá đầu chỉ gắn `not is_test_drive_request(...)` vào cửa `CLARIFY_TASK`
    # ngay dưới. Tránh được câu hỏi vô duyên, nhưng lượt rơi thẳng xuống
    # `CONTINUE_TASK` — tức CHẠY LẠI bảng điểm cũ — và khách nhận đè lên đúng bản
    # đề xuất họ vừa đọc. Lối thoát dẫn vào cái hố sâu hơn.
    #
    # Lưới E2E `test_post_pitch_test_drive_e2e` đỏ 1/4 lần vì chuyện này, chập
    # chờn theo việc LLU có gắn `ADVISORY` cho câu xin lái thử hay không. Trả
    # `NONE` để KHÔNG mở việc tư vấn nào: `_advance_post_pitch` là chỗ đọc câu
    # này, và nó là bản đọc tất định.
    #
    # KHÔNG kèm `_has_new_task_information` vào cửa này, dù bản đầu có.
    #
    # Hàm đó so hai bản đồ slot mà `current_slots` là thứ LLM trích ra — và trên
    # câu *"đăng ký lái thử"* nó trích ra khác nhau giữa các lần chạy. Đo được:
    # bộ tìm nhu cầu gắn `PREMIUM_COMFORT` cho đúng câu ấy (score 0.467). Thêm
    # điều kiện đó vào là mời chính chỗ chập chờn quay lại — lưới E2E vẫn đỏ
    # 1/4 lần sau bản vá đầu.
    #
    # Đánh đổi đã cân nhắc: câu vừa xin lái thử vừa mang tiêu chí mới ("cho anh
    # xe 7 chỗ rồi đăng ký lái thử") sẽ KHÔNG chấm lại điểm ở lượt này. Chấp
    # nhận được — khách nói to nhất là muốn lái thử, chặng sau đề xuất hỏi họ
    # mẫu nào, và tiêu chí vừa nói vẫn nằm trong slot cho lượt tư vấn kế tiếp.
    if (
        active_task is not None
        and active_task.task_type is TaskType.ADVISORY
        and active_task.status is TaskStatus.COMPLETED
        and is_test_drive_request(user_message)
    ):
        return TaskAction.NONE, ()
    if (
        active_task is not None
        and active_task.task_type is TaskType.ADVISORY
        and active_task.status is TaskStatus.COMPLETED
        and Intent.ADVISORY in intent_set
        and not _has_new_task_information(current_slots, known_slots)
        and not vehicle_mentions
        # Lời xin TÍNH TIỀN ("tính giá lăn bánh") sau đề xuất không phải "xem lại
        # danh sách hay đổi tiêu chí": LLM prod gán ADVISORY cho câu đó và khách
        # nhận câu hỏi lạc đề (prod 2026-08-29). Cùng khuôn với ngoại lệ lái thử.
        and not asks_for_cost_estimate(canonical)
    ):
        # A completed recommendation is resumable memory, not the default
        # meaning of every later "I want advice" turn.  With no new criterion
        # and no explicit resume/revise/restart cue, ask which operation the
        # customer intends instead of replaying the old scoring inputs.
        return TaskAction.CLARIFY_TASK, ()
    if active_task is not None and active_task.task_type is TaskType.ADVISORY and Intent.ADVISORY in intent_set:
        return TaskAction.CONTINUE_TASK, ()
    if intent_set:
        return TaskAction.START_NEW_TASK, ()
    return TaskAction.NONE, ()


def _has_new_task_information(
    current_slots: Mapping[str, SlotValue] | None,
    known_slots: Mapping[str, SlotValue] | None,
) -> bool:
    """Return whether this turn changed any advisory criterion.

    The extractor can repeat ``vehicle_type=CAR`` for a vague phrase such as
    "tư vấn xe".  A value identical to persisted state is context, not new
    customer information, and must not authorize replaying completed scoring.
    """

    current = dict(current_slots or {})
    known = dict(known_slots or {})
    return any(name not in known or known[name] != value for name, value in current.items())


def is_revise_results_request(user_message: str, canonical: CanonicalText | None = None) -> bool:
    """Return whether the customer explicitly asks for different recommendations.

    So trên `canonical.folded` — gate không tự normalize (AMENDMENT 2).
    """

    canonical = canonical or build_canonical_text(user_message)
    return _OTHER_RESULTS_CUE.search(canonical.folded) is not None


def is_restart_task_request(user_message: str, canonical: CanonicalText | None = None) -> bool:
    """Return whether the customer explicitly discards the old task criteria.

    So trên `canonical.folded` — gate không tự normalize (AMENDMENT 2).
    """

    canonical = canonical or build_canonical_text(user_message)
    return _RESTART_CUE.search(canonical.folded) is not None


def _seen_recommendation_ids(task: ActiveTask | None) -> tuple[str, ...]:
    if task is None or task.task_type is not TaskType.ADVISORY:
        return ()
    raw = task.form.get("seen_recommendation_ids")
    if not isinstance(raw, list):
        return ()
    return tuple(dict.fromkeys(str(value) for value in raw if value))


__all__ = [
    "is_revise_results_request",
    "is_restart_task_request",
    "reconcile_scope",
    "reconcile_task_action",
]
