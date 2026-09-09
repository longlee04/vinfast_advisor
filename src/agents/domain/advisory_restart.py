"""Phân biệt "mở một lượt tư vấn MỚI" với "nói thêm cho lượt đang chạy".

Bug đã quan sát trên hội thoại thật:

    khách: tôi cần tư vấn xe          → bot hỏi ô tô điện hay xe máy điện
    khách: xe ô tô điện               → bot liệt kê danh mục, hỏi ngân sách
    khách: 900 triệu và cho 5 người   → bot trả VF5, VF6 Eco, VF6 Plus
    khách: tôi muốn tư vấn xe         → bot trả lại NGUYÊN VẸN ba xe đó

Lượt cuối là ĐÚNG câu đã mở đầu hội thoại, nhưng lần này `conversation_slots`
còn nguyên `vehicle_type`/`budget_max_vnd`/`passenger_count` của lượt trước. Cây
slot A3-1 thấy không thiếu gì nên không hỏi lại câu nào, và bộ lọc chạy lại với
đúng tiêu chí cũ — ra đúng kết quả cũ. Không có bước nào của pipeline hỏi câu
"khách đang bắt đầu lại hay đang nói tiếp", nên module này trả lời câu đó.

Luật ở đây là DETERMINISTIC, cùng khuôn với `domain/conversation_control.py`:
một lượt reset xoá tiến độ của khách, nên nó không được phụ thuộc vào một lần
gọi LLM có thể trả khác nhau giữa hai lần chạy.

Có HAI cánh cửa dẫn tới lệnh bắt đầu lại, và cửa thứ hai sinh ra từ một ca
tái hiện thứ hai mà cửa thứ nhất để lọt:

    khách: tôi cần tư vấn xe ô tô giá từ 400 - 900 triệu → VF 8, VF 6 Plus, VF 7
    khách: xe vf 5 đi được bao nhiêu km/1 lần sạc        → trả lời thông số VF 5
    khách: tôi cần tư vấn xe ô tô điện                   → trả lại NGUYÊN VẸN ba xe cũ

Lượt cuối không nhắc một chữ nào về tiền, nhưng `budget_min_vnd`/`budget_max_vnd`
của lượt đầu vẫn còn, nên bộ lọc lại chạy theo khoảng 400–900 triệu.

    Cửa 1 — LỜI NHỜ TƯ VẤN TRẦN. Bỏ cụm nhờ tư vấn ra, phần còn lại chỉ là hư từ
    ("tôi muốn tư vấn xe", "cho tôi tư vấn lại", "tư vấn xe mới").

    Cửa 2 — CÂU MỞ MỘT CUỘC TƯ VẤN. Động từ nhờ tư vấn gắn thẳng vào tân ngữ
    "xe"/"ô tô"/"xe máy" ("tôi cần tư vấn xe ô tô điện", "tư vấn xe cho gia đình
    5 người"). Đây là ĐÚNG khuôn câu mở đầu hội thoại, nên nó mở một cuộc mới kể
    cả khi có kèm tiêu chí — tiêu chí trong chính câu đó được `extract_slots`
    điền lại ngay sau khi reset, còn tiêu chí của cuộc CŨ thì không.

Ba trường hợp bị chặn trước cả hai cửa, vì chúng có chữ "tư vấn" mà không phải
lệnh bắt đầu lại: xin gặp tư vấn viên bằng xương bằng thịt, nói tiếp ("tư vấn
thêm", "tư vấn tiếp"), và câu có nêu tên một mẫu xe cụ thể — nêu tên mẫu nghĩa
là đang hỏi về mẫu đó, không phải mở lại một cuộc chọn xe từ đầu.

Nhờ vậy "900 triệu và cho 5 người" hay "vậy còn xe 7 chỗ thì sao" không bao giờ
chạm tới nhánh reset.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.canonical_text import CanonicalText, build_canonical_text
from src.agents.domain.entity_catalog import SEED_CAR_MODELS, SEED_MOTORBIKE_MODELS
from src.agents.domain.values import SlotName


class AdvisoryFlowAction(StrEnum):
    """Lượt này nối tiếp cuộc tư vấn đang chạy, hay mở một cuộc mới."""

    CONTINUE = "CONTINUE"
    #: [GIẢ ĐỊNH] Tên intent mới. Không tái dùng `Intent.ADVISORY`: `Intent` là
    #: nhãn của thứ khách muốn NHẬN và được `intent_reconciliation` chốt sau
    #: `extract_slots`, còn đây là một lệnh điều khiển phiên phải chạy TRƯỚC khi
    #: vào graph — cùng họ với `ConversationControlAction`, không cùng họ với
    #: `Intent`.
    RESTART_ADVISORY = "RESTART_ADVISORY"


def _ascii_fold(value: str) -> str:
    """Bỏ dấu và hạ thường — khai TRƯỚC các hằng số vì chúng dựng regex từ nó."""

    normalized = unicodedata.normalize("NFKD", value.casefold()).replace("đ", "d")
    return "".join(char for char in normalized if not unicodedata.combining(char))


#: Slot bị xoá khi khách mở lượt tư vấn mới — TOÀN BỘ cây A3-1.
#:
#: Lấy từ `SlotName` chứ không liệt kê tay: thêm một slot vào cây mà quên thêm
#: vào đây thì slot đó sống sót qua lệnh reset và con bug quay lại dưới hình
#: hài mới. Tỉnh/thành của luồng giá lăn bánh KHÔNG nằm trong `SlotName` nên nó
#: cũng không bị đụng tới — đúng ý: reset tư vấn không phải huỷ tra cứu giá.
#: `interest_vehicle` là bối cảnh (xe khách vừa xem), không phải tiêu chí: "anh muốn tư
#: vấn" ngay sau khi xem VF 5 phải GIỮ nó (Sếp 2026-08-29); chỉ "bắt đầu lại" mới xoá.
RESTART_SLOTS: Final[frozenset[str]] = frozenset(
    slot.value for slot in SlotName if slot is not SlotName.INTEREST_VEHICLE
)

#: Động từ cho thấy khách đang NHỜ TƯ VẤN, chứ không hỏi số liệu một mẫu xe.
_ADVISE_VERB: Final[str] = r"(?:tu\s*van|tim\s*(?:mua\s*)?xe|chon\s*(?:mua\s*)?xe|mua\s*xe|goi\s*y\s*xe)"
_ADVISORY_REQUEST: Final[re.Pattern[str]] = re.compile(rf"\b{_ADVISE_VERB}\b")

#: Hư từ được phép chen giữa động từ nhờ tư vấn và tân ngữ "xe" mà câu vẫn là
#: một câu mở cuộc tư vấn: "tư vấn CHO TÔI xe khác", "tư vấn GIÚP EM xe 7 chỗ".
#:
#: Cố ý KHÔNG nhận "thêm"/"tiếp" ở đây — xem `_CONTINUATION_TOKENS`.
_ADVISE_CONNECTOR: Final[str] = r"(?:cho|giup|gium|dum|ho|toi|minh|em|anh|chi|ban|mot|1)"

#: CỬA 2 — câu mở một cuộc tư vấn: động từ nhờ tư vấn gắn thẳng vào tân ngữ chỉ
#: PHƯƠNG TIỆN. Đây là khuôn của chính câu mở đầu hội thoại, nên nó mở một cuộc
#: mới kể cả khi câu có kèm tiêu chí ("tư vấn xe ô tô giá từ 400 - 900 triệu").
#:
#: Bắt buộc phải có tân ngữ: "tư vấn giúp em trả góp thế nào" hỏi về một thủ tục
#: chứ không mở lại việc chọn xe, và nó không được phép xoá tiến độ của khách.
_ADVISORY_OPENING: Final[re.Pattern[str]] = re.compile(
    rf"\b{_ADVISE_VERB}\b(?:\s+{_ADVISE_CONNECTOR}\b)*\s*\b(?:xe|o\s*to|oto|xe\s*may)\b"
)

#: Khách xin gặp NGƯỜI THẬT. Có chữ "tư vấn" nhưng không phải lệnh bắt đầu lại,
#: và nhánh handoff/HITL mới là nhánh phải nhận câu này.
_HUMAN_ADVISOR: Final[re.Pattern[str]] = re.compile(r"\btu\s*van\s*vien\b")

#: Dấu hiệu NÓI TIẾP. "tư vấn thêm cho tôi" là xin thêm mẫu trong cùng tiêu chí,
#: không phải xoá tiêu chí đi làm lại.
_CONTINUATION_TOKENS: Final[frozenset[str]] = frozenset({"them", "tiep"})

#: Câu có nêu tên một mẫu xe cụ thể là câu HỎI VỀ MẪU ĐÓ. Dựng từ seed của
#: `entity_catalog` chứ không gõ lại: thêm một mẫu vào danh mục mà quên chép
#: sang đây thì "tư vấn xe VF 10 giúp em" lại xoá tiến độ của khách.
_MODEL_MENTION: Final[re.Pattern[str]] = re.compile(
    "|".join(
        sorted(
            (
                r"\b" + r"\s*".join(re.escape(part) for part in _ascii_fold(name).split()) + r"\b"
                for name in (*SEED_CAR_MODELS, *SEED_MOTORBIKE_MODELS)
            ),
            key=len,
            reverse=True,
        )
    )
)

#: CỬA 1 — hư từ được phép còn lại sau khi bỏ cụm nhờ tư vấn. Cố ý HẸP: mỗi chữ
#: thêm vào đây là một câu nữa có thể xoá tiến độ của khách, nên chỉ nhận đại từ,
#: từ đệm, và các dấu hiệu "làm lại" ("lại", "mới", "khác", "từ đầu", "lần nữa").
#:
#: Vắng mặt có chủ đích: "tiếp", "thêm" (nói tiếp, không phải làm lại), "này",
#: "đó" (trỏ về thứ đang bàn), mọi token có chữ số, và mọi từ chỉ loại xe
#: ("ô", "tô", "máy").
#:
#: Vắng "ô"/"tô"/"máy" KHÔNG còn nghĩa là "tư vấn xe ô tô điện" bị coi là nói
#: tiếp: câu đó đi qua CỬA 2 (`_ADVISORY_OPENING`) và không bao giờ tới được
#: đây. Cửa 1 chỉ còn nhận những câu nhờ tư vấn không có tân ngữ phương tiện
#: nào cả ("cho tôi tư vấn lại", "tư vấn lại từ đầu").
_FILLER_TOKENS: Final[frozenset[str]] = frozenset(
    {
        # đại từ, xưng hô, từ đệm cuối câu
        "toi",
        "minh",
        "em",
        "e",
        "anh",
        "chi",
        "ban",
        "a",
        "ah",
        "ak",
        "oi",
        "nhe",
        "nha",
        "voi",
        "vs",
        "chao",
        "xin",
        "on",
        "lam",
        # động từ nhờ vả
        "muon",
        "can",
        "nho",
        "hay",
        "thich",
        "dinh",
        "dang",
        "se",
        "giup",
        "gium",
        "dum",
        "ho",
        "cho",
        "di",
        # hư từ nối
        "cai",
        "con",
        "the",
        "thi",
        "la",
        "va",
        "cung",
        "ve",
        # tân ngữ trung tính, không mang tiêu chí nào
        "xe",
        "dien",
        "vinfast",
        # dấu hiệu LÀM LẠI
        "lai",
        "moi",
        "khac",
        "tu",
        "dau",
        "bat",
        "lan",
        "nua",
    }
)


@dataclass(frozen=True, slots=True)
class AdvisoryFlowDecision:
    """Kết luận kèm LÝ DO — lý do là thứ đọc được trong log khi truy bug sau này."""

    action: AdvisoryFlowAction
    reason: str


def classify_advisory_flow(user_message: str, canonical: CanonicalText | None = None) -> AdvisoryFlowDecision:
    """Lượt này có phải lệnh bắt đầu lại cuộc tư vấn không.

    So khớp trên `canonical.folded` sinh tại chain (ENG REVIEW AMENDMENT 2) —
    gate không tự normalize. Vắng mặt thì tự dựng từ `user_message` (đường
    tương thích cho test double).
    """

    canonical = canonical or build_canonical_text(user_message)
    text = canonical.folded
    if not text:
        return AdvisoryFlowDecision(AdvisoryFlowAction.CONTINUE, "tin nhan rong")
    if _ADVISORY_REQUEST.search(text) is None:
        return AdvisoryFlowDecision(AdvisoryFlowAction.CONTINUE, "khong co cum nho tu van")

    # Ba chốt chặn chạy TRƯỚC cả hai cửa: chúng đều có chữ "tư vấn" mà không câu
    # nào là lệnh bắt đầu lại, nên để lọt xuống dưới là xoá tiến độ của khách.
    if _HUMAN_ADVISOR.search(text) is not None:
        return AdvisoryFlowDecision(AdvisoryFlowAction.CONTINUE, "khach xin gap tu van vien")
    model = _MODEL_MENTION.search(text)
    if model is not None:
        return AdvisoryFlowDecision(
            AdvisoryFlowAction.CONTINUE,
            f"cau hoi ve mot mau xe cu the: {model.group(0)}",
        )
    tokens = _tokens(text)
    continued = [token for token in tokens if token in _CONTINUATION_TOKENS]
    if continued:
        return AdvisoryFlowDecision(
            AdvisoryFlowAction.CONTINUE,
            f"dau hieu noi tiep cuoc dang chay: {' '.join(continued)}",
        )

    opening = _ADVISORY_OPENING.search(text)
    if opening is not None:
        return AdvisoryFlowDecision(
            AdvisoryFlowAction.RESTART_ADVISORY,
            f"cau mo mot cuoc tu van moi: {' '.join(opening.group(0).split())}",
        )
    remainder = _ADVISORY_REQUEST.sub(" ", text)
    carried = [token for token in _tokens(remainder) if token not in _FILLER_TOKENS]
    if carried:
        return AdvisoryFlowDecision(
            AdvisoryFlowAction.CONTINUE,
            f"cau con mang thong tin cho luot dang chay: {' '.join(carried)}",
        )
    return AdvisoryFlowDecision(
        AdvisoryFlowAction.RESTART_ADVISORY,
        "loi nho tu van tran, khong kem tieu chi nao",
    )


def _tokens(text: str) -> list[str]:
    return [token for token in re.split(r"[^0-9a-z]+", text) if token]


__all__ = [
    "RESTART_SLOTS",
    "AdvisoryFlowAction",
    "AdvisoryFlowDecision",
    "classify_advisory_flow",
]
