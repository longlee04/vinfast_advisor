"""Lớp hội thoại tự nhiên: đọc TẤT ĐỊNH những câu xã giao/cảm xúc ngắn của khách.

"ok xe đẹp đấy", "đắt quá", "để anh suy nghĩ", "cảm ơn em" không mang yêu cầu
nghiệp vụ nào, nhưng chúng là CÂU TRẢ LỜI cho điều bot vừa nói. Trước lớp này,
mọi câu như vậy rơi chung vào `DialogueAct.SOCIAL` và — khi chặng còn là
`GREETING` (một lượt tra cứu không đổi chặng) — khách nhận lại nguyên lời chào
giới thiệu "Em là trợ lý tư vấn…" giữa cuộc hội thoại (log thật 2026-09-23).

Module THUẦN: không I/O, không LLM, không import `core/`. Nó được `core.understand`
gọi sau cửa LLM, và được `services.conversational` dùng để chọn cách đáp — tách
như vậy để khi chuyển sang harness agentic, cùng module này dùng lại được như
một tool/node mà không kéo theo lõi v2. [GIẢ ĐỊNH]
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from src.agents.domain.text_normalization import normalize


class ConversationalIntent(StrEnum):
    FEEDBACK_POSITIVE = "FEEDBACK_POSITIVE"
    FEEDBACK_NEGATIVE = "FEEDBACK_NEGATIVE"
    HESITATION = "HESITATION"
    ACK = "ACK"
    THANKS = "THANKS"
    GOODBYE = "GOODBYE"
    CHITCHAT = "CHITCHAT"
    GREETING = "GREETING"


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Ngữ cảnh tối thiểu để hiểu một câu ngắn và để viết câu đáp.

    `last_bot_question` là câu hỏi CUỐI trong tin nhắn gần nhất của bot (rỗng nếu
    tin đó không hỏi gì). `has_bot_turn` phân biệt lời chào ĐẦU phiên với một câu
    "chào em" giữa chừng.
    """

    active_vehicle: str | None = None
    last_bot_question: str = ""
    has_bot_turn: bool = False
    filled_slots: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    recent_turns: tuple[tuple[str, str], ...] = ()


#: Câu dài hơn mức này gần như luôn mang nội dung nghiệp vụ — để cửa LLM lo.
#: [GIẢ ĐỊNH] 8 từ: rộng hơn ngưỡng "≤ 6 từ bắt buộc có ngữ cảnh" của spec một
#: chút để bắt "ok xe đẹp đấy em ạ, nhìn sang ghê".
MAX_CONVERSATIONAL_WORDS: Final = 8

# Mọi cụm dưới đây ở dạng ĐÃ `normalize` (thường, không dấu, không dấu câu).
_IDENTITY: Final = (
    "nguoi hay may",
    "nguoi that",
    "la nguoi a",
    "la may a",
    "la bot",
    "robot",
    "em la ai",
    "ban la ai",
    "ai vay",
    "chatgpt",
)
_SMALL_TALK: Final = ("nong qua", "mua qua", "troi dep", "an com chua", "em ten gi", "may tuoi", "met qua")
#: Dấu hiệu câu hỏi NGHIỆP VỤ. Có một cái là lớp này nhường cho luồng chính —
#: "xe đẹp nhưng giá bao nhiêu" là câu hỏi giá, lời khen chỉ là phần đệm.
_BUSINESS: Final = (
    "gia xe",
    "gia ban",
    "gia sao",
    "gia the nao",
    "gia bao",
    "gia lan banh",
    "bao nhieu",
    "bn",
    "nhieu tien",
    "tien dien",
    "tra gop",
    "lai thu",
    "dat lich",
    "so sanh",
    "thong so",
    "sac dien",
    "sac pin",
    "sac day",
    "sac nhanh",
    "tram sac",
    "pin bao",
    "bao lau",
    "bao xa",
    "may cho",
    "khuyen mai",
    "uu dai",
    "showroom",
    "dai ly",
    "lan banh",
    "chi phi",
    "the nao",
    "ra sao",
    "co khong",
    "khong a",
)
_GOODBYE: Final = ("bye", "tam biet", "hen gap lai", "chao em nhe", "chao nhe", "di day")
_THANKS: Final = ("cam on", "cam ong", "thank", "thanks", "tks", "thks", "camon")
_NEGATIVE: Final = (
    "dat qua",
    "dat the",
    "dat vay",
    "dat ghe",
    "hoi dat",
    "xau",
    "pin yeu",
    "yeu qua",
    "chan qua",
    "chan the",
    "te qua",
    "kem qua",
    "khong thich",
    "khong dep",
    "khong ung",
    "chua ung",
    "khong hop",
    "nho qua",
)
_HESITATION: Final = (
    "suy nghi",
    "chua chac",
    "de xem",
    "de xem da",
    "phan van",
    "can nhac",
    "tinh sau",
    "chua biet",
    "de toi xem",
    "de anh xem",
    "de chi xem",
    "hmm",
    "hm",
)
_POSITIVE: Final = (
    "dep",
    "ngon",
    "duoc day",
    "thich",
    "xin qua",
    "xin day",
    "xin that",
    "xin ghe",
    "tuyet",
    "xuat sac",
    "hay day",
    "chat luong",
    "ung y",
    "ung qua",
    "ung roi",
    "thay ung",
    "ok xe",
    "oke xe",
    "on day",
    "ngau",
    "sang trong",
    "xin xo",
    "qua da",
    "dinh qua",
    "dinh that",
    "dinh cao",
)
_GREETING: Final = ("chao", "hello", "hi", "alo", "xin chao", "hey")
#: Câu ĐỒNG Ý cụt. So KHỚP NGUYÊN câu (không phải chứa), vì "ok" nằm trong vô
#: số câu có nội dung.
_ACK_EXACT: Final = frozenset(
    {
        "ok",
        "oke",
        "okay",
        "okie",
        "ok em",
        "ok a",
        "u",
        "uh",
        "uk",
        "um",
        "vang",
        "da",
        "da vang",
        "vay a",
        "the a",
        "duoc",
        "dc",
        "duoc em",
        "co",
        "co em",
        "yes",
        "u em",
        "ok luon",
        "chot",
    }
)
#: Phủ định đứng ngay trước một lời khen đảo nghĩa nó ("không đẹp", "chưa thích").
_NEGATORS: Final = ("khong", "chua", "chang", "k", "ko", "hong")

