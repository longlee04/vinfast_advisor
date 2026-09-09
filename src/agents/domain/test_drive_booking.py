"""Khách chốt một khung giờ lái thử bằng NÚT, không bằng chữ tự do.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

Sếp 2026-08-26: "nối luôn đăng ký lái thử". Bước chốt lịch là chỗ **không được
đoán**: sai một giờ là khách tới showroom vào lúc không ai đợi, và sai showroom
thì họ đi nhầm thành phố. Nên khung giờ đi qua một mã có cấu trúc do chính hệ
sinh ra, không qua phép đọc "chiều mai lúc 3h".

Mã đi trong `QuickReply.value`, tức vẫn là một TIN NHẮN bình thường — cùng quy
ước với mọi nút khác, nên bấm nút và gõ tay chạy qua đúng một nhánh xử lý.
Frontend đã giấu nó khỏi khung chat bằng cờ `silent`, nên khách không thấy chuỗi
kỹ thuật này.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from binascii import Error as BinasciiError
from datetime import datetime, timedelta
from typing import Final, NamedTuple

#: Tiền tố đủ lạ để không câu tiếng Việt nào trùng, và đủ ngắn để đọc log được.
_PREFIX: Final[str] = "__lichlaithu__"

_SEPARATOR: Final[str] = "|"

#: Phiên bản payload. Đổi cách ghi thì tăng số này — mã cũ tự hết hiệu lực thay
#: vì bị đọc sai thành một khung giờ khác.
_VERSION: Final[str] = "v1"

#: Dấu ngăn giữa các trường trong payload. Ký tự điều khiển US (0x1f) chứ không
#: phải `|`: tên showroom chứa được mọi ký tự in được, và một tên có `|` mà chen
#: được thêm trường vào payload thì chữ ký vẫn đúng.
_FIELD: Final[str] = "\x1f"

#: Hạn của một giấy phép khung giờ.
#:
#: Tính từ lúc CẤP, không phải từ giờ hẹn: một mã cấp hôm nay cho khung giờ tuần
#: sau vẫn phải hết hạn trước khi tuần sau tới. Hai giờ đủ dài cho một cuộc trò
#: chuyện và đủ ngắn để một mã lọt ra ngoài không sống lâu.
SLOT_TOKEN_TTL: Final[timedelta] = timedelta(hours=2)

#: Khoảng lệch đồng hồ chấp nhận được giữa máy CẤP và máy ĐỌC.
#:
#: Hai máy lệch nhau vài giây là chuyện thường, không phải tấn công — chặn cứng
#: `issued_at <= now` sẽ làm rơi những mã hợp lệ do máy cấp chạy nhanh hơn.
CLOCK_SKEW: Final[timedelta] = timedelta(minutes=2)

#: Chữ ký cắt còn 16 byte. Đủ để đoán mò là vô vọng, và giữ mã ngắn.
_SIGNATURE_BYTES: Final[int] = 16


class BookingChoice(NamedTuple):
    """Một khung giờ khách đã chốt, đã qua kiểm chữ ký và ràng buộc."""

    showroom: str
    scheduled_at: datetime


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload: bytes, secret: bytes) -> str:
    return _b64(hmac.new(secret, payload, hashlib.sha256).digest()[:_SIGNATURE_BYTES])


def encode_slot_choice(
    *,
    showroom: str,
    scheduled_at: datetime,
    session_id: str,
    customer_id: str,
    issued_at: datetime,
    secret: bytes,
) -> str:
    """Cấp một GIẤY PHÉP cho đúng một khung giờ.

    Bản trước là chữ thường — `__lichlaithu__|<giờ>|<showroom>` — nên ai cũng tự
    gõ được: showroom bịa, giờ đã qua, giờ ngoài cửa sổ bảy ngày, hoặc showroom
    chưa từng được mời cho phiên đó. `_book_test_drive` tách chuỗi rồi ghi thẳng
    vào `test_drive_bookings`.

    Giờ mã buộc vào PHIÊN, KHÁCH, showroom, mốc giờ và một hạn dùng, rồi ký
    HMAC. Sửa một byte là chữ ký hỏng; mượn mã của phiên khác là sai ràng buộc.

    KHÔNG buộc `vehicle_id`: endpoint availability không biết xe nào, và xe đọc
    từ chặng sau đề xuất ở phía server nên client không chọn được nó.

    Thời gian đi dạng ISO có múi giờ: mất múi giờ là lệch bảy tiếng trên một hệ
    lưu `TIMESTAMPTZ`, và lệch đó chỉ lộ ra khi khách tới showroom.
    """

    fields = (_VERSION, session_id, customer_id, scheduled_at.isoformat(), issued_at.isoformat(), showroom)
    payload = _FIELD.join(fields).encode("utf-8")
    return f"{_PREFIX}{_SEPARATOR}{_b64(payload)}{_SEPARATOR}{_sign(payload, secret)}"


def decode_slot_choice(
    user_message: str,
    *,
    session_id: str,
    customer_id: str,
    now: datetime,
    secret: bytes,
) -> BookingChoice | None:
    """Đọc giấy phép; mọi thứ khác trả `None`.

    Không cố sửa mã hỏng: một mã sai nghĩa là client cũ, mã hết hạn, hoặc ai đó
    đang thử tay — và đặt lịch từ dữ liệu đoán được là kiểu sai tệ nhất ở bước
    này. Mã của bản cũ (chữ thường) rơi vào đây và bị từ chối, đúng như ý.
    """

    parts = (user_message or "").strip().split(_SEPARATOR)
    if len(parts) != 3 or parts[0] != _PREFIX:
        return None
    try:
        payload = _unb64(parts[1])
    except (ValueError, BinasciiError):
        return None
    # `compare_digest` chứ không phải `==`: so chuỗi thường rò rỉ thời gian, và
    # chỗ này là thứ duy nhất đứng giữa một khung giờ thật và một khung bịa.
    #
    # So bằng BYTES, không bằng str: `compare_digest` NÉM `TypeError` khi một vế
    # có ký tự ngoài ASCII. Mã của bản cũ — `__lichlaithu__|<giờ>|<showroom>` —
    # cũng có ba mảnh, và mảnh thứ ba là tên showroom tiếng Việt ("VinFast E-Car
    # Hưng Yên"), nên một khách bấm lại nút cũ làm hàm này NỔ thay vì trả `None`.
    # Lượt prod LP21 chết đúng ở đây: `act._book` không bọc `try`, `run_turn` bắt
    # được ngoại lệ và trả câu an toàn của chặng, khách nhận "anh/chị đang tìm ô
    # tô điện hay xe máy điện ạ?" cho một cái nút đặt lịch.
    if not hmac.compare_digest(_sign(payload, secret).encode("ascii"), parts[2].encode("utf-8")):
        return None
    try:
        version, token_session, token_customer, when, issued, showroom = payload.decode("utf-8").split(_FIELD)
    except (UnicodeDecodeError, ValueError):
        return None
    if version != _VERSION or token_session != session_id or token_customer != customer_id:
        return None
    try:
        scheduled_at = datetime.fromisoformat(when)
        issued_at = datetime.fromisoformat(issued)
    except ValueError:
        return None
    # Chặn CẢ HAI đầu. Bản trước chỉ hỏi "mã có quá cũ không", mà hiệu số thành
    # ÂM khi `issued_at` nằm ở tương lai — nên một mã ghi ngày mai vẫn qua cửa,
    # và nó sống dài hơn TTL thật đúng bằng khoảng lệch đó.
    age = now - issued_at
    if age > SLOT_TOKEN_TTL or age < -CLOCK_SKEW:
        return None
    showroom = showroom.strip()
    if not showroom:
        return None
    return BookingChoice(showroom=showroom, scheduled_at=scheduled_at)


#: Khách ĐỒNG Ý lái thử. Cùng khuôn `concern_reply`: lõi là từ trọn vẹn, đuôi chỉ
#: nhận tập từ đệm đóng.
_ACCEPT_PATTERN: Final[re.Pattern[str]] = re.compile(
    # Tiền tố ậm ừ đồng ý. "uh"/"um" phải có mặt: đo trên câu thật, "uh đặt đi"
    # là một lời nhận lời hoàn chỉnh mà bản trước không đọc được vì tiền tố chỉ
    # nhận "u" trơ.
    r"^(?:da|u|uh|um|a|ah|vang|oke|ok|okie)?\s*"
    r"(?:co|dong y|duoc|muon|nhat tri|chac chan|dat|dang ky|lai thu|thu|ok|okie|oke|vang|u|um|"
    r"cho toi|cho anh|cho em|di|nhe)"
    # Đuôi phải nhận cả "lich" và "giup ...": "đặt lịch giúp anh" là câu nhận lời
    # thẳng thắn nhất mà khách hay gõ, và bản trước trả `None` cho nó.
    r"\b(?:\s*(?:di|nhe|nha|a|ah|luon|chu|thoi|em|anh|minh|dat lich|lai thu|thu|xem|"
    r"dang ky|mot buoi|buoi|lich|giup|ho|cho|toi|minh|voi))*\s*[.!]?$"
)

#: Khách TỪ CHỐI lái thử. Xét TRƯỚC mẫu đồng ý — "không cần đâu" mở đầu bằng
#: "không" nhưng chứa "cần", và "cần" nằm trong tập đuôi của mẫu đồng ý.
_DECLINE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:da|u|a|vang)?\s*"
    r"(?:khong|ko|thoi|chua|de sau|de khi khac|chua can|khong can)"
    # "khong" nằm trong tập ĐUÔI, không chỉ trong lõi: "thôi không" mở bằng
    # "thôi" rồi đóng bằng "không", và thiếu nó thì một lời từ chối rõ ràng rơi
    # xuống `UNCLEAR` — tức khách bị hỏi lại đúng câu họ vừa từ chối.
    r"\b(?:\s*(?:can|co|a|ah|dau|nhe|nha|em|anh|minh|gi|luon|thoi|bay gio|voi|"
    r"khong|ko|de sau|de khi khac|dat lich|lai thu))*\s*[.!]?$"
)


def _fold(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d")).strip()


def wants_test_drive(user_message: str) -> bool | None:
    """`True` đồng ý, `False` từ chối, `None` chưa rõ.

    Ba kết quả chứ không hai — cùng lý do với `concern_reply`: "để xem" không nói
    lên khách muốn hay không, và đoán hộ ở đây là đặt lịch cho người chưa nhận
    lời, hoặc bỏ qua người vừa đồng ý.
    """

    folded = _fold(user_message)
    if not folded:
        return None
    if _DECLINE_PATTERN.match(folded):
        return False
    if _ACCEPT_PATTERN.match(folded):
        return True
    if re.search(r"\b(?:lai thu|dat lich lai thu|cho (?:anh|em|toi) lai thu)\b", folded):
        return True
    return None
