"""Khách trả lời câu "còn băn khoăn gì về mẫu này không".

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

**Vì sao phải có bản đọc tất định TRƯỚC khi hỏi câu này.** Trong đúng một ngày
2026-08-26, ba lần luồng chết vì cùng một hình dạng: bot đặt câu hỏi MỞ, khách
đáp ngắn ("không cần", "thôi không", "có tất cả"), và bộ phân loại phạm vi đọc
câu đáp đó như một tin nhắn lạc đề rồi đóng lượt. Thêm một câu mở nữa mà không
có bản đọc đi kèm là mở thêm đúng cái cửa đó.

Nên module này ra đời **cùng lúc** với câu hỏi, không phải sau khi nó vỡ.

Ba kết quả, không phải hai: `NO_CONCERN`, `HAS_CONCERN`, và `UNCLEAR`. Ép câu mơ
hồ về một trong hai đầu là đoán hộ khách — "cũng được" không nói lên họ đã yên
tâm hay đang ngần ngại. Câu mơ hồ thì hỏi lại, đừng đoán.
"""

from __future__ import annotations

import re
import unicodedata
from enum import StrEnum
from typing import Final


class ConcernReply(StrEnum):
    """Khách đã yên tâm, còn vướng, hay chưa rõ."""

    NO_CONCERN = "NO_CONCERN"
    HAS_CONCERN = "HAS_CONCERN"
    UNCLEAR = "UNCLEAR"


class PostPitchDecision(StrEnum):
    """Khách trả lời câu hỏi HAI LỐI sau khi xem thông tin xe và chi phí.

    Câu hỏi: *"Anh/chị muốn đặt lịch lái thử, hay còn điều gì cần em làm rõ?"*
    """

    #: Nhận lời lái thử → sang bước chọn khung giờ.
    TEST_DRIVE = "TEST_DRIVE"
    #: Còn vướng một điều gì đó → tư vấn viên.
    HAS_CONCERN = "HAS_CONCERN"
    #: Không muốn cả hai — dừng ở đây, không nài.
    DECLINED = "DECLINED"
    #: Hết vướng nhưng chưa nói gì về lái thử → mời lại một lần cho RÕ.
    #:
    #: Khác `UNCLEAR`: ở đây khách đã trả lời xong vế "còn điều gì cần làm rõ"
    #: (không còn gì), chỉ là chưa trả lời vế lái thử. Gộp nó vào `TEST_DRIVE` là
    #: đặt lịch cho người chưa nhận lời; gộp vào `UNCLEAR` là hỏi lại đúng câu họ
    #: vừa trả lời một nửa.
    NO_CONCERN = "NO_CONCERN"
    #: Chưa rõ → hỏi lại, không đoán.
    UNCLEAR = "UNCLEAR"


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


#: "Không còn gì" — đứng MỘT MÌNH, đuôi chỉ nhận tập từ đệm ĐÓNG.
#:
#: Cùng khuôn `slot_salvage._STANDALONE_REFUSAL_PATTERN`, và cùng lý do: đuôi tự
#: do thì mọi câu bắt đầu bằng "không" thành "đã yên tâm" — kể cả "không, tôi
#: muốn hỏi thêm về pin", tức đúng câu NGƯỢC nghĩa.
_NO_CONCERN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:da|u|a|vang|oke|ok|okie)?\s*"
    r"(?:"
    r"(?:khong|ko|k0|chua)\s*(?:con|co)?\s*(?:gi|van de|thac mac|bang khoan|ban khoan|lan tan|thac mac gi)?"
    r"|(?:on|tot|duoc|hai long|ung|thoa man|ro roi|ro rang|ok|okie|oke)"
    r"|het roi|the la du|du roi|xong roi"
    r")\b"
    r"(?:\s*(?:roi|a|ah|nhe|nha|em|anh|minh|lam|ca|het|luon|day|the|thoi|va|dau|gi|ca gi|gi ca|gi dau))*\s*[.!]?$"
)