_WORD_SPLIT = re.compile(r"\s+")


def _contains(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _any(text: str, phrases: Sequence[str]) -> bool:
    return any(_contains(text, phrase) for phrase in phrases)


def _negated_positive(text: str) -> bool:
    tokens = text.split()
    for index, token in enumerate(tokens[:-1]):
        if token in _NEGATORS and _any(" ".join(tokens[index + 1 : index + 3]), _POSITIVE):
            return True
    return False


#: "giá" đứng một mình cuối câu ("xe đẹp nhưng giá?") — KHÔNG khớp "gia đình".
_BARE_PRICE = re.compile(r"(?<![a-z0-9])gia(?![a-z0-9])(?! dinh)")


def has_business_question(message: str) -> bool:
    """Câu có hỏi/đòi một việc nghiệp vụ — lúc đó luồng chính thắng."""

    text = normalize(message)
    if _any(text, _BUSINESS) or _BARE_PRICE.search(text):
        return True
    return "?" in message and not _any(text, _IDENTITY)


def classify_conversational(message: str, context: ConversationContext) -> ConversationalIntent | None:
    """Nhãn hội thoại của câu, hoặc `None` khi câu thuộc luồng nghiệp vụ.

    Thứ tự ưu tiên có chủ ý: hỏi danh tính (có dấu "?" vẫn là tán gẫu) → câu
    nghiệp vụ (nhường) → tạm biệt → cảm ơn → chê → phân vân → khen → chào → đồng ý.
    Chê đứng trước khen để "không đẹp lắm" không bị đọc thành lời khen; khen
    đứng trước chào để "chào em, xe đẹp đấy" giữa chừng là FEEDBACK chứ không
    phải một lời chào mới (spec: GREETING giữa hội thoại hạ ưu tiên).
    """

    text = normalize(message)
    if not text:
        return None
    if _any(text, _IDENTITY):
        return ConversationalIntent.CHITCHAT
    if has_business_question(message):
        return None
    if len(_WORD_SPLIT.split(text)) > MAX_CONVERSATIONAL_WORDS:
        return None
    if _any(text, _GOODBYE):
        return ConversationalIntent.GOODBYE
    if _any(text, _THANKS):
        return ConversationalIntent.THANKS
    if _any(text, _NEGATIVE) or _negated_positive(text):
        return ConversationalIntent.FEEDBACK_NEGATIVE
    if _any(text, _HESITATION):
        return ConversationalIntent.HESITATION
    if _any(text, _POSITIVE):
        return ConversationalIntent.FEEDBACK_POSITIVE
    if _any(text, _SMALL_TALK):
        return ConversationalIntent.CHITCHAT
    if _any(text, _GREETING):
        return ConversationalIntent.GREETING
    if text in _ACK_EXACT:
        return ConversationalIntent.ACK
    return None


#: Câu hỏi có/không kiểu "…nhé?", "…không ạ?". Câu có "hay" là câu hỏi LỰA
#: CHỌN ("ưng VF 9 không, hay để em so với mẫu khác?") — "ok" không trả lời được nó.
_YES_NO_TAIL: Final = re.compile(r"(nhe|nha|khong|khong a|chu a|chu|duoc khong|nhe a|nha a|luon nhe)\s*$")


def is_yes_no_question(question: str) -> bool:
    text = normalize(question)
    if not text or not question.rstrip().endswith("?"):
        return False
    if _contains(text, "hay"):
        return False
    return _YES_NO_TAIL.search(text) is not None


def last_question(text: str) -> str:
    """Câu hỏi CUỐI trong một tin nhắn của bot (tới dấu "?" cuối), hoặc rỗng."""

    if "?" not in (text or ""):
        return ""
    head = text[: text.rindex("?") + 1]
    start = max(head.rfind(mark, 0, len(head) - 1) for mark in (".", "!", "\n", "?"))
    return head[start + 1 :].strip()


#: Việc mà một câu hỏi có/không của bot đang mời — "ok" đáp câu đó thì đi làm
#: đúng việc đó. Khoá là cụm ĐÃ normalize.
ACK_JOBS: Final[tuple[tuple[str, str], ...]] = (
    ("lai thu", "TEST_DRIVE"),
    ("dat lich", "TEST_DRIVE"),
    ("lan banh", "ON_ROAD_PRICE"),
    ("chi phi", "COST"),
    ("uu dai", "OFFER"),
    ("khuyen mai", "OFFER"),
)


def ack_job(question: str) -> str | None:
    """Tên intent (chuỗi) của việc mà câu hỏi có/không đang mời, hoặc `None`."""

    if not is_yes_no_question(question):
        return None
    text = normalize(question)
    for phrase, job in ACK_JOBS:
        if _contains(text, phrase):
            return job
    return None


__all__ = [
    "ACK_JOBS",
    "MAX_CONVERSATIONAL_WORDS",
    "ConversationContext",
    "ConversationalIntent",
    "ack_job",
    "classify_conversational",
    "has_business_question",
    "is_yes_no_question",
    "last_question",
]
