"""[A7-9] Phân loại và định tuyến bốn câu hỏi thuộc nhóm ĐỊNH GIÁ.

Một trong bốn được chạy tự động, ba còn lại vẫn phải có người duyệt:

- `ON_ROAD_PRICE_LOOKUP` — **tự động** khi đủ slot. Giá lăn bánh là phép cộng cố
  định trên biểu phí đã công bố (`tools/on_road_price.py`), cùng bản chất với giá
  niêm yết mà A7-4 đã cho đi thẳng, và KHÔNG nằm trong bốn loại câu trả lời bắt
  buộc HITL của `docs/vinfast-agent-mvp.md` §A7.
- `TCO_ESTIMATE_LOOKUP` — **vẫn qua HITL**. PRD xếp TCO vào đúng bốn loại đó, và
  tiêu chí hoàn thành 3 ghi cam kết duyệt "không có ngoại lệ". Đây là quyết định
  đã cân nhắc, không phải bỏ sót: TCO là ước tính nhiều tầng giả định, tư vấn
  viên cần duyệt hoặc hiệu chỉnh trước khi con số tới khách.
- `PRICE_NEGOTIATION` — khách mặc cả. "Giá lăn bánh bao nhiêu" là hỏi một con số
  tính được; "giảm cho em 20 triệu" là xin một con số CHƯA tồn tại.
- `CUSTOM_FINANCING` — trả góp với lãi suất/kỳ hạn tự chọn.

Câu mang CẢ hai yếu tố ("giá lăn bánh vf5, giảm được không") luôn về nhóm HITL:
một câu vừa hỏi vừa mặc cả thì phần mặc cả là phần quyết định.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.quote_risk import detect_risk_flags
from src.agents.domain.text_normalization import contains_keyword


class PricingIntent(StrEnum):
    """Sub-intent của nhóm định giá. `NONE` = câu hỏi không thuộc nhóm này."""

    ON_ROAD_PRICE_LOOKUP = "ON_ROAD_PRICE_LOOKUP"
    TCO_ESTIMATE_LOOKUP = "TCO_ESTIMATE_LOOKUP"
    PRICE_NEGOTIATION = "PRICE_NEGOTIATION"
    CUSTOM_FINANCING = "CUSTOM_FINANCING"
    NONE = "NONE"


class PricingRoute(StrEnum):
    """Ba đường đi, khớp pseudocode trong đặc tả A7-9."""

    AUTO_TOOL_CALL = "AUTO_TOOL_CALL"
    SLOT_FILLING = "SLOT_FILLING"
    HITL_REQUIRED = "HITL_REQUIRED"


class RiskTier(StrEnum):
    LOW = "LOW"
    HIGH = "HIGH"


_ON_ROAD_KEYWORDS: Final[tuple[str, ...]] = (
    "lăn bánh",
    "phí lăn bánh",
    "giá lăn",
    "giá ra biển",
    "chi phí ra biển",
    "phí đăng ký",
    "chi phí đăng ký",
    "on-road price",
    "on road price",
    "ra biển",
    "tổng chi phí mua xe",
    "mua xe hết bao nhiêu",
)
_TCO_KEYWORDS: Final[tuple[str, ...]] = (
    "tco",
    "chi phí sở hữu",
    "chi phí sử dụng",
    "nuôi xe",
    "chi phí vận hành",
    "tốn bao nhiêu một năm",
    "tốn bao nhiêu 1 năm",
    "chi phí mỗi năm",
)
#: Trả góp TỰ CHỌN. "trả góp" trần không đủ: hỏi gói mặc định là tra cứu được,
#: chỉ khi khách tự đặt lãi suất/kỳ hạn mới cần người duyệt.
_CUSTOM_FINANCING_KEYWORDS: Final[tuple[str, ...]] = (
    "lãi suất",
    "kỳ hạn",
    "ky han",
    "trả trong",
    "vay bao nhiêu",
    "trả góp bao nhiêu năm",
    "trả góp mấy năm",
)


def mentions_on_road_price(user_message: str) -> bool:
    """Câu có nhắc GIÁ LĂN BÁNH — kể cả gõ không dấu ("vf3 lan banh bn").

    Cửa tất định cho `core/understand`: blind run 2026-08-31 cho thấy LLM gán
    câu này CATALOG_LOOKUP và khách nhận nguyên bảng thông số — một con số nhỏ
    hơn thực tế hàng chục triệu vì thiếu trước bạ/biển số.
    """

    return any(contains_keyword(user_message, keyword) for keyword in _ON_ROAD_KEYWORDS)


def classify_pricing_intent(user_message: str, canonical: CanonicalText) -> PricingIntent:
    """Phân loại một câu hỏi vào nhóm định giá.

    Thứ tự cố ý: hai nhóm CHẶN xét trước hai nhóm tự động. Câu "giá lăn bánh vf5
    có giảm được không" mang cả hai, và phần cần người quyết định phải thắng —
    nhầm chiều này là để agent tự thương lượng giá.

    So khớp rủi ro chạy trên `canonical` sinh tại chain — gate không tự
    normalize (ENG REVIEW AMENDMENT 2).
    """

    if not canonical.original:
        return PricingIntent.NONE
    if detect_risk_flags(user_message=user_message, canonical=canonical)["is_negotiated"]:
        return PricingIntent.PRICE_NEGOTIATION
    # Khớp qua `contains_keyword`: bảng từ khoá viết CÓ dấu, còn khách gõ
    # nhanh thì không. "gia lan banh cua vf 5" trước đây rơi về `NONE` và
    # khách hỏi giá lăn bánh nhận về bảng thông số — thiếu hẳn phí trước bạ,
    # biển số, bảo hiểm, tức một con số nhỏ hơn thực tế hàng chục triệu.
    #
    # Hàm đó CHỈ bỏ dấu khi câu không có dấu nào; câu có dấu vẫn khớp chặt
    # như cũ, nên không lượt nào đang chạy bị đổi kết quả.
    if any(contains_keyword(user_message, kw) for kw in _CUSTOM_FINANCING_KEYWORDS):
        return PricingIntent.CUSTOM_FINANCING
    if any(contains_keyword(user_message, kw) for kw in _ON_ROAD_KEYWORDS):
        return PricingIntent.ON_ROAD_PRICE_LOOKUP
    if any(contains_keyword(user_message, kw) for kw in _TCO_KEYWORDS):
        return PricingIntent.TCO_ESTIMATE_LOOKUP
    return PricingIntent.NONE


# ── Nhận diện tỉnh/thành ──────────────────────────────────────────────────────
#
# [GIẢ ĐỊNH] Khớp theo danh sách tĩnh trong domain thay vì đọc bảng `locations`:
# routing chỉ cần biết "khách đã nêu tỉnh hay chưa", và một lần truy vấn database
# cho câu hỏi đó là đắt hơn giá trị nó mang lại.
#
# **Phủ hết tỉnh có showroom** (Sếp 2026-08-26). Bản trước chỉ có 10 tỉnh "lượng
# khách lớn", nên khách gõ "Tuyên Quang" không được nhận ra — hệ tưởng họ chưa
# trả lời và hỏi lại đúng câu vừa hỏi. Với TCO thì càng vô lý: câu hỏi thật chỉ
# là "có phải Hà Nội/TP.HCM không", mà một tỉnh không có trong bảng lại không
# trả lời nổi cả câu đó.
#
# 36 tên dưới đây lấy từ địa chỉ showroom trong `data-p150/locations` — đúng tập
# tỉnh VinFast đang có mặt. Mã của 9 tỉnh cũ giữ nguyên (`HN`, `HCM`, `DN`…) vì
# `on_road_price` so sánh mã với `region_code` của bảng phí; tỉnh mới dùng slug
# đầy đủ để không đụng mã cũ và không trùng nhau (`TN` sẽ vừa là Thái Nguyên vừa
# là Tây Ninh).
PROVINCES: Final[dict[str, str]] = {
    "hà nội": "HN",
    "ha noi": "HN",
    "hn": "HN",
    "thủ đô": "HN",
    "hồ chí minh": "HCM",
    "ho chi minh": "HCM",
    "tphcm": "HCM",
    "tp hcm": "HCM",
    "hcm": "HCM",
    "sài gòn": "HCM",
    "sai gon": "HCM",
    "đà nẵng": "DN",
    "da nang": "DN",
    "hải phòng": "HP",
    "hai phong": "HP",
    "cần thơ": "CT",
    "can tho": "CT",
    "bình dương": "BD",
    "đồng nai": "DNA",
    "dong nai": "DNA",
    "khánh hòa": "KH",
    "nha trang": "KH",
    "huế": "HUE",
    "nghệ an": "NA",
    "vinh": "NA",
    "an giang": "AN_GIANG",
    "bình định": "BINH_DINH",
    "binh dinh": "BINH_DINH",
    "bắc ninh": "BAC_NINH",
    "bac ninh": "BAC_NINH",
    "cao bằng": "CAO_BANG",
    "cao bang": "CAO_BANG",
    "cà mau": "CA_MAU",
    "ca mau": "CA_MAU",
    "gia lai": "GIA_LAI",
    "hà tĩnh": "HA_TINH",
    "ha tinh": "HA_TINH",
    "hưng yên": "HUNG_YEN",
    "hung yen": "HUNG_YEN",
    "kiên giang": "KIEN_GIANG",
    "kien giang": "KIEN_GIANG",
    "lai châu": "LAI_CHAU",
    "lai chau": "LAI_CHAU",
    "lào cai": "LAO_CAI",
    "lao cai": "LAO_CAI",
    "lâm đồng": "LAM_DONG",
    "lam dong": "LAM_DONG",
    "lạng sơn": "LANG_SON",
    "lang son": "LANG_SON",
    "ninh bình": "NINH_BINH",
    "ninh binh": "NINH_BINH",
    "phú thọ": "PHU_THO",
    "phu tho": "PHU_THO",
    "quảng ngãi": "QUANG_NGAI",
    "quang ngai": "QUANG_NGAI",
    "quảng ninh": "QUANG_NINH",
    "quang ninh": "QUANG_NINH",
    "quảng trị": "QUANG_TRI",
    "quang tri": "QUANG_TRI",
    "sơn la": "SON_LA",
    "son la": "SON_LA",
    "thanh hóa": "THANH_HOA",
    "thanh hoa": "THANH_HOA",
    "thái nguyên": "THAI_NGUYEN",
    "thai nguyen": "THAI_NGUYEN",
    "tuyên quang": "TUYEN_QUANG",
    "tuyen quang": "TUYEN_QUANG",
    "tây ninh": "TAY_NINH",
    "tay ninh": "TAY_NINH",
    "vĩnh long": "VINH_LONG",
    "vinh long": "VINH_LONG",
    "điện biên": "DIEN_BIEN",
    "dien bien": "DIEN_BIEN",
    "đắk lắk": "DAK_LAK",
    "dak lak": "DAK_LAK",
    "đồng tháp": "DONG_THAP",
    "dong thap": "DONG_THAP",
}


#: Mã tỉnh thuộc Khu vực I của biểu lệ phí biển số. Ánh xạ này tồn tại vì
#: `PROVINCES` trả MÃ TỈNH ("HN"), còn `tco_assumptions` khoá theo MÃ KHU VỰC
#: ("KHU_VUC_I") — hai không gian mã khác nhau, nối nhầm thì tra cứu không khớp
#: dòng nào và câu trả lời im lặng biến mất.
_KHU_VUC_I_PROVINCE_CODES: Final[frozenset[str]] = frozenset({"HN", "HCM"})


def region_for_province_code(province_code: str | None) -> str:
    """Mã tỉnh → mã khu vực dùng để tra `tco_assumptions`."""

    return "KHU_VUC_I" if province_code and province_code.upper() in _KHU_VUC_I_PROVINCE_CODES else "KHU_VUC_II"


#: Tên tỉnh xét theo thứ tự DÀI TRƯỚC, không theo thứ tự khai báo.
#:
#: Ranh giới từ không đủ khi một tên là TIỀN TỐ của tên khác: "vinh" (Nghệ An)
#: khớp trọn vẹn vào "vinh long" vì sau nó là khoảng trắng, nên khách gõ "Vĩnh
#: Long" bị gán sang Nghệ An — sai tỉnh, sai luôn phí. Xét dài trước thì "vinh
#: long" ăn trước và "vinh" không bao giờ có cơ hội đọc nhầm.
#:
#: Sắp một lần ở tầm module: `detect_province` chạy mỗi lượt, sắp lại 77 tên
#: trong mỗi lần gọi là trả giá cho một thứ không bao giờ đổi.
_PROVINCE_NAMES_LONGEST_FIRST: Final[tuple[tuple[str, str], ...]] = tuple(
    sorted(PROVINCES.items(), key=lambda item: len(item[0]), reverse=True)
)


def detect_province(user_message: str, canonical: CanonicalText) -> str | None:
    """Mã tỉnh khách vừa nêu, hoặc `None` khi chưa nêu.

    Khớp theo RANH GIỚI TỪ cho các mã ngắn ("hn", "hcm"): tìm chuỗi con sẽ cho
    "hn" khớp vào "nhìn" và gán nhầm cả tỉnh cho khách. Chạy trên
    `canonical.original` (giữ dấu) — gate không tự normalize.
    """

    normalized = canonical.original
    for name, code in _PROVINCE_NAMES_LONGEST_FIRST:
        pattern = rf"(?<![a-zà-ỹ]){re.escape(name)}(?![a-zà-ỹ])"
        if re.search(pattern, normalized):
            return code
    return None


# ── Slot bắt buộc và quyết định đường đi ──────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PricingDecision:
    """Kết luận routing cho một câu hỏi định giá."""

    intent: PricingIntent
    route: PricingRoute
    risk_tier: RiskTier
    #: Slot bắt buộc còn thiếu — `route=SLOT_FILLING` thì đây là thứ phải hỏi.
    missing_slots: tuple[str, ...] = ()
    #: Slot đã dùng để gọi tool.
    resolved_slots: Mapping[str, object] | None = None


#: Slot BẮT BUỘC theo intent. Thiếu là hỏi lại, tuyệt đối không gọi tool với giá
#: trị rỗng hay mặc định — một con số phí trước bạ tính theo tỉnh mặc định là một
#: con số sai gửi cho khách, khác hẳn với việc chưa trả lời.
REQUIRED_SLOTS: Final[dict[PricingIntent, tuple[str, ...]]] = {
    PricingIntent.ON_ROAD_PRICE_LOOKUP: ("vehicle_variant", "province"),
}


def route_pricing_question(
    *,
    intent: PricingIntent,
    vehicle_variant: object | None,
    province: str | None = None,
) -> PricingDecision:
    """Quyết định lượt này gọi tool thẳng, hỏi thêm slot, hay chuyển người duyệt.

    Chỉ GIÁ LĂN BÁNH được chạy tự động. TCO ở lại nhánh HITL cùng
    `PRICE_NEGOTIATION` và `CUSTOM_FINANCING`: `docs/vinfast-agent-mvp.md` §A7 xếp
    TCO vào bốn loại câu trả lời bắt buộc có người duyệt, và tiêu chí hoàn thành 3
    ghi rõ cam kết đó "không có ngoại lệ". Giá lăn bánh KHÔNG nằm trong bốn loại
    ấy — nó là phép cộng cố định trên biểu phí đã công bố, cùng bản chất với giá
    niêm yết mà A7-4 đã cho đi thẳng.
    """

    if intent in {
        PricingIntent.TCO_ESTIMATE_LOOKUP,
        PricingIntent.PRICE_NEGOTIATION,
        PricingIntent.CUSTOM_FINANCING,
    }:
        return PricingDecision(intent=intent, route=PricingRoute.HITL_REQUIRED, risk_tier=RiskTier.HIGH)
    if intent is PricingIntent.ON_ROAD_PRICE_LOOKUP:
        return _route_on_road(vehicle_variant, province)
    return PricingDecision(intent=PricingIntent.NONE, route=PricingRoute.SLOT_FILLING, risk_tier=RiskTier.LOW)


def _route_on_road(vehicle_variant: object | None, province: str | None) -> PricingDecision:
    """Giá lăn bánh: variant và tỉnh đều BẮT BUỘC, không có mặc định.

    Tỉnh không được mặc định vì phí trước bạ và phí biển số khác nhau giữa các
    tỉnh; lấy đại một tỉnh là gửi cho khách một con số của địa phương khác — sai,
    chứ không phải thiếu.
    """

    missing = tuple(name for name, value in (("vehicle_variant", vehicle_variant), ("province", province)) if not value)
    if missing:
        return PricingDecision(
            intent=PricingIntent.ON_ROAD_PRICE_LOOKUP,
            route=PricingRoute.SLOT_FILLING,
            risk_tier=RiskTier.LOW,
            missing_slots=missing,
        )
    return PricingDecision(
        intent=PricingIntent.ON_ROAD_PRICE_LOOKUP,
        route=PricingRoute.AUTO_TOOL_CALL,
        risk_tier=RiskTier.LOW,
        resolved_slots={"vehicle_variant": vehicle_variant, "province": province},
    )


__all__ = [
    "PROVINCES",
    "REQUIRED_SLOTS",
    "PricingDecision",
    "PricingIntent",
    "PricingRoute",
    "RiskTier",
    "classify_pricing_intent",
    "detect_province",
    "region_for_province_code",
    "route_pricing_question",
]


@dataclass(frozen=True, slots=True)
class ProvinceOption:
    """Một tỉnh thành khách chọn được, kèm khu vực để client nói ra vì sao giá đổi."""

    code: str
    name: str
    region_code: str


def _display_name(alias: str) -> str:
    """Viết hoa đầu mỗi từ, giữ nguyên dấu: "hà nội" → "Hà Nội"."""

    return " ".join(word[:1].upper() + word[1:] for word in alias.split())


#: Danh sách tỉnh cho ô CHỌN trên giao diện, dựng từ chính bảng `PROVINCES`.
#:
#: Sếp 2026-08-27: thẻ chi phí phải cho khách chọn tỉnh ngay tại chỗ. Danh sách
#: suy từ bảng đang dùng để ĐỌC lời khách, nên hai chiều không bao giờ lệch:
#: tỉnh nào chọn được trên giao diện thì gõ tay cũng nhận ra, và ngược lại.
#:
#: Mỗi mã lấy bí danh CÓ DẤU và DÀI NHẤT làm tên hiển thị — "hà nội" thắng "hn",
#: "hồ chí minh" thắng "hcm". Bảng bí danh sinh ra để khớp lời khách gõ vội, còn
#: ô chọn thì phải đọc ra tên thật.
def province_options() -> tuple[ProvinceOption, str]:
    """Danh sách tỉnh đã sắp theo tên, và mã khu vực mặc định khi chưa chọn."""

    best: dict[str, tuple[tuple[bool, int], str]] = {}
    for alias, code in PROVINCES.items():
        score = (any(ord(character) > 127 for character in alias), len(alias))
        if code not in best or score > best[code][0]:
            best[code] = (score, alias)
    options = tuple(
        sorted(
            (
                ProvinceOption(code=code, name=_display_name(alias), region_code=region_for_province_code(code))
                for code, (_, alias) in best.items()
            ),
            key=lambda option: option.name,
        )
    )
    return options, region_for_province_code(None)


def assumption_note(*, daily_km: float, known_distance: bool, province: object) -> str:
    """Nói ra con số này đang đứng trên giả định nào, và mời sửa.

    Ở `domain/` chứ không ở `chain` vì có HAI nơi hiển thị chi phí và cả hai phải
    nói cùng một câu: khối chữ trong chat, và thẻ chi phí có ô chỉnh trên giao
    diện (`api/routes.estimate_tco`). Hai bản chữ là hai chỗ để lệch nhau, mà
    khách thì nhìn thấy cả hai trong cùng một màn hình.

    Bắt buộc, không phải lịch sự: một ước tính không nói mình ước tính theo gì thì
    khách không có cách nào biết nó sai ở đâu để sửa. Và ở đây có đúng hai chỗ có
    thể sai — quãng đường mỗi ngày, và khu vực đăng ký.

    Khu vực là chỗ sai đắt nhất: lệ phí biển số ô tô là 140.000đ ở Khu vực II và
    14.000.000đ ở Khu vực I (Hà Nội, TP.HCM) — chênh đúng 100 lần. Chưa biết tỉnh
    thì phải nói rõ con số đang tính theo mức nào, chứ không im lặng đưa một tổng.
    """

    distance = f"{int(daily_km)} km/ngày" + ("" if known_distance else " (em tạm tính)")
    if isinstance(province, str) and province:
        region = "Hà Nội/TP.HCM" if region_for_province_code(province) == "KHU_VUC_I" else "ngoài Hà Nội/TP.HCM"
        where = f"đăng ký tại khu vực {region}"
        invite = "Nếu quãng đường thực tế khác, anh/chị nói em tính lại ngay ạ."
    else:
        where = "đăng ký ngoài Hà Nội/TP.HCM (lệ phí biển số 140.000đ; nếu đăng ký tại Hà Nội hoặc TP.HCM thì khoản này là 14.000.000đ)"
        invite = "Anh/chị cho em biết quãng đường thực tế hoặc tỉnh đăng ký thì em tính lại ngay ạ."
    return f"Tính theo {distance}, {where}. {invite}"