#: "Còn, tôi muốn hỏi…" — câu NÊU một thắc mắc. Xét TRƯỚC mẫu trên vì một câu có
#: thể vừa mở bằng "không" vừa nêu vấn đề ("không, tôi lo về pin").
_HAS_CONCERN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\?"
    r"|\bcon\s+(?:mot|vai|chut|thac mac|ban khoan|bang khoan|lan tan|van de|dieu)\b"
    # Lookbehind chặn PHỦ ĐỊNH: "không thắc mắc gì" là đã yên tâm, ngược hẳn
    # "còn thắc mắc". Thiếu nó thì câu hết vướng bị đẩy sang tư vấn viên.
    r"|(?<!khong )(?<!chua )\b(?:thac mac|ban khoan|bang khoan|lan tan|lo lang|lo ngai|lo|chua ro|chua hieu|khong hieu)\b"
    r"|\bmuon\s+(?:hoi|biet|tim hieu|xem)\b"
    # Câu NGHI VẤN không mang dấu hỏi. Rất nhiều khách gõ liền không chấm câu:
    # "xe này pin đi được bao xa", "còn xe nào khác không". Chỉ dựa vào `\?` thì
    # đúng những câu hỏi thật của khách rơi vào vùng không đọc được, và agent
    # hỏi lại đúng người vừa đặt câu hỏi cho mình.
    r"|\bbao (?:xa|nhieu|lau|gio|nhieu tien)\b"
    r"|\bthe nao\b|\bra sao\b|\bnhu the nao\b"
    r"|\bnao khac\b|\bkhac khong\b|\bnao nua\b"
    r"|\bduoc khong\b|\bcó the\b"
    r"|\bcho\s+(?:hoi|em hoi|toi hoi)\b"
    r"|\bnhung\b|\btuy nhien\b|\bso\b|\bhoi lo\b"
    # `\bdat\b` là "đắt" — nhưng bỏ dấu xong "ĐẶT lịch" cũng thành "dat lich".
    #
    # Bản trước dùng lookahead ĐEN (chặn "lich", "lai thu"…) và vẫn thủng: "uh đặt
    # đi" thành "uh dat di", không nằm trong danh sách chặn, nên một lời ĐỒNG Ý
    # bị đọc thành lời than giá và đẩy khách sang tư vấn viên — sai hẳn hướng.
    #
    # Danh sách đen không bao giờ đủ: mọi từ đứng sau "đặt" đều phải liệt kê.
    # Nên đảo thành lookahead TRẮNG — "đắt" chỉ được nhận khi theo sau là từ mức
    # độ hoặc là hết câu, đúng cách người ta than giá ("đắt quá", "đắt lắm",
    # "đắt hơn dự tính", "xe này đắt"). Mọi cụm động từ "đặt …" rơi ra ngoài.
    r"|\bgia\b.*\bcao\b"
    r"|\bdat\b(?=\s*(?:qua|lam|the|nhi|hon|so voi|a|ah|day|roi)\b|\s*[.!,]|\s*$)"
    r"|\bcon\b.*\?(?!$)"
)


def classify_post_pitch_decision(user_message: str) -> PostPitchDecision:
    """Đọc câu trả lời cho câu hỏi hai lối sau đề xuất.

    **Vì sao gộp hai câu hỏi thành một** (Sếp 2026-08-26). Bản trước hỏi "còn
    băn khoăn gì không" rồi lượt sau mới mời lái thử — hai lượt cho một quyết
    định, và câu đầu là câu MỞ nên mọi lời đáp ngắn đều rơi vào vùng `UNCLEAR`.
    Câu gộp NÊU RÕ cả hai lối ngay trong câu hỏi, nên bộ đọc chỉ phải phân biệt
    hai nhánh khách vừa được nghe tên.

    **Thứ tự xét có ý nghĩa.** Nỗi lo thắng lời nhận lời: "được, nhưng em lo về
    pin" là câu CÒN vướng, và đẩy người vừa nói ra một nỗi lo sang bước chọn giờ
    là bỏ qua đúng điều họ vừa nói. Hai mẫu hiếm khi cùng khớp — `_ACCEPT_PATTERN`
    của `test_drive_booking` đòi khớp TOÀN chuỗi từ một tập từ đóng — nhưng khi
    chúng cùng khớp thì phải ngã về phía lắng nghe.
    """

    from src.agents.domain.test_drive_booking import wants_test_drive

    concern = classify_concern_reply(user_message)
    if concern is ConcernReply.HAS_CONCERN:
        return PostPitchDecision.HAS_CONCERN

    accepted = wants_test_drive(user_message)
    if accepted is True:
        return PostPitchDecision.TEST_DRIVE
    if accepted is False:
        return PostPitchDecision.DECLINED

    if concern is ConcernReply.NO_CONCERN:
        return PostPitchDecision.NO_CONCERN
    return PostPitchDecision.UNCLEAR


def classify_concern_reply(user_message: str) -> ConcernReply:
    """Đọc câu trả lời cho "còn băn khoăn gì không".

    Thứ tự xét CÓ Ý NGHĨA: một câu vừa mở bằng "không" vừa nêu vấn đề ("không,
    tôi lo về pin") là câu CÒN vướng. Xét mẫu "hết vướng" trước thì nó ăn mất vế
    sau và luồng đẩy khách sang lái thử trong khi họ vừa nói ra một nỗi lo.
    """

    folded = _fold(user_message)
    if not folded:
        return ConcernReply.UNCLEAR
    if _HAS_CONCERN_PATTERN.search(folded):
        return ConcernReply.HAS_CONCERN
    if _NO_CONCERN_PATTERN.match(folded):
        return ConcernReply.NO_CONCERN
    return ConcernReply.UNCLEAR
