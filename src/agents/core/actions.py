"""Hành động lõi v2 chọn ra sau mỗi lượt (spec mục 6). Thuần dữ liệu."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from src.agents.core.state import CoreState, PendingKind

#: Khoá `pending` / `Ask` — một chỗ định nghĩa, policy và render dùng chung
#: (trước đây rải chuỗi thô ở cả hai file, lệch một chữ là hỏng âm thầm).
PENDING_VEHICLE = "vehicle"
PENDING_SHOWROOM_SLOT = "showroom_slot"
#: MỘT câu hỏi mở duy nhất của luồng tư vấn (ngân sách + mục đích + thói quen).
#: Không phải tên một `SlotName`: câu trả lời cho nó điền NHIỀU slot cùng lúc.
PENDING_PROFILE = "profile"

#: Khoá `Pending(kind=CONFIRM).key` — việc đang treo chờ khách xác nhận.
CONFIRM_BOOK = "book"
CONFIRM_OFFER = "offer"

#: `Lookup.mode`.
LOOKUP_BROWSE = "browse"
LOOKUP_LOOKUP = "lookup"
LOOKUP_POLICY = "policy"

#: `Lookup.aspect` / `Understanding.aspect` — khía cạnh khách hỏi về một mẫu.
#: Chỉ có GIÁ: đó là khía cạnh duy nhất mà bảng tổng quan trả lời SAI cách (đọc
#: cả trang thông số cho một câu hỏi tiền). Thông số khác vẫn đi bảng tổng quan.
ASPECT_PRICE = "price"

#: `Reply.template` — render.py chỉ nhận đúng các giá trị này.
TEMPLATE_SOCIAL = "social"
TEMPLATE_CONCERN = "concern"
TEMPLATE_CANCELLED = "cancelled"
#: Khách nói THÔI, không muốn tư vấn nữa — dừng, không hỏi thêm, không đẩy thẻ.
TEMPLATE_STOPPED = "stopped"
TEMPLATE_CLARIFY = "clarify"
TEMPLATE_CHOSEN_SUMMARY = "chosen_summary"
#: Đề xuất lại mà không có mẫu nào MỚI để nói → một câu ngắn xác nhận lựa chọn
#: cũ, KHÔNG đọc lại nguyên bài (chỉ số "lặp bài", spec mục 8).
TEMPLATE_SAME_PICK = "same_pick"
#: Đã chỉnh theo yêu cầu nhưng không còn mẫu nào khớp hơn — nói thật, kèm mẫu
#: gần nhất, thay vì lặng lẽ đưa lại bản cũ.
TEMPLATE_NO_BETTER = "no_better"

#: `Recommend.reason` — vì sao lượt này chạy đề xuất. Ở cùng file với
#: `Recommend` (policy đặt, act đọc): để riêng bên policy thì act phải import
#: ngược tầng quyết định chỉ để so ba chuỗi.
REASON_FIRST = "first"
REASON_SLOTS_CHANGED = "slots_changed"
REASON_RETRY = "retry"
#: Khách xin CHỈNH bản đề xuất bằng lối so sánh ("rẻ hơn", "cốp rộng hơn") —
#: `Recommend.refine` chở nguyên văn câu đó cho tầng act đọc.
REASON_REVISED = "revised"

#: Khoá đếm số lượt UNCLEAR liên tiếp trong `ask_counts` (không phải tên slot).
UNCLEAR_KEY = "__unclear__"

#: Ba mức kết luận của một lượt đối chiếu xe với nhu cầu (`core/fit.py`).
#:
#: Hằng nằm ở ĐÂY chứ không ở `fit.py` vì cả `fit` lẫn `render` đều đọc chúng,
#: mà `fit` đã import `render` (dùng chung một bộ định dạng tiền) — để hằng bên
#: `fit` là dựng một vòng import giữa hai file thuần.
FIT_YES = "hợp"
FIT_PARTIAL = "hợp một phần"
FIT_UNFIT = "chưa hợp"


def _frozen_args(args: Mapping[str, str] | None) -> Mapping[str, str]:
    return MappingProxyType(dict(args or {}))


@dataclass(frozen=True, slots=True)
class Ask:
    key: str
    kind: PendingKind
    #: Giá trị máy: id xe cho CHOICE, mã tính năng cho SLOT.
    options: tuple[str, ...] = ()
    #: Nhãn khách đọc được, song song `options` — tầng act điền (policy không
    #: biết tên xe). CHOICE thiếu nhãn mà options là id thô → render kêu lỗi.
    labels: tuple[str, ...] = ()
    resume_pending: bool = False
    #: Tên VIỆC đang cần xe ("đặt lái thử", "tính chi phí") — render dùng để câu
    #: "mẫu nào?" nói đúng khung. Log prod 2026-08-31: "đăng ký lái thử" chưa có
    #: xe nhận câu của luồng thông số ("xem mẫu nào để em kể đúng phần cần"),
    #: khách tưởng bot hỏi nơi và gõ "Hà Nội". Rỗng = giữ câu cũ.
    job: str = ""


@dataclass(frozen=True, slots=True)
class Reply:
    template: str
    args: Mapping[str, str] = field(default_factory=lambda: _frozen_args({}))
    resume_pending: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "args", _frozen_args(self.args))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Reply) and (self.template, dict(self.args), self.resume_pending) == (
            other.template,
            dict(other.args),
            other.resume_pending,
        )

    __hash__ = None  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class Recommend:
    #: Vì sao chạy đề xuất — tầng act đọc để khỏi đọc lại nguyên bài:
    #: "first" (lần đầu), "slots_changed" (khách đổi tiêu chí), "retry"
    #: (khách xin mẫu khác mà tiêu chí không đổi → phải loại `exclude_ids`).
    reason: str = "first"
    exclude_ids: tuple[str, ...] = ()
    #: Nguyên văn lời xin chỉnh ("cho em mẫu rẻ hơn"). CHỈ có ở `reason=revised`.
    #: Policy KHÔNG đọc hiểu nó — tầng act đọc bằng `domain/comparative_revision`,
    #: nơi đã có sẵn bảng từ vựng cho 28 mã tính năng và 4 cảm quan.
    refine: str = ""
    #: Loại xe MỚI khi khách đổi giữa chừng ("thôi xe máy đi"). `act` mở đầu bài
    #: bằng một câu nói ra việc chuyển loại — không nói thì bài mới trông y như
    #: lõi lờ mất câu vừa nghe (lượt prod LP03).
    switched_type: str = ""
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Lookup:
    mode: str  # LOOKUP_BROWSE | LOOKUP_LOOKUP | LOOKUP_POLICY
    #: Xe khách gọi ĐÍCH DANH trong lượt tra cứu. Có xe thì `act` trả lời về
    #: CHÍNH chiếc đó; rỗng mới là một lượt duyệt danh mục.
    vehicle_ids: tuple[str, ...] = ()
    #: Khía cạnh hỏi về chiếc đó (`ASPECT_PRICE` hoặc rỗng). Có `vehicle_ids`
    #: mới có nghĩa: hỏi giá mà chưa trỏ ra xe thì vẫn là một lượt duyệt.
    aspect: str = ""
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class NotInCatalog:
    """Khách nêu một tên xe KHÔNG có trong danh mục ("mẫu vf10").

    Prod benchmark2 (2026-08-30): `vehicle_ids=[]` nên policy hỏi cụt "Anh/chị
    muốn xem mẫu nào ạ?" — khách vừa nêu tên xong. Nói thật là chưa có mẫu đó,
    bày danh mục của đúng loại xe suy từ tên, và VẪN treo câu chọn mẫu để câu
    "VF 8" tiếp theo đi đúng đường.
    """

    mention: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Compare:
    vehicle_ids: tuple[str, ...]
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Nearby:
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class VehicleQa:
    vehicle_id: str
    question: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class FitCheck:
    """Đối chiếu MỘT chiếc xe với nhu cầu khách rồi trả lời "có hợp không".

    Hai lối vào (cả hai đều là lượt prod vòng 9): khách vừa CHỌN xe và hỏi luôn
    trong cùng một câu ("ok chọn VF 2 đi, có hợp với nhu cầu của tôi không"), và
    khách kể THÊM nhu cầu sau khi đã chọn ("gia đình tôi có 4 người, tôi muốn đi
    chơi xa") — lượt sau này trước đây trả về đúng câu "em vẫn thấy VF 2 hợp
    nhất", tức lờ mất thứ khách vừa nói.
    """

    vehicle_id: str
    #: Ứng viên để so khi xe đang xét chưa hợp — thường là `recommended_ids`.
    #: `act` còn tự tìm thêm theo tiêu chí MỚI khi danh sách này không vá được.
    alternative_ids: tuple[str, ...] = ()
    #: Lượt này khách vừa chốt xe → câu trả lời mở đầu bằng lời ghi nhận, để
    #: một tin nhắn làm đủ hai việc khách vừa xin.
    just_chosen: bool = False
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class NextSteps:
    """ "Làm sao để chốt xe này" — các bước đi tiếp, không phải một lượt đề xuất lại."""

    vehicle_id: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class ScopeNote:
    """Câu hỏi NGOÀI phạm vi tư vấn xe, hỏi về chiếc xe đang xem.

    Nói thật là em chỉ tư vấn về xe, rồi kéo về đúng thứ giúp được: tầm chạy
    của chính chiếc xe đó. Trước đây lượt này rơi vào đường xin CHỈNH đề xuất
    và khách nhận "em chưa có mẫu nào khác hợp hơn" cho một câu hỏi du lịch.
    """

    vehicle_id: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Tco:
    vehicle_id: str
    resume_pending: bool = False
    #: Lượt chạy-LẠI vì khách vừa nhắc km/tỉnh SAU khi đã có thẻ (policy 5a'):
    #: chữ phải là "em đã cập nhật lại bảng" chứ không phải bài dẫn mới —
    #: client đang thay số TẠI CHỖ trên thẻ cũ (Sếp 2026-08-31).
    refreshed_km: bool = False
    refreshed_province: bool = False


@dataclass(frozen=True, slots=True)
class OnRoadPrice:
    vehicle_id: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class ShowroomOptions:
    vehicle_id: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Book:
    vehicle_id: str
    choice_ref: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class EnqueueHitl:
    vehicle_id: str
    resume_pending: bool = False


@dataclass(frozen=True, slots=True)
class Handoff:
    resume_pending: bool = False
    #: "requested" = khách tự xin gặp người; rỗng = lõi bỏ cuộc (quá trần hỏi).
    reason: str = ""


@dataclass(frozen=True, slots=True)
class Silent:
    resume_pending: bool = False


#: Vì sao lượt rơi xuống agent — hai móc của plan agent-migration §1.3.
OPEN_REASON_UNCLEAR = "unclear"
OPEN_REASON_DEAD_END = "dead_end"


@dataclass(frozen=True, slots=True)
class OpenQuestion:
    """Lõi TẤT ĐỊNH đã tới ngõ cụt — thử trả lời bằng agent loop (chỉ-đọc).

    KHÔNG phải một việc mới: mọi nhánh hỏng của agent đều rơi về ĐÚNG kết quả
    tất định mà hệ thống trả hôm nay (`act._open_question` trả `None`). Vì vậy
    Action này không mang `state_patch` nào và không bao giờ chạm ownership.
    """

    question: str
    reason: str
    vehicle_ids: tuple[str, ...] = ()
    resume_pending: bool = False


Action = (
    Ask
    | Reply
    | Recommend
    | Lookup
    | NotInCatalog
    | Compare
    | Nearby
    | VehicleQa
    | FitCheck
    | NextSteps
    | ScopeNote
    | Tco
    | OnRoadPrice
    | ShowroomOptions
    | Book
    | EnqueueHitl
    | Handoff
    | Silent
    | OpenQuestion
)

#: Hành động không đảo ngược — confidence thấp phải hỏi xác nhận trước (spec mục 5).
IRREVERSIBLE: tuple[type, ...] = (Book, EnqueueHitl)


@dataclass(frozen=True, slots=True)
class Decision:
    action: Action
    state_after: CoreState
