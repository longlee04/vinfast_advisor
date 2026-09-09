"""Máy trạng thái chặng SAU khi đã đề xuất xe.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

Sếp 2026-08-26 vẽ luồng: khách chọn mẫu → gửi thông tin xe → tính chi phí sử
dụng → hết lăn tăn thì mời lái thử (chọn luôn showroom gần nhất), còn lăn tăn thì
qua tư vấn viên cấp ưu đãi rồi **quay lại** mời lái thử.

**Vì sao phải có trạng thái tường minh.** Chặng này có năm điểm dừng, mà cả hệ
chỉ có một cờ `pending_question` nói được "đang chờ trả lời" — không nói đang chờ
trả lời CÁI GÌ. Không có máy trạng thái thì lượt sau đọc nhầm ý: khách gõ "không"
có thể là "không cần tính năng", "không còn lăn tăn", hay "không muốn lái thử",
và ba câu đó dẫn đi ba hướng khác hẳn nhau.

Lưu trong `ActiveTask.form` (`TaskType.POST_PITCH`) — nó sẵn có TTL, revision và
compare-before-write, đúng ba thứ một máy trạng thái nhiều lượt cần.

**Hai chốt an toàn, cả hai đều học từ lỗi thật:**

- `MAX_HITL_ROUNDS` chặn vòng lặp `lăn tăn → tư vấn viên → ưu đãi → lái thử →
  lăn tăn → …`. Không chặn thì hai bên quay mãi.
- `HITL_WAIT_LIMIT` là hạn chờ tư vấn viên. Hết hạn thì vẫn mời lái thử: tư vấn
  viên không online mà luồng đứng im là khách bị treo, và nhánh "quay về lái thử"
  không bao giờ chạy.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Final

#: Số vòng HITL tối đa cho một phiên. Vòng thứ ba thì đưa thẳng sang lái thử —
#: khách đã gặp tư vấn viên hai lần, quay thêm không giải quyết được gì.
MAX_HITL_ROUNDS: Final[int] = 2

#: Chờ tư vấn viên quá mốc này thì luồng tự đi tiếp. Không có mốc thì một phiên
#: mở ngoài giờ làm việc treo tới sáng hôm sau.
HITL_WAIT_LIMIT: Final[timedelta] = timedelta(minutes=30)


class PostPitchStage(StrEnum):
    """Điểm dừng hiện tại của chặng sau đề xuất."""

    #: Vừa gửi bản đề xuất, đang chờ khách nói mẫu nào.
    AWAITING_CHOICE = "AWAITING_CHOICE"
    #: Đã gửi thông tin xe + chi phí; đang chờ khách chọn MỘT trong hai lối:
    #: đặt lịch lái thử, hay nêu điều còn vướng.
    #:
    #: Chặng này thay cho `AWAITING_CONCERN` + `AWAITING_TEST_DRIVE` cũ (Sếp
    #: 2026-08-26). Hai chặng đó hỏi hai câu cho MỘT quyết định, và câu đầu là
    #: câu MỞ ("còn băn khoăn gì không") nên mọi lời đáp ngắn đều rơi vào vùng
    #: không đọc được. Câu gộp nêu rõ cả hai lối, nên bộ đọc chỉ phân biệt hai
    #: nhánh khách vừa được nghe tên.
    AWAITING_DECISION = "AWAITING_DECISION"
    #: Còn băn khoăn; đã chuyển tư vấn viên và đang chờ ưu đãi.
    IN_HITL = "IN_HITL"
    #: Tư vấn viên vừa cấp ưu đãi, đã báo khách, đang chờ khách nói CÓ/KHÔNG
    #: cho câu "em tính lại chi phí lăn bánh nhé".
    #:
    #: Chặng riêng, không gộp vào `AWAITING_DECISION` (Sếp 2026-08-27): ở đó chữ
    #: "có" nghĩa là NHẬN LỜI LÁI THỬ, còn ở đây nó nghĩa là XIN TÍNH LẠI GIÁ.
    #: Cùng một tiếng "có", hai việc khác hẳn — gộp lại là mời khách đi lái thử
    #: khi họ chỉ muốn xem con số.
    AWAITING_COST_CONSENT = "AWAITING_COST_CONSENT"
    #: Đã đồng ý lái thử, đang chờ khách chọn showroom + khung giờ.
    AWAITING_SLOT = "AWAITING_SLOT"
    #: Chặng đóng lại — đã đăng ký lái thử, hoặc khách dừng.
    DONE = "DONE"


_STAGE_KEY: Final[str] = "stage"
_VEHICLE_KEY: Final[str] = "vehicle_name"
_ROUNDS_KEY: Final[str] = "hitl_rounds"
_WAIT_SINCE_KEY: Final[str] = "hitl_since"


#: Chặng của bản CŨ → chặng tương đương hôm nay.
#:
#: Bắt buộc phải có, không phải để cho đẹp: `active_task_state` là JSON đã nằm
#: trong DB prod. Đổi tên chặng mà không ánh xạ thì mọi phiên đang mở giữa chừng
#: đọc ra `None`, chặng biến mất, và khách đang chờ đặt lịch bị bỏ giữa đường.
_LEGACY_STAGES: Final[dict[str, PostPitchStage]] = {
    # Xin quãng đường: giờ dùng mốc mặc định, khách rơi thẳng vào câu hai lối.
    "AWAITING_DISTANCE": PostPitchStage.AWAITING_DECISION,
    # Hai chặng cũ đã gộp làm một.
    "AWAITING_CONCERN": PostPitchStage.AWAITING_DECISION,
    "AWAITING_TEST_DRIVE": PostPitchStage.AWAITING_DECISION,
}


def stage_of(form: Mapping[str, Any] | None) -> PostPitchStage | None:
    """Đọc chặng từ `ActiveTask.form`; giá trị lạ coi như KHÔNG có chặng nào.

    Không raise: `form` là JSON đọc từ DB, có thể do một bản cũ ghi. Vỡ ở đây là
    vỡ cả lượt của khách vì một giá trị lịch sử.
    """

    if not form:
        return None
    raw = str(form.get(_STAGE_KEY))
    try:
        return PostPitchStage(raw)
    except ValueError:
        return _LEGACY_STAGES.get(raw)


_PRICE_KEY: Final[str] = "vehicle_price_vnd"


def remember_vehicle_price(price_vnd: str) -> dict[str, Any]:
    """Nhớ GIÁ NIÊM YẾT của mẫu đang bàn, để lúc cấp ưu đãi nói được "còn bao nhiêu".

    Ghi ở đây vì `chain._cost_summary` là chỗ duy nhất vừa biết mẫu xe vừa vừa
    đọc xong giá từ snapshot. Tầng duyệt của tư vấn viên không có cổng catalog
    nào, nên không có dòng này thì thông báo ưu đãi chỉ nói được mức giảm — và
    bắt khách tự trừ ra con số họ sẽ đem đi so với đại lý.
    """

    return {_PRICE_KEY: price_vnd}


def vehicle_price(form: Mapping[str, Any] | None) -> str | None:
    """Giá niêm yết đã nhớ của mẫu đang bàn, nếu có."""

    if not form:
        return None
    value = form.get(_PRICE_KEY)
    return value.strip() if isinstance(value, str) and value.strip() else None


def remember_chosen_vehicle(vehicle_name: str) -> dict[str, Any]:
    """Ghi tên mẫu đang bàn vào form mà KHÔNG đụng tới chặng.

    Nút khung giờ sinh từ công cụ tìm showroom (khách trả lời câu hỏi vị trí)
    không đi qua `after_choice`, nên lượt sau bấm nút thì không ai biết đang đặt
    lịch cho xe nào — và thiếu tên xe thì không tra được `vehicle_id`, lịch
    không ghi được. Bug thật trên prod 2026-08-27: nút hiện đủ, bấm vào lại nhận
    một thẻ xe.

    Khác `after_choice` ở chỗ nó KHÔNG chuyển chặng: khách mới trả lời câu hỏi
    vị trí, chưa quyết định gì thêm.
    """

    return {_VEHICLE_KEY: vehicle_name}


def chosen_vehicle(form: Mapping[str, Any] | None) -> str | None:
    """Tên mẫu khách đã chốt, nếu có."""

    if not form:
        return None
    name = form.get(_VEHICLE_KEY)
    return name.strip() if isinstance(name, str) and name.strip() else None


def hitl_rounds(form: Mapping[str, Any] | None) -> int:
    """Số vòng đã qua tư vấn viên. Giá trị lạ coi như chưa vòng nào."""

    if not form:
        return 0
    value = form.get(_ROUNDS_KEY)
    return value if isinstance(value, int) and value >= 0 else 0


def start_after_pitch() -> dict[str, Any]:
    """Chặng bắt đầu ngay sau khi gửi bản đề xuất."""

    return {_STAGE_KEY: PostPitchStage.AWAITING_CHOICE.value, _ROUNDS_KEY: 0}


def after_choice(form: Mapping[str, Any] | None, *, vehicle_name: str) -> dict[str, Any]:
    """Khách vừa chốt mẫu → gửi thông tin xe + chi phí và hỏi câu hai lối.

    Không còn nhánh "thiếu quãng đường thì xin trước" (Sếp 2026-08-26): bảng chi
    phí chạy được với mốc mặc định 30 km/ngày và NÓI RA mốc đó, nên không lượt
    nào phải dừng lại để xin một con số chiếm chưa tới 9% tổng tiền.
    """

    updated = dict(form or {})
    updated[_VEHICLE_KEY] = vehicle_name
    updated[_STAGE_KEY] = PostPitchStage.AWAITING_DECISION.value
    updated.setdefault(_ROUNDS_KEY, 0)
    return updated


def after_concern(form: Mapping[str, Any] | None, *, has_concern: bool, now: datetime) -> dict[str, Any]:
    """Khách trả lời câu hỏi hai lối.

    Còn vướng → tư vấn viên, TRỪ KHI đã đủ số vòng: lúc đó ở lại chặng quyết
    định. Quay vòng thêm không giải quyết được gì mà khách phải chờ thêm lần nữa.
    """

    updated = dict(form or {})
    if not has_concern or hitl_rounds(form) >= MAX_HITL_ROUNDS:
        updated[_STAGE_KEY] = PostPitchStage.AWAITING_DECISION.value
        return updated
    updated[_STAGE_KEY] = PostPitchStage.IN_HITL.value
    updated[_ROUNDS_KEY] = hitl_rounds(form) + 1
    updated[_WAIT_SINCE_KEY] = now.isoformat()
    return updated


def after_offer(form: Mapping[str, Any] | None) -> dict[str, Any]:
    """Hết hạn chờ tư vấn viên → quay lại câu hỏi hai lối.

    Dùng cho nhánh QUÁ HẠN, không phải nhánh có ưu đãi thật: ưu đãi thật đi qua
    `after_offer_granted` vì nó còn phải chờ khách đáp câu mời tính lại giá.
    """

    updated = dict(form or {})
    updated[_STAGE_KEY] = PostPitchStage.AWAITING_DECISION.value
    updated.pop(_WAIT_SINCE_KEY, None)
    return updated


def after_offer_granted(form: Mapping[str, Any] | None) -> dict[str, Any]:
    """Tư vấn viên đã cấp ưu đãi và khách đã được báo → chờ khách đồng ý tính lại.

    Sếp 2026-08-27: KHÔNG trừ thẳng rồi thay số. Một cái tổng lặng lẽ đổi giữa
    cuộc nói chuyện là chỗ mất niềm tin nhanh nhất — khách không biết nó đổi vì
    ưu đãi hay vì ta vừa sửa gì khác.
    """

    updated = dict(form or {})
    updated[_STAGE_KEY] = PostPitchStage.AWAITING_COST_CONSENT.value
    updated.pop(_WAIT_SINCE_KEY, None)
    return updated


def hitl_wait_expired(form: Mapping[str, Any] | None, *, now: datetime) -> bool:
    """Chờ tư vấn viên quá hạn chưa?

    Không có mốc bắt đầu thì coi như CHƯA quá hạn — chiều an toàn ở đây là để
    khách chờ thêm, còn kết luận "quá hạn" từ một giá trị hỏng là cắt ngang một
    cuộc trao đổi đang diễn ra thật.
    """

    if stage_of(form) is not PostPitchStage.IN_HITL:
        return False
    raw = (form or {}).get(_WAIT_SINCE_KEY)
    if not isinstance(raw, str):
        return False
    try:
        since = datetime.fromisoformat(raw)
    except ValueError:
        return False
    moment = now if now.tzinfo is not None else now.replace(tzinfo=since.tzinfo)
    if since.tzinfo is None:
        since = since.replace(tzinfo=moment.tzinfo)
    return moment - since > HITL_WAIT_LIMIT


def after_test_drive_accepted(form: Mapping[str, Any] | None) -> dict[str, Any]:
    """Khách nhận lời lái thử ⇒ chờ họ chọn showroom + khung giờ.

    Không đặt lịch ngay: hệ chưa biết khách rảnh lúc nào, mà đoán giờ ở bước này
    là hẹn khách tới lúc không ai đợi.
    """

    updated = dict(form or {})
    updated[_STAGE_KEY] = PostPitchStage.AWAITING_SLOT.value
    return updated


def close(form: Mapping[str, Any] | None) -> dict[str, Any]:
    """Chặng đóng lại."""

    updated = dict(form or {})
    updated[_STAGE_KEY] = PostPitchStage.DONE.value
    return updated
