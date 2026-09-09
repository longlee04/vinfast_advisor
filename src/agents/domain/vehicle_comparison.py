"""[COMPARE_VEHICLES] Luật thuần cho lượt so sánh xe: nhận cue, chốt tập xe.

Module này KHÔNG chuẩn hoá tên xe và KHÔNG khớp tên xe. Đó là việc của Lớp 2
(`domain/fuzzy_match.py` + `domain/entity_catalog.py`) và của
`adapters/catalog_reader.resolve_vehicle_names`. Ở đây chỉ trả lời hai câu hỏi
mà hai chỗ kia không trả lời được:

1. Lượt này có phải ý SO SÁNH không (dựa trên câu chữ, không dựa trên entity)?
2. Tập xe khách nêu có hợp lệ để gọi tool không (đủ 2, không trùng, không quá 3)?

Tách cue ra một hàm dùng chung (`has_comparison_cue`) là có chủ đích: Lớp 3
(`domain/nlu_confidence`), bộ hoà giải nhãn (`domain/intent_reconciliation`) và
node định tuyến (`nodes/route_intent`) đều phải hỏi đúng một câu "câu này có ý
so sánh không". Ba bảng từ khoá riêng cho cùng một câu hỏi là ba câu trả lời
lệch nhau mà không log nào chỉ ra được.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.text_normalization import normalize, squash

#: Trần số xe trong một bảng so sánh.
#:
#: [GIẢ ĐỊNH] 3 xe — cùng con số mà `domain/comparison.compare_candidates` (A5-4)
#: đã chốt cho bảng so sánh gửi tư vấn viên, nên hai đường đi của cùng một nghiệp
#: vụ không nói hai giới hạn khác nhau. Bốn cột trở lên cũng không đọc được trên
#: màn hình điện thoại, vốn là nơi phần lớn lượt chat diễn ra.
MAX_COMPARISON_VEHICLES: Final[int] = 3
#: Sàn: so sánh một xe với chính nó không phải so sánh.
MIN_COMPARISON_VEHICLES: Final[int] = 2

#: Tên slot của trạng thái "đang chờ khách nêu xe để so sánh".
#:
#: [KHÁC BIỆT] Đặc tả nói tới một state machine hội thoại có sẵn để thêm
#: `AWAITING_COMPARE_TARGETS` vào. Repo KHÔNG có enum như vậy: `AI →
#: PENDING_HANDOFF → HUMAN` mới chỉ là một đầu dò `getattr` ở
#: `chain._handoff_active` (xem [GIẢ ĐỊNH] tại chỗ), còn
#: `domain/conversation_memory.ConversationState` chỉ có `ACTIVE`/`ARCHIVED` —
#: đó là vòng đời của một cuộc hội thoại, không phải trạng thái đối thoại.
#:
#: Cơ chế "đang chờ khách trả lời một thứ, sống qua nhiều lượt" mà repo THẬT SỰ
#: có là `PendingSlotRequest` của A7-10, lưu ở `conversation_sessions.
#: pending_slot_request`. Trạng thái này vì vậy là MỘT bản ghi pending với
#: `intent="COMPARE_VEHICLES"` và `missing_slot=COMPARE_TARGETS_SLOT`. Đổi lại
#: là được reset đúng cách miễn phí: `chain._apply_conversation_control`,
#: `_apply_advisory_restart` và `_clear_session_pending` đều đã xoá pending, nên
#: khách gõ lệnh reset hay đổi chủ đề là thoát trạng thái, không phải viết thêm
#: một nhánh dọn dẹp thứ hai (và quên nó ở một trong ba chỗ).
COMPARE_TARGETS_SLOT: Final[str] = "compare_targets"

#: Từ khoá NÓI THẲNG ý so sánh. Khớp trên câu đã chuẩn hoá (không dấu) nên mỗi
#: mục chỉ cần viết một lần, không phải viết cả bản có dấu lẫn bản không dấu.
_EXPLICIT_COMPARISON_CUES: Final[tuple[str, ...]] = (
    "so sanh",
    "so voi",
    "khac gi",
    "khac nhau",
    "khac biet",
    "doi chieu",
    "hon kem",
    "chenh nhau",
    "khac o cho nao",
    "khac cho nao",
)

#: Từ khoá HỎI CHỌN. Một mình chúng chưa đủ ("nên mua xe gì" là câu tư vấn, không
#: phải câu so sánh) nên `plan_comparison` chỉ nhận khi lượt còn nêu ≥2 tên xe.
_CHOICE_CUES: Final[tuple[str, ...]] = (
    "nen chon",
    "nen mua",
    "nen lay",
    "chon xe nao",
    "xe nao",
    "cai nao",
    "con nao",
    "ban nao",
    "tot hon",
    "hay hon",
    "ngon hon",
    "dang mua hon",
    "on hon",
)

#: Từ nối liệt kê giữa hai tên xe. Chỉ dùng làm điều kiện PHỤ cho `_CHOICE_CUES`
#: — "vf3 và vf5" đứng một mình là một lời kể, không phải một câu hỏi.
_CONNECTOR_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?<![a-z0-9])(?:vs|voi|va|hay|hoac|so voi)(?![a-z0-9])")


class ComparisonOutcome(StrEnum):
    """Kết cục của việc chốt tập xe cho một lượt so sánh."""

    #: Lượt này không mang ý so sánh — nhánh compare không được chạm vào nó.
    NOT_A_COMPARISON = "NOT_A_COMPARISON"
    #: Có ý so sánh nhưng CHƯA nắm được xe nào → hỏi khách muốn so sánh những xe
    #: nào (trạng thái `COMPARE_TARGETS_SLOT`).
    NEED_ANY_VEHICLE = "NEED_ANY_VEHICLE"
    #: Có ý so sánh nhưng mới nắm được một xe → rơi về intent cũ, hỏi thêm xe.
    NEED_MORE_VEHICLES = "NEED_MORE_VEHICLES"
    #: Khách gõ trùng đúng một mẫu hai lần ("so sánh vf3 và vf3").
    DUPLICATE_VEHICLE = "DUPLICATE_VEHICLE"
    #: Quá trần `MAX_COMPARISON_VEHICLES`.
    TOO_MANY_VEHICLES = "TOO_MANY_VEHICLES"
    #: Đủ điều kiện gọi tool.
    COMPARE = "COMPARE"


@dataclass(frozen=True, slots=True)
class ComparisonPlan:
    """Quyết định của một lượt so sánh, kèm đúng tập tên xe sẽ đưa xuống tool."""

    outcome: ComparisonOutcome
    #: Tên xe đã khử trùng, giữ thứ tự khách nêu. Chỉ có nghĩa ở `COMPARE`,
    #: `DUPLICATE_VEHICLE` (một tên) và `NEED_MORE_VEHICLES` (một tên).
    vehicle_names: tuple[str, ...] = ()
    #: Số tên xe trước khi cắt trần — để câu trả lời nói đúng "anh/chị nêu 4 mẫu".
    requested_count: int = 0

    @property
    def should_call_tool(self) -> bool:
        return self.outcome is ComparisonOutcome.COMPARE


def has_comparison_cue(user_message: str) -> bool:
    """Câu này có mang ý so sánh không — kể cả khi không có chữ "so sánh".

    Trả `True` cho hai nhóm: nói thẳng ("so sánh", "khác gì nhau") và hỏi chọn
    ("nên mua … hay …", "… tốt hơn"). Nhóm thứ hai một mình chưa đủ để gọi tool;
    `plan_comparison` mới là chỗ ràng buộc thêm điều kiện ≥2 xe.
    """

    normalized = normalize(user_message)
    if not normalized:
        return False
    return _contains_any(normalized, _EXPLICIT_COMPARISON_CUES) or _contains_any(normalized, _CHOICE_CUES)


def is_explicit_comparison(user_message: str) -> bool:
    """Câu có chữ nói thẳng ý so sánh (không tính nhóm hỏi chọn)."""

    normalized = normalize(user_message)
    return bool(normalized) and _contains_any(normalized, _EXPLICIT_COMPARISON_CUES)


def asks_which_to_choose(user_message: str) -> bool:
    """Khách có hỏi thẳng "nên chọn/mua xe nào" không.

    Tách khỏi `has_comparison_cue` vì hai câu hỏi khác nhau: cái kia quyết định
    lượt có vào nhánh so sánh không, cái này quyết định đoạn tóm tắt được phép
    khuyến nghị hay phải trung lập. Một câu có thể vừa nói thẳng "so sánh" vừa
    hỏi "nên chọn cái nào", nên không suy được cái này từ cái kia.
    """

    normalized = normalize(user_message)
    return bool(normalized) and _contains_any(normalized, _CHOICE_CUES)


def plan_comparison(
    *,
    user_message: str,
    vehicle_names: Sequence[str],
    assume_comparison: bool = False,
) -> ComparisonPlan:
    """Chốt xem lượt này có được gọi `compare_vehicles` không, và với xe nào.

    `vehicle_names` là tên đã CHUẨN HOÁ do Lớp 2 / bộ trích slot trả về — hàm này
    không tự đoán thêm tên nào từ câu chữ.

    Danh sách ca BẮT BUỘC audit khi sửa hàm này (không phải danh sách đầy đủ
    tuyệt đối — gặp ca mới thì bổ sung vào đây kèm test):

    - khoảng trắng tuỳ ý trong mã xe: `vf 2`, `vf2`, `vf  3`, `VF 3`, `Vf3`;
    - có dấu / không dấu, hoa thường lẫn lộn: `vinfast vf3`, `VINFAST VF 3`;
    - từ nối khác nhau: `vs`, `với`, `và`, `so với`, `hay`, `vf3-vf5`, `vf3, vf5, vf6`;
    - tên đầy đủ lẫn tên rút gọn trong cùng câu: "so sánh VinFast VF3 với vf5";
    - câu không có chữ "so sánh": "vf3 hay vf5 tốt hơn", "nên mua vf3 hay vf5";
    - gõ trùng cùng một xe: "so sánh vf3 và vf3" → KHÔNG gọi tool;
    - trộn ô tô với xe máy điện: "so sánh vf3 với evo200" → HỢP LỆ, P-150 bán cả hai;
    - liệt kê quá `MAX_COMPARISON_VEHICLES` mẫu → KHÔNG gọi tool, xin thu gọn.

    Bốn ca đầu là việc của Lớp 2 và đã có test ở `tests/agents/unit/domain/
    test_fuzzy_match.py`; ở đây chỉ kiểm rằng chúng đi tới được tập tên xe đúng.
    """

    normalized = normalize(user_message)
    unique = _in_message_order(normalized, _dedupe(vehicle_names))
    if not (assume_comparison or has_comparison_cue(user_message)):
        return ComparisonPlan(
            outcome=ComparisonOutcome.NOT_A_COMPARISON,
            vehicle_names=unique,
            requested_count=len(unique),
        )
    if not unique:
        # Khách nói rõ muốn so sánh nhưng chưa nêu xe nào ("tôi muốn so sánh
        # xe"). Chỉ nhận khi câu NÓI THẲNG ý so sánh, hoặc khi lượt này đã nằm
        # sẵn trong trạng thái chờ: nhóm cue hỏi-chọn một mình quá rộng — "nên
        # mua xe gì" cũng khớp, mà đó là một câu tư vấn chọn xe, không phải một
        # câu so sánh, và cướp nó về nhánh này sẽ giết luồng ADVISORY.
        if assume_comparison or is_explicit_comparison(user_message):
            return ComparisonPlan(outcome=ComparisonOutcome.NEED_ANY_VEHICLE)
        return ComparisonPlan(outcome=ComparisonOutcome.NOT_A_COMPARISON)
    if len(unique) < MIN_COMPARISON_VEHICLES:
        # Một xe duy nhất: hoặc khách gõ trùng ("vf3 và vf3"), hoặc khách mới nêu
        # được một mẫu. Hai ca này cần hai câu trả lời khác nhau, và chỉ đếm số
        # LẦN XUẤT HIỆN trong câu gốc mới phân biệt được — Lớp 2 khử trùng theo
        # canonical nên "vf3 và vf3" tới đây đã chỉ còn một entity.
        if unique and _mention_count(normalized, unique[0]) >= MIN_COMPARISON_VEHICLES:
            return ComparisonPlan(
                outcome=ComparisonOutcome.DUPLICATE_VEHICLE,
                vehicle_names=unique,
                requested_count=_mention_count(normalized, unique[0]),
            )
        return ComparisonPlan(
            outcome=ComparisonOutcome.NEED_MORE_VEHICLES,
            vehicle_names=unique,
            requested_count=len(unique),
        )
    if len(unique) > MAX_COMPARISON_VEHICLES:
        return ComparisonPlan(
            outcome=ComparisonOutcome.TOO_MANY_VEHICLES,
            vehicle_names=unique,
            requested_count=len(unique),
        )
    return ComparisonPlan(
        outcome=ComparisonOutcome.COMPARE,
        vehicle_names=unique,
        requested_count=len(unique),
    )


def _contains_any(normalized_text: str, keywords: Sequence[str]) -> bool:
    """Từ khoá xuất hiện theo RANH GIỚI TỪ trong câu đã chuẩn hoá.

    Ranh giới là bắt buộc, không phải để chặt chẽ cho đẹp: bỏ dấu làm không gian
    từ hẹp lại nên so chuỗi con sẽ cho "so voi" khớp vào "so voi" của "kích thước
    so voi"… và tệ hơn, "vs" khớp vào giữa mọi từ có "vs". Cùng khuôn với
    `domain/text_normalization.contains_keyword`.
    """

    return any(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", normalized_text) for keyword in keywords)


def has_list_connector(user_message: str) -> bool:
    """Câu có từ nối liệt kê giữa các tên xe không (`vs`, `và`, `hay`, `với`)."""

    normalized = normalize(user_message)
    return bool(normalized) and _CONNECTOR_PATTERN.search(normalized) is not None


def _dedupe(vehicle_names: Sequence[str]) -> tuple[str, ...]:
    """Khử trùng theo dạng đã bỏ khoảng trắng, giữ thứ tự khách nêu.

    "VinFast VF3" và "vf 3" là cùng một xe: khử theo chuỗi thô sẽ để lọt hai cột
    giống hệt nhau vào bảng so sánh.
    """

    seen: dict[str, str] = {}
    for name in vehicle_names:
        key = squash(name)
        if key and key not in seen:
            seen[key] = name
    return tuple(seen.values())


def _in_message_order(normalized_message: str, vehicle_names: Sequence[str]) -> tuple[str, ...]:
    """Xếp tên xe theo thứ tự chúng XUẤT HIỆN trong câu khách viết.

    Cột của bảng phải đọc theo đúng thứ tự câu hỏi: "so sánh VF 5 với VF 3" mà
    trả bảng đặt VF 3 trước là bắt khách tự ánh xạ lại. Thứ tự đầu vào không dùng
    được vì nó là hợp của hai nguồn nhận diện — bộ trích slot xếp theo cách mô
    hình liệt kê, Lớp 2 xếp theo điểm khớp giảm dần, và cả hai đều không phải thứ
    tự khách viết.

    Tên không tìm thấy trong câu (bộ trích suy ra từ ngữ cảnh hội thoại trước)
    được đẩy về cuối, giữ nguyên thứ tự tương đối.
    """

    def position(name: str) -> tuple[int, int]:
        found = _first_index(normalized_message, name)
        return (1, 0) if found is None else (0, found)

    return tuple(sorted(vehicle_names, key=position))


def _first_index(normalized_message: str, vehicle_name: str) -> int | None:
    """Vị trí xuất hiện đầu tiên của một mẫu xe, hoặc `None`."""

    match = _mention_pattern(vehicle_name)
    if match is None:
        return None
    found = match.search(normalized_message)
    return None if found is None else found.start()


def _mention_pattern(vehicle_name: str) -> re.Pattern[str] | None:
    """Regex khớp mọi cách viết của một mẫu xe trong câu ĐÃ CHUẨN HOÁ."""

    spaced, joined = normalize(vehicle_name), squash(vehicle_name)
    forms = {form for form in (spaced, joined) if form}
    if not forms:
        return None
    body = "|".join(re.escape(form) for form in sorted(forms, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{body})(?![a-z0-9])")


def _mention_count(normalized_message: str, vehicle_name: str) -> int:
    """Số lần một mẫu xe xuất hiện trong câu, đếm cả cách viết liền lẫn có cách.

    Đếm trên câu ĐÃ CHUẨN HOÁ nên "VF3" và "vf 3" trong cùng một câu đều được
    tính; đó chính là ca "so sánh VF3 với vf 3" mà khách gõ trùng mà không biết.
    """

    pattern = _mention_pattern(vehicle_name)
    return 0 if pattern is None else len(pattern.findall(normalized_message))


__all__ = [
    "COMPARE_TARGETS_SLOT",
    "MAX_COMPARISON_VEHICLES",
    "MIN_COMPARISON_VEHICLES",
    "ComparisonOutcome",
    "ComparisonPlan",
    "asks_which_to_choose",
    "has_comparison_cue",
    "has_list_connector",
    "is_explicit_comparison",
    "plan_comparison",
]
