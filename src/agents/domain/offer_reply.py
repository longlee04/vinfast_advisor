"""Báo cho khách biết tư vấn viên vừa cấp ưu đãi gì, rồi MỜI tính lại chi phí.

THUẦN Python — không import FastAPI/SQLAlchemy/LangGraph/LLM SDK.

Sếp 2026-08-27: *"khi cấp thì không phải trừ thẳng rồi tính TCO mà sau khi duyệt
xong phải có thông báo cho khách… nếu về giá thì phải có hiện từ đi còn bao
nhiêu… phải thông báo người ta nhận được quà và sau khi trả như vậy xong thì hỏi
thêm anh/chị có để em tính giá TCO cho mình không"*.

Ba việc, đúng thứ tự đó, và thứ tự là phần quan trọng nhất:

1. **NÓI CÓ ƯU ĐÃI** trước khi nói bất kỳ con số nào. Khách đang cân nhắc vì
   thấy đắt; câu đầu tiên họ đọc phải là câu gỡ đúng chỗ vướng ấy.
2. **HIỆN GIẢM BAO NHIÊU, CÒN BAO NHIÊU.** Chỉ nói "được giảm 5%" bắt khách tự
   nhân — mà con số họ tự nhân ra là con số họ đem đi so với đại lý.
3. **HỎI** trước khi tính lại chi phí, không tự trừ rồi thay số. Một cái tổng
   lặng lẽ đổi giữa cuộc nói chuyện là chỗ mất niềm tin nhanh nhất: khách không
   biết nó đổi vì ưu đãi hay vì ta vừa sửa gì khác.

Số ở đây render TẤT ĐỊNH từ chính bản ghi ưu đãi và giá catalog, không qua LLM —
cùng đường với `chain._cost_summary` và `_nearest_showroom`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.reply_format import bold

#: Câu MỞ, dùng khi khách đang vướng và ta vừa xin được ưu đãi cho họ.
#:
#: Nhắc lại đúng việc họ đang cân nhắc rồi mới đưa ưu đãi — không nhảy thẳng vào
#: con số. Đây là câu Sếp đọc mẫu ("Nếu anh còn cân nhắc về vấn đề trên, em xin
#: phép…"), giữ nguyên tinh thần ấy.
_LEAD: Final[str] = "Dạ, về điều anh/chị còn cân nhắc, em vừa xin được ưu đãi riêng cho anh/chị ạ."

#: Câu CHỐT — mời tính lại, KHÔNG tự tính.
_ASK_RECALCULATE: Final[str] = "Anh/chị có muốn em tính lại chi phí lăn bánh theo ưu đãi này để tiện ước chừng không ạ?"

#: Câu khi ưu đãi không mang con số nào đọc được.
#:
#: Xảy ra thật: đo trên prod 2026-08-27, cả hai bản ghi `session_offers` đều có
#: `percent`, `amount_vnd`, `new_value` RỖNG. Nói "được giảm" trong tình huống đó
#: là hứa một con số không tồn tại, nên chỉ nêu tên chương trình và để tư vấn
#: viên nói phần chi tiết.
_VALUELESS: Final[str] = "Chi tiết mức ưu đãi em nhờ anh tư vấn viên trao đổi thêm với anh/chị ạ."


#: Tư vấn viên xem xong mà CHƯA cấp được ưu đãi.
#:
#: Sếp 2026-08-27: *"nếu advisor từ chối thì cũng phải có thông báo tư vấn viên
#: đang tìm kiếm ưu đãi phù hợp nhất với khách hàng và đề xuất khách tính TCO"*.
#:
#: Im lặng ở đây là bỏ rơi khách đúng lúc họ đang chờ: họ vừa nói ra điều còn
#: vướng, được báo là đã chuyển người, rồi không nghe gì nữa. Câu này nói thật
#: rằng việc vẫn đang chạy, và mở tiếp một lối đi được ngay thay vì bắt họ chờ.
#:
#: KHÔNG hứa sẽ có ưu đãi — chỉ nói đang tìm. Hứa một thứ tư vấn viên vừa từ
#: chối là đặt vào miệng người khác một lời cam kết.
_ADVISOR_STILL_LOOKING: Final[str] = (
    "Dạ, anh tư vấn viên bên em đang tìm chương trình ưu đãi phù hợp nhất cho anh/chị và sẽ phản hồi sớm ạ."
)


#: Mời tính chi phí trong lúc CHỜ ưu đãi — khác câu mời sau khi ĐÃ có ưu đãi.
#:
#: `_ASK_RECALCULATE` nói "theo ưu đãi này", mà ở nhánh này chưa có ưu đãi nào.
#: Dùng lại nó là nhắc tới một thứ vừa bị từ chối.
_ASK_COST_WHILE_WAITING: Final[str] = (
    "Trong lúc chờ, anh/chị có muốn em tính chi phí lăn bánh để tiện ước chừng không ạ?"
)


def advisor_still_looking_notice() -> str:
    """Báo khách việc vẫn đang chạy, rồi mời tính chi phí trong lúc chờ."""

    return f"{_ADVISOR_STILL_LOOKING}\n\n{_ASK_COST_WHILE_WAITING}"


def _as_decimal(value: object) -> Decimal | None:
    """Số đọc được, hoặc `None`. Chuỗi rỗng và dữ liệu hỏng đều về `None`."""

    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed > 0 else None


def _format_vnd(amount: Decimal) -> str:
    """`Decimal` → "899.000.000 đồng". Cắt phần thập phân toàn số không."""

    whole = int(amount)
    return f"{whole:,}".replace(",", ".") + " đồng"


def discount_amount(offer: Mapping[str, object], *, base_price_vnd: Decimal | None) -> Decimal | None:
    """Số tiền ưu đãi trừ đi, hoặc `None` khi ưu đãi không phải kiểu tiền.

    Ưu tiên `amount_vnd` (số tuyệt đối) trước `percent`: một bản ghi có cả hai là
    bản ghi mâu thuẫn, và con số tuyệt đối là thứ tư vấn viên gõ tay nên nó gần
    ý định của họ hơn.

    `percent` cần giá gốc mới quy ra tiền được; thiếu giá thì trả `None` chứ
    không đoán — nói "giảm 5%" mà không biết 5% của bao nhiêu là chưa nói gì.
    """

    absolute = _as_decimal(offer.get("amount_vnd"))
    if absolute is not None:
        return absolute
    percent = _as_decimal(offer.get("percent"))
    if percent is None or base_price_vnd is None or base_price_vnd <= 0:
        return None
    return (base_price_vnd * percent / Decimal("100")).quantize(Decimal("1"))


def total_discount(
    offers: Sequence[Mapping[str, object]],
    *,
    base_price_vnd: Decimal | None,
) -> Decimal:
    """Tổng tiền ưu đãi trừ vào GIÁ XE, cộng dồn mọi ưu đãi đang hiệu lực.

    Ba luật, Sếp chốt 2026-08-27:

    1. **Trừ vào giá xe**, không trừ vào tổng chi phí. Ưu đãi hiện tại của
       VinFast chỉ giảm giá bán, nên trừ đúng chỗ đó. Kéo theo: lệ phí trước bạ
       tính trên giá xe cũng giảm theo — đó là đúng, không phải hiệu ứng phụ.
    2. **Cộng dồn** nhiều ưu đãi.
    3. **Hết hạn thì không query ra** — `session_offers.active_for_session` chỉ
       trả bản ghi `ACTIVE`, nên hàm này không cần biết gì về thời hạn.

    Ưu đãi phần trăm quy ra tiền trên GIÁ GỐC, không trên giá đã trừ dở: cộng
    dồn theo kiểu lãi kép làm con số phụ thuộc thứ tự tư vấn viên bấm, và hai
    tư vấn viên cấp cùng bộ ưu đãi sẽ ra hai giá khác nhau.

    Trần là chính giá xe: tổng ưu đãi vượt giá thì giá về 0, không âm.
    """

    if base_price_vnd is None or base_price_vnd <= 0:
        return sum(
            (amount for offer in offers if (amount := discount_amount(offer, base_price_vnd=None)) is not None),
            start=Decimal("0"),
        )
    total = sum(
        (amount for offer in offers if (amount := discount_amount(offer, base_price_vnd=base_price_vnd)) is not None),
        start=Decimal("0"),
    )
    return total if total < base_price_vnd else base_price_vnd


def offer_announcement(
    offer: Mapping[str, object],
    *,
    vehicle_name: str | None = None,
    base_price_vnd: Decimal | None = None,
) -> str:
    """Thông báo ưu đãi gửi khách, kết bằng câu mời tính lại chi phí.

    KHÔNG tự trừ vào bảng chi phí — đó là việc của lượt sau, và chỉ khi khách
    đồng ý (Sếp 2026-08-27).
    """

    lines = [_LEAD]
    detail = _offer_detail(offer, vehicle_name=vehicle_name, base_price_vnd=base_price_vnd)
    lines.extend(detail)
    lines.append(_ASK_RECALCULATE)
    return "\n\n".join(lines)


def _offer_detail(
    offer: Mapping[str, object],
    *,
    vehicle_name: str | None,
    base_price_vnd: Decimal | None,
) -> list[str]:
    """Phần thân: giảm bao nhiêu, còn bao nhiêu — hoặc quà tặng gì."""

    gift = str(offer.get("gift_code") or "").strip()
    months = _as_decimal(offer.get("months"))
    amount = discount_amount(offer, base_price_vnd=base_price_vnd)
    name = str(offer.get("display_name") or offer.get("promotion_code") or "").strip()

    if amount is not None:
        # HIỆN CẢ HAI con số: giảm bao nhiêu, và còn bao nhiêu. Chỉ nói mức giảm
        # là bắt khách tự trừ, mà kết quả họ tự trừ ra là con số họ đem đi so giá.
        head = f"{bold('Ưu đãi')}: giảm {_format_vnd(amount)}"
        if base_price_vnd is not None and base_price_vnd > 0:
            remaining = base_price_vnd - amount
            floor = remaining if remaining > 0 else Decimal("0")
            subject = vehicle_name or "xe"
            head += f" — giá {subject} còn {_format_vnd(floor)}"
        return [head + (f" ({name})" if name else "") + "."]

    if gift:
        return [f"{bold('Quà tặng')}: {gift}" + (f" ({name})" if name else "") + "."]

    if months is not None:
        return [f"{bold('Ưu đãi')}: {int(months)} tháng" + (f" ({name})" if name else "") + "."]

    if name:
        return [f"{bold('Ưu đãi')}: {name}.", _VALUELESS]
    return [_VALUELESS]


#: Khách CHỦ ĐỘNG xin tính chi phí sử dụng / lăn bánh.
#:
#: Sếp 2026-08-27: bảng chi phí KHÔNG còn tự hiện lúc khách vừa chọn xe. Thứ tự
#: mới là xem xe → hỏi han về xe → khi nào khách muốn thì mới tính tiền. Đổ một
#: bảng chi phí vào đúng lúc khách vừa nhìn thấy chiếc xe mình thích là kéo câu
#: chuyện về tiền trước khi họ kịp thích nó.
#:
#: Cụm phải nói về CHI PHÍ, không phải về giá bán: "giá bao nhiêu" là câu hỏi tra
#: cứu đã có đường xử lý riêng, còn đây là bảng năm năm.
_COST_REQUEST: Final[re.Pattern[str]] = re.compile(
    r"\b(?:tco|chi phi|chiphi|lan banh|nuoi xe|"
    r"tinh (?:gia|tien|chi phi|thu|giup|ho|xem)|"
    r"uoc (?:chung|tinh)|tong (?:chi phi|tien)|"
    r"toi tot bao nhieu|het bao nhieu tien)\b"
)


def asks_for_cost_estimate(canonical: CanonicalText) -> bool:
    """Khách có đang xin bảng chi phí không.

    Đọc TẤT ĐỊNH vì đây là chỗ quyết định có đổ một bảng số vào màn hình hay
    không — và mô hình đoán sai chiều nào cũng dở: đoán có thì nói tiền khi khách
    chưa hỏi, đoán không thì im khi họ vừa hỏi thẳng.
    """

    return _COST_REQUEST.search(canonical.folded) is not None


class CostConsent(StrEnum):
    """Khách trả lời câu "em tính lại chi phí lăn bánh nhé"."""

    AGREE = "AGREE"
    DECLINE = "DECLINE"
    UNCLEAR = "UNCLEAR"


#: TỪ CHỐI xét TRƯỚC, cùng lý do với `concern_reply.classify_concern_reply`: câu
#: "thôi khỏi, cảm ơn em" mở bằng chữ chối, và xét lời nhận trước sẽ để chữ "cảm
#: ơn" kéo nó thành đồng ý.
_DECLINE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:thoi|khoi|khong can|khong cn|ko can|k can|de sau|de luc khac|chua can|khong|ko)\b"
)

#: NHẬN LỜI. Lõi là từ trọn vẹn — cùng khuôn `test_drive_booking._ACCEPT_PATTERN`,
#: để hai chỗ đọc lời đồng ý không lệch nhau.
#:
#: Chia làm HAI mẫu, và đó là điều kiện đúng đắn chứ không phải chỗ cầu kỳ:
#:
#: - `_AGREE_LEAD` — tiếng ừ hử ngắn, chỉ tính khi đứng ĐẦU câu.
#: - `_AGREE_ANY` — cụm nói rõ việc cần làm, đứng đâu cũng tính.
#:
#: Neo `da` vào đầu câu là bắt buộc: bỏ dấu thì **"đã" và "dạ" trùng nhau**, nên
#: câu hoãn *"anh xem lại đã"* bị đọc thành lời đồng ý. Cùng họ bẫy với "đặt" và
#: "đắt" ở `concern_reply`, và hậu quả ở đây là ta thay một con số khách chưa xin.
#:
#: "xem" và "muốn" cũng đã bị loại, cùng lý do: *"anh muốn xem xe khác"* không
#: phải lời nhận cho câu hỏi về chi phí.
_AGREE_LEAD: Final[re.Pattern[str]] = re.compile(r"^(?:co|vang|da|u|uh|um|ok|oke|okie)\b")
_AGREE_ANY: Final[re.Pattern[str]] = re.compile(r"\b(?:dong y|duoc|nho em tinh|em tinh|tinh (?:di|giup|ho|lai|luon))\b")


def classify_cost_consent(canonical: CanonicalText) -> CostConsent:
    """Khách có muốn tính lại chi phí theo ưu đãi không.

    `UNCLEAR` là kết cục HỢP LỆ và phải hỏi lại, không được đoán: đoán "có" thì
    ta thay một con số khách chưa xin, đoán "không" thì bỏ mất đúng việc vừa mời.
    """

    folded = canonical.folded.strip()
    if not folded:
        return CostConsent.UNCLEAR
    if _DECLINE.search(folded):
        return CostConsent.DECLINE
    if _AGREE_LEAD.match(folded) or _AGREE_ANY.search(folded):
        return CostConsent.AGREE
    return CostConsent.UNCLEAR


__all__ = [
    "CostConsent",
    "advisor_still_looking_notice",
    "asks_for_cost_estimate",
    "classify_cost_consent",
    "discount_amount",
    "offer_announcement",
    "total_discount",
]
