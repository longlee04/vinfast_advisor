"""Closed claim vocabulary for evidence-backed advisory prose.

The LLM may arrange sentences, but it may not invent why a vehicle is suitable.
Every suitability statement is represented by a placeholder whose text is rendered
from a scoring reason that already passed deterministic domain rules.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from src.agents.domain.budget_parsing import (
    BUDGET_TOLERANCE,
    NO_BUDGET_LIMIT_VND,
)

#: `ScoringReason.render()` (`domain/scoring.py`) không CHỈ ghi `slot=` — lý do
#: có nguồn need-tag/feature (`_need_tag_reasons`, `_document_reasons`,
#: `_feature_mention_reasons`) còn nối thêm `need_tag=`/`feature_code=`/
#: `source=`/`evidence=` trước dấu `]`. Pattern cũ chỉ khớp `[slot=x]` TRƠN
#: nên BA nguồn lý do đó chưa từng sinh được claim nào — bug có sẵn, lộ ra khi
#: nối `_feature_mention_reasons` (Sếp 2026-08-21). Terminator `[;\]]` chấp
#: nhận cả hai dạng.
SLOT_TRACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\[slot=([a-z_]+)[;\]]")
FEATURE_CODE_TRACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"feature_code=([A-Za-z0-9_]+)")
#: Lý do đến từ `_feature_mention_reasons` — khách CHỦ ĐỘNG xác nhận ở lượt 2,
#: khác hẳn feature suy từ need-tag (`_need_tag_reasons`) nên cần claim text
#: riêng, không dùng chung câu "phù hợp thói quen sử dụng" chung chung. Bắt
#: luôn NHÃN cụ thể (vd "khoá chống trộm") từ message — `scoring.py` đã giải
#: nhãn qua `ScoringProfile.feature_mention_labels` (Sếp 2026-08-21: khách
#: hỏi "khoá chống trộm thì sao" mà claim chỉ nói chung chung "tính năng anh/
#: chị vừa xác nhận" là không đủ, phải gọi đúng tên).
_CUSTOMER_CONFIRMED_FEATURE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"Có tính năng (.+?) mà khách vừa xác nhận quan tâm"
)
#: Lý do đến từ `scoring._feature_showcase_reasons` — tính năng xe THẬT SỰ có
#: nhưng khách CHƯA hỏi tới. Khác `_CUSTOMER_CONFIRMED_FEATURE_PATTERN` ở chỗ
#: không được nói "Quý khách vừa xác nhận" (khách có xác nhận gì đâu), và khác
#: câu chung `_CLAIM_TEXT_BY_SLOT["habit_need_tags"]` ở chỗ gọi ĐÚNG TÊN tính
#: năng thay vì "có tính năng đã kiểm chứng đúng với thói quen sử dụng".
_APPROVED_FEATURE_PATTERN: Final[re.Pattern[str]] = re.compile(r"Xe được trang bị (.+?) theo dữ liệu đã duyệt")
CLAIM_PLACEHOLDER_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{(CLAIM_[A-Z][A-Z0-9_]*)\}")
UNSTRUCTURED_CLAIM_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(?:phù\s*hợp|lý\s*tưởng|thích\s*hợp|đáp\s*ứng|hỗ\s*trợ|"
    r"tốt\s+cho|đủ\s+cho)\b"
    # Nhóm B: câu tán dương mơ hồ không căn cứ nào. Ba loại:
    # - thuộc tính vật lý KHÔNG đo được (gầm cao, thân xe lớn) — catalog không có
    #   cột `ground_clearance_mm` hay kích thước, nên không gì đỡ được;
    # - cảm tính không đo được (êm ái) — không có dữ liệu treo/cách âm/NVH;
    # - từ tuyệt đối (tuyệt đối, vượt trội, hàng đầu).
    #
    # "mạnh mẽ" ĐÃ RỜI danh sách này (Sếp 2026-08-26): nó đo được bằng
    # `CAR_MOTOR_POWER_KW`, nên `perceptual_traits` cấp phép theo số thay vì cấm
    # thẳng. Chặn cứng ở đây là giết cả câu ĐÚNG — VF 9 công suất 300 kW.
    # "gầm cao" RỜI theo, cùng lý do nhưng căn cứ là một giá trị CHỮ:
    # `CAR_BODY_TYPE` có đủ cho 11/11 mẫu, và `perceptual_traits.TRAIT_SUV_STANCE`
    # chỉ cấp phép cho xe thật sự là SUV — VF 2 (Hatchback) vẫn bị chặn.
    # "rộng rãi" TRẦN thì ở lại: số lít đo được là KHOANG HÀNH LÝ, không phải
    # cabin (VF 9 to nhất, bảy chỗ, mà chỉ 212 L). Muốn nói thì phải nói rõ
    # "khoang hành lý rộng" — cụm đó `perceptual_traits` quản.
    #
    # "sang trọng" đi kèm lookahead ÂM "tiện nghi" để không dính name_vi
    # "Sang trọng tiện nghi" (nhãn PREMIUM_COMFORT hợp lệ); "tiết kiệm" trần cũng
    # cấm vì dính name_vi "Tiết kiệm chi phí" — chỉ chặn "tiết kiệm điện".
    #
    # "tiện lợi" thêm 2026-08-27, Sếp bắt được trên prod. Đo trên 6 pitch
    # thật liên tiếp: 5 cái mang cụm này, và không cái nào có căn cứ —
    #     "hợp với mục đích sử dụng … nên RẤT TIỆN LỢI cho việc di chuyển
    #      trong đô thị"   ← nhại lại lời khách rồi khẳng định thành
    #                        đặc tính sản phẩm
    # Cùng một câu đã bị bắt hồi 2026-08-26 ở vế "nhỏ gọn"; vế "rất tiện lợi"
    # sống sót vì không có trong danh sách, nên nguyên nửa câu bịa vẫn ra tới
    # khách suốt từ đó.
    #
    # Phải là CỤM "tiện lợi", không phải "tiện" trần: claim hợp lệ
    # `home_charging` viết "THUẬN TIỆN sạc tại nhà".
    r"|\b(?:rộng\s+rãi|thân\s+xe\s+lớn|êm\s+ái|tiện\s+lợi|linh\s+hoạt|"
    r"tiết\s+kiệm\s+điện|tuyệt\s+đối|vượt\s+trội|hàng\s+đầu)\b"
    r"|\bsang\s*trọng\b(?!\s*tiện\s*nghi)",
    re.IGNORECASE,
)

#: Câu chữ của từng claim, viết như một tư vấn viên nói — KHÔNG phải như một bản
#: ghi dữ liệu. GIỌNG "anh/chị" từ 2026-08-31: bản "Quý khách" cũ lọt nguyên văn
#: ra prod qua đường synthesis (LLM chép claim vào pitch, không qua cửa
#: `render.assert_clean` vốn cấm chữ đó) — hai giọng trong cùng một bài. Bản cũ đọc là "đúng loại phương tiện bạn đang tìm, có giá nằm trong
#: ngân sách bạn đã xác nhận": đúng nghiệp vụ nhưng nghe như biên bản đối chiếu,
#: và "đã xác nhận" là từ của hệ thống chứ không phải của khách.
#:
#: Ba ràng buộc khi sửa những câu này, cả ba đều là ràng buộc cứng:
#: - KHÔNG chữ số (`synthesis._reject_digits_outside_placeholders`).
#: - KHÔNG dấu gạch dưới hay tên trường (`synthesis.RAW_STRUCTURED_PATTERN`).
#: - KHÔNG ghép "phù hợp/lý tưởng" với "đi xa/đường dài/về quê" khi không có dẫn
#:   chứng tài liệu (`semantic_validation.SEMANTIC_CLAIM_RULES`).
_CLAIM_TEXT_BY_SLOT: Final[dict[str, str]] = {
    "vehicle_type": "thuộc đúng dòng xe anh/chị đang tìm",
    "budget_max_vnd": "có giá nằm trong ngân sách anh/chị dự tính",
    "passenger_count": "đủ chỗ cho số người anh/chị thường chở",
    "required_range_km": "có tầm vận hành thoải mái cho quãng đường mỗi ngày",
    "home_charging": "thuận tiện sạc tại nhà theo điều kiện anh/chị chia sẻ",
    "purpose": "hợp với mục đích sử dụng anh/chị chia sẻ",
    "ENERGY_CONSUMPTION_KWH_PER_100KM": "tiết kiệm điện khi đi lại trong đô thị",
    "max_load_kg": "chở được khối lượng anh/chị cần",
    "habit_need_tags": "có tính năng đã kiểm chứng đúng với thói quen sử dụng",
}
_OVER_BUDGET_REASON_PATTERN: Final[re.Pattern[str]] = re.compile(r"\bvượt\s+ngân\s+sách\b", re.IGNORECASE)
#: Đối xứng với mẫu trên, cho lý do "Giá thấp hơn khoảng ngân sách đã nêu" mà
#: `scoring._budget_reasons` sinh ra khi khách nêu một KHOẢNG và xe nằm dưới đáy.
#:
#: Thiếu mẫu này thì một mẫu 188 triệu trong cuộc tư vấn "từ 400 đến 600 triệu"
#: nhận đúng câu claim của xe đúng ngân sách — tức nói với khách một điều sai, và
#: sai theo chiều khó phát hiện nhất vì câu đó nghe hoàn toàn bình thường.
_UNDER_BUDGET_REASON_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bthấp\s+hơn\s+khoảng\s+ngân\s+sách\b", re.IGNORECASE
)
#: Từ khác với `OVER_BUDGET_NOTE` một cách có chủ ý: nhãn đứng ngay trên đoạn
#: này rồi, nên lặp lại đúng chữ "nhỉnh hơn" khiến một thẻ xe nói cùng một câu
#: hai lần.
_OVER_BUDGET_CLAIM = "có giá cao hơn ngân sách anh/chị dự tính"
#: KHÔNG được viết "giá thấp": `quote_risk._NEGOTIATION_PATTERNS` có mẫu
#: `giá\s+(tốt|mềm|cuối|chốt|thấp)`, và cổng A7-4 quét cờ rủi ro trên
#: `user_message + draft_answer` — tức trên cả câu chữ của chính bot. Một claim
#: chứa "giá thấp" làm lượt tư vấn bị gắn `is_negotiated` và đẩy sang tư vấn viên
#: dù khách không hề mặc cả. Xem `test_claim_vocabulary_is_not_negotiation_language`.
_UNDER_BUDGET_CLAIM = "có mức giá dưới khoảng ngân sách anh/chị dự tính"


@dataclass(frozen=True, slots=True)
class PlannedClaim:
    """One deterministic customer-visible claim made available to synthesis."""

    placeholder: str
    slot: str
    text: str


def plan_claims(recommendation_reasons: Sequence[str]) -> tuple[PlannedClaim, ...]:
    """Convert traced scoring reasons into a unique, closed claim set.

    Lý do có `feature_code` (need-tag/tài liệu/khách xác nhận lượt 2) khoá
    riêng theo `slot:feature_code` thay vì chỉ `slot` — mỗi feature một claim,
    không gộp mất khi một candidate khớp nhiều feature khác nguồn. Trùng khoá
    (cùng slot, cùng feature_code) thì giữ claim gặp ĐẦU TIÊN — thứ tự trong
    `recommendation_reasons` (do `_score_candidate` quyết định) là chỗ duy nhất
    chọn ai thắng khi hai nguồn cùng nói về một feature.
    """

    claims: list[PlannedClaim] = []
    seen: set[str] = set()
    for reason in recommendation_reasons:
        match = SLOT_TRACE_PATTERN.search(reason)
        if match is None:
            continue
        slot = match.group(1)
        feature_match = FEATURE_CODE_TRACE_PATTERN.search(reason)
        feature_code = feature_match.group(1) if feature_match else None
        key = f"{slot}:{feature_code}" if feature_code is not None else slot
        if key in seen:
            continue
        text = _claim_text(slot, reason, feature_code)
        if text is None:
            continue
        seen.add(key)
        suffix = feature_code if feature_code is not None else slot
        claims.append(
            PlannedClaim(
                placeholder=f"CLAIM_{suffix.upper()}",
                slot=slot,
                text=text,
            )
        )
    return tuple(claims)


def _claim_text(slot: str, scoring_reason: str, feature_code: str | None) -> str | None:
    """Preserve the polarity of deterministic reasons when building prose claims."""

    if slot == "budget_max_vnd":
        if _OVER_BUDGET_REASON_PATTERN.search(scoring_reason):
            return _OVER_BUDGET_CLAIM
        if _UNDER_BUDGET_REASON_PATTERN.search(scoring_reason):
            return _UNDER_BUDGET_CLAIM
    if feature_code == "ENERGY_CONSUMPTION_KWH_PER_100KM":
        return _CLAIM_TEXT_BY_SLOT[feature_code]
    if feature_code is not None:
        confirmed_match = _CUSTOMER_CONFIRMED_FEATURE_PATTERN.search(scoring_reason)
        if confirmed_match is not None:
            label = confirmed_match.group(1)
            return f"có đúng {label} mà anh/chị vừa xác nhận quan tâm ở lượt trước"
        # SAU nhánh trên, không được đảo: cùng một feature_code có thể vừa được
        # khách xác nhận vừa nằm trong danh sách showcase, và lời "đúng thứ Quý
        # khách vừa hỏi" mạnh hơn hẳn lời kể suông.
        showcase_match = _APPROVED_FEATURE_PATTERN.search(scoring_reason)
        if showcase_match is not None:
            return f"được trang bị {showcase_match.group(1)}"
    return _CLAIM_TEXT_BY_SLOT.get(slot)


def reject_unstructured_claims(text_without_placeholders: str) -> None:
    """Reject free-form suitability assertions that bypass the claim plan."""

    if UNSTRUCTURED_CLAIM_PATTERN.search(text_without_placeholders):
        raise ValueError("suitability statement must use an approved claim placeholder")


#: Cụm chữ nhận ra một tính năng ĐANG ĐƯỢC KHẲNG ĐỊNH trong văn xuôi.
#:
#: **Bug thật 2026-08-26**: khách xin "một chiếc nhỏ gọn", hệ đề xuất VF 8 (SUV
#: cỡ D, dài 4750 mm) và pitch viết "với thiết kế nhỏ gọn, rất tiện lợi cho việc
#: di chuyển trong nội thành". Cờ `COMPACT_SIZE` chỉ gắn cho VF 2 và VF 3 —
#: catalog đúng, mô hình **nhại lại chính lời khách** thành lời khẳng định.
#:
#: `UNSTRUCTURED_CLAIM_PATTERN` không bắt được: nó chặn cụm TIẾP THỊ mơ hồ
#: ("phù hợp", "lý tưởng"), còn "nhỏ gọn" nghe như một SỰ THẬT.
#:
#: **Vì sao chặn được**: mọi thứ CÓ căn cứ đều đi qua placeholder, và hàm này chỉ
#: nhận phần văn xuôi ĐÃ BÓC placeholder. Tên tính năng còn sót lại ở đó là tên
#: không có căn cứ — cùng tinh thần luật "chữ số phải nằm trong placeholder".
#:
#: ⚠️ Cụm phải ĐỦ ĐẶC TRƯNG, đây là chỗ dễ dính bẫy 3.5 nhất. `"sạc"` trần không
#: được vào danh sách vì "thời gian sạc tại nhà" là câu hợp lệ; phải là
#: `"sạc nhanh"`. `"da"` không được vào vì nó nằm trong "đa dạng"; phải là
#: `"ghế bọc da"`. Thêm mã mới thì bắt buộc thêm một ca ÂM TÍNH vào
#: `tests/agents/unit/domain/test_unbacked_feature_claim.py`.
#:
#: Danh sách này cố ý chỉ phủ những mã mà một lời khẳng định sai gây hiểu lầm
#: nặng nhất về sản phẩm. Tập mã là ĐÓNG (28 mã) nên nó hoàn thiện dần được,
#: khác hẳn việc đuổi theo chủ đề ngoài ngành.
_FEATURE_CLAIM_CUES: Final[dict[str, tuple[str, ...]]] = {
    "COMPACT_SIZE": ("nhỏ gọn",),
    "7_SEATER": ("bảy chỗ", "ba hàng ghế", "7 chỗ"),
    "PANORAMIC_ROOF": ("cửa sổ trời", "nóc kính", "kính toàn cảnh"),
    "ADAS_SUITE": ("giữ làn", "phanh khẩn cấp"),
    "BLIND_SPOT_MONITOR": ("điểm mù",),
    "CAMERA_360": ("camera quan sát toàn cảnh", "camera toàn cảnh", "camera 360"),
    "FAST_CHARGING": ("sạc nhanh",),
    "HIGH_RANGE_BATTERY": ("pin dung lượng lớn", "pin đi được xa", "đi được xa"),
    # HIGH_PAYLOAD KHÔNG có mặt ở đây, cố ý (Sếp 2026-08-26). Nó là một trong ba
    # mã 0 cờ YES, nên cue của nó hại cả hai chiều: khách gõ "chở nặng" thì quy về
    # một mã không xe nào mang (im lặng, 0 điểm), còn pitch nói "chở nặng" thì bị
    # `reject_unbacked_feature_claims` chặn VĨNH VIỄN vì mã này không bao giờ vào
    # nổi tập đã duyệt — kể cả xe máy tải 180 kg có thật.
    # Ba cụm đó chuyển sang `perceptual_traits.TRAIT_HEAVY_CARRY`, cấp phép theo
    # `MOTORBIKE_MAX_LOAD_KG` (phủ 40/40 xe máy). Ngày nào catalog duyệt cờ
    # HIGH_PAYLOAD thật thì cân lại chỗ này — hai bảng không được cùng giữ một cụm.
    "ANTI_THEFT": ("khoá chống trộm", "chống trộm"),
    "BATTERY_REMOVABLE": ("pin tháo rời",),
    "BATTERY_SWAPPABLE": ("đổi pin", "pin đổi"),
    "TOWING": ("móc kéo", "kéo moóc"),
    "LEATHER_SEATS": ("ghế bọc da", "ghế da"),
    "VENTILATED_SEATS": ("ghế thông gió",),
    "POWER_DRIVER_SEAT": ("ghế lái chỉnh điện", "ghế chỉnh điện"),
    "MULTI_ZONE_AC": (
        "điều hòa tự động chia vùng",
        "điều hoà tự động chia vùng",
        "điều hòa 2 vùng",
    ),
    "WIRELESS_CHARGING": ("sạc điện thoại không dây", "sạc không dây"),
    "HEAD_UP_DISPLAY": ("hiển thị trên kính lái", "màn hình hud", "hud"),
    "ISOFIX_ANCHORS": ("isofix",),
    "POWER_TAILGATE": ("cốp sau chỉnh điện", "cốp điện"),
    "ECO_MODE": ("chế độ lái tiết kiệm", "chế độ eco"),
    "GPS": ("định vị gps", "gps"),
    "BLUETOOTH": ("bluetooth",),
    "ESIM": ("esim",),
    "MOBILE_APP": ("ứng dụng điều khiển", "ứng dụng điện thoại"),
    "SMARTPHONE_MIRRORING": ("carplay", "android auto"),
    "AUTO_SHUTOFF_CHARGER": ("tự ngắt khi đầy", "sạc tự ngắt"),
}


def feature_claim_label(code: str) -> str | None:
    """Cụm tiếng Việt tự nhiên nhất cho một mã tính năng, hoặc `None` nếu lạ.

    Lấy cụm ĐẦU TIÊN trong `_FEATURE_CLAIM_CUES[code]` — bảng cụm nhận-diện
    tính năng trong văn xuôi ở trên, cụm đầu luôn là cách nói tự nhiên nhất
    (VD "7_SEATER" → "bảy chỗ"). Lối vào PUBLIC duy nhất cho render lõi v2
    (`src/agents/core/render.py`) dịch mã tính năng thô sang chữ khách đọc
    được — không đọc thẳng `_FEATURE_CLAIM_CUES` (private) từ module khác.
    """

    cues = _FEATURE_CLAIM_CUES.get(code)
    return cues[0] if cues else None


_CLAIM_PREFIX: Final[str] = "CLAIM_"


def approved_feature_codes(claim_by_key: Mapping[str, object]) -> frozenset[str]:
    """Mã tính năng đã có căn cứ, suy từ khoá của claim plan.

    Khoá là `CLAIM_<HẬU_TỐ>`, trong đó hậu tố là `feature_code` khi lý do gắn
    với một tính năng, còn lại là tên slot (`CLAIM_BUDGET_MAX_VND`). Hậu tố không
    phải mã tính năng thì vô hại — nó chỉ không khớp mã nào trong bảng cụm chữ.

    Tách thành hàm riêng vì hình dạng khoá này là một HỢP ĐỒNG ngầm giữa
    `plan_claims` và chỗ kiểm nháp. Bản nối đầu tiên đoán khoá có dạng
    `slot:feature_code` và cho ra tập RỖNG — tức chặn nhầm mọi pitch hợp lệ, một
    lỗi im lặng vì test cũ không có tên tính năng nào trong văn xuôi.
    """

    return frozenset(key.removeprefix(_CLAIM_PREFIX) for key in claim_by_key if key.startswith(_CLAIM_PREFIX))


def _fold_diacritics(value: str) -> str:
    """Bỏ dấu + gộp khoảng trắng, để so khớp không phụ thuộc cách gõ.

    Gõ KHÔNG DẤU là cách viết rất thường trong chat, không phải lỗi gõ. Bản đầu
    chỉ `casefold()` nên "nho gon" không khớp "nhỏ gọn" — đo trên prod thấy hàm
    trả rỗng cho bản không dấu và đúng mã cho bản có dấu của CÙNG một câu.

    Bỏ dấu làm nhiều chữ trùng nhau ("đa" → "da"), nên ca âm tính phải kiểm ở CẢ
    hai dạng — xem test đi kèm.
    """

    decomposed = unicodedata.normalize("NFD", value.casefold())
    plain = "".join(character for character in decomposed if unicodedata.category(character) != "Mn")
    return re.sub(r"\s+", " ", plain.replace("đ", "d"))


#: Bảng cụm chữ đã bỏ dấu sẵn — tính một lần lúc import, không mỗi lượt.
_FOLDED_CLAIM_CUES: Final[dict[str, tuple[str, ...]]] = {
    code: tuple(_fold_diacritics(cue) for cue in cues) for code, cues in _FEATURE_CLAIM_CUES.items()
}


#: Cụm PHỦ ĐỊNH đứng trước một cụm tính năng, cho phép chen tối đa 2 chữ
#: ("không cần xe 7 chỗ", "ghét camera 360"). Đo 2026-08-28: "không cần 7 chỗ,
#: không cần camera 360" bị đọc thành YÊU CẦU hai tính năng đó.
_NEGATION_BEFORE_CUE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:khong\s+can|khong\s+co|khong\s+thich|khong|ko|k|chang|dung|ghet|bo|khoi\s+can|mien|thoi)"
    r"(?:\s+\w+){0,2}\s*$"
)


def negated_feature_codes(text: str) -> frozenset[str]:
    """Mã tính năng khách nói KHÔNG cần — để loại khỏi yêu cầu, không cộng điểm."""

    haystack = _fold_diacritics(text)
    negated: set[str] = set()
    for code, cues in _FOLDED_CLAIM_CUES.items():
        for cue in cues:
            for match in re.finditer(re.escape(cue), haystack):
                if _NEGATION_BEFORE_CUE.search(haystack[max(0, match.start() - 30) : match.start()]):
                    negated.add(code)
    return frozenset(negated)


def feature_codes_mentioned(text: str) -> frozenset[str]:
    """Lời khách → mã tính năng, bằng chính bảng cụm chữ ở trên.

    Chiều NGƯỢC của cùng một bảng. Chữ nào đủ đặc trưng để kết tội một câu bịa
    thì cũng đủ đặc trưng để nhận ra một yêu cầu — giữ MỘT bảng cho hai chiều là
    cách chắc chắn nhất để chúng không lệch nhau.

    **Vì sao cần**: đo trên prod 2026-08-26, prompt trích slot đã khai đúng
    `COMPACT_SIZE = thân xe nhỏ gọn` (kiểm bằng cách đọc thẳng schema trong
    container) mà mô hình vẫn trả `feature_mentions=[]` cho câu "anh chỉ cần 1
    chiếc nhỏ gọn". Cùng kiểu với bộ phân loại phạm vi ở mục 3.14: prompt đúng,
    mô hình không theo. Bản đọc tất định là lối ra.

    Nhận NHẦM ở chiều này gán cho khách một yêu cầu họ chưa nêu rồi cộng điểm
    cho xe sai — nên mọi cụm mới phải qua ca âm tính trong
    `tests/agents/unit/domain/test_unbacked_feature_claim.py`.
    """

    haystack = _fold_diacritics(text)
    return frozenset(code for code, cues in _FOLDED_CLAIM_CUES.items() if any(cue in haystack for cue in cues))


#: Mã tính năng mà SNAPSHOT của chính lượt đó đã chứng minh, không cần claim plan.
#:
#: BUG THẬT trên prod 2026-08-26: 32/32 pitch bị vứt đều cùng một lỗi
#: `unbacked feature claim in prose: FAST_CHARGING ('sac nhanh')`. Không mô hình
#: nào bịa cả — cả 10 ô tô ĐỀU có sạc nhanh, và số phút sạc nằm sẵn trong
#: snapshot dưới mã `FAST_CHARGE_TIME_MINUTES`. Nhưng `approved_feature_codes`
#: chỉ đọc claim plan, mà claim plan chỉ chứa tính năng KHÁCH NHẮC — khách không
#: nhắc sạc nhanh thì câu "sạc nhanh trong {FAST_CHARGE_TIME_MINUTES} phút" hoá
#: thành lời bịa, dù con số ngay bên cạnh là bằng chứng.
#:
#: Nặng hơn: `_SPEC_FIELDS` của bản dự phòng deterministic đặt nhãn "Thời gian
#: sạc nhanh" và "Công suất sạc nhanh", nên chính lưới đỡ cũng vướng cùng cái
#: bẫy — xe rơi vào nhánh dự phòng vẫn chết.
#:
#: Cùng tinh thần `perceptual_traits.traits_from_values`: tính năng dựa vào CỜ,
#: nhưng cờ không phải nguồn căn cứ DUY NHẤT — một con số trong snapshot cũng là
#: căn cứ, và nó còn chắc hơn cờ vì guardrail A6-1 đối chiếu được từng chữ số.
#:
#: Chỉ thêm mã vào bảng này khi sự có mặt của fact là bằng chứng ĐỦ cho lời
#: khẳng định. "Có số phút sạc nhanh" ⇒ "xe sạc nhanh được" là đủ; còn "có số
#: chỗ ngồi" KHÔNG suy ra được "bảy chỗ", nên `7_SEATER` không được vào đây.
_FACT_BACKED_FEATURE_CODES: Final[dict[str, tuple[str, ...]]] = {
    "FAST_CHARGING": ("FAST_CHARGE_TIME_MINUTES", "CAR_FAST_CHARGE_POWER_KW"),
}


def feature_codes_backed_by_facts(fact_codes: Collection[str]) -> frozenset[str]:
    """Mã tính năng được chính thông số trong snapshot của lượt chứng minh."""

    present = set(fact_codes)
    return frozenset(code for code, backing in _FACT_BACKED_FEATURE_CODES.items() if present.intersection(backing))


def reject_unbacked_feature_claims(text_without_placeholders: str, *, approved_feature_codes: frozenset[str]) -> None:
    """Chặn lời khẳng định về một tính năng mà xe KHÔNG có căn cứ.

    `approved_feature_codes` là mã đã được duyệt cho ĐÚNG chiếc xe đang pitch.
    Mã nào không nằm trong đó mà cụm chữ của nó xuất hiện trong văn xuôi thì đó
    là mô hình tự bịa — dừng lượt để nó viết lại.
    """

    haystack = _fold_diacritics(text_without_placeholders)
    for code, cues in _FOLDED_CLAIM_CUES.items():
        if code in approved_feature_codes:
            continue
        for cue in cues:
            if cue in haystack:
                raise ValueError(f"unbacked feature claim in prose: {code} ({cue!r})")


# ── Nhãn "lệch ngân sách" gắn lên thẻ xe ─────────────────────────────────────

OVER_BUDGET_NOTE: Final[str] = "(nhỉnh hơn ngân sách một chút)"
UNDER_BUDGET_NOTE: Final[str] = "(thấp hơn ngân sách một chút, tiết kiệm hơn)"
#: Lệch quá `BUDGET_TOLERANCE` thì KHÔNG gọi là "một chút" nữa, nhưng vẫn phải nói.
FAR_OVER_BUDGET_NOTE: Final[str] = "(cao hơn ngân sách)"
FAR_UNDER_BUDGET_NOTE: Final[str] = "(thấp hơn ngân sách)"


def budget_fit_note(
    *,
    price_vnd: Decimal | None,
    budget_min_vnd: Decimal | None,
    budget_max_vnd: Decimal | None,
) -> str | None:
    """Nhãn ngắn nói rõ xe này lệch ngân sách về phía nào, hoặc `None` khi vừa khoảng.

    LUÔN gắn nhãn khi giá nằm ngoài khoảng khách nêu. Bản đầu chỉ gắn khi lệch dưới
    `BUDGET_TOLERANCE` và im lặng khi lệch nhiều hơn — đúng chiều ngược: mẫu lệch
    nhiều nhất là mẫu khách cần được cảnh báo nhất, mà lại là mẫu không có nhãn nào.

    `BUDGET_TOLERANCE` chỉ quyết định CÂU CHỮ: trong biên thì là "một chút", ngoài
    biên thì nói thẳng. Một mẫu đắt gấp rưỡi ngân sách không bao giờ được gọi là
    "nhỉnh hơn một chút".
    """

    if price_vnd is None:
        return None
    if (
        budget_max_vnd is not None
        and budget_max_vnd > 0
        and budget_max_vnd < NO_BUDGET_LIMIT_VND
        and price_vnd > budget_max_vnd
    ):
        overshoot = (price_vnd - budget_max_vnd) / budget_max_vnd
        return OVER_BUDGET_NOTE if overshoot <= BUDGET_TOLERANCE else FAR_OVER_BUDGET_NOTE
    if budget_min_vnd is not None and budget_min_vnd > 0 and price_vnd < budget_min_vnd:
        shortfall = (budget_min_vnd - price_vnd) / budget_min_vnd
        return UNDER_BUDGET_NOTE if shortfall <= BUDGET_TOLERANCE else FAR_UNDER_BUDGET_NOTE
    return None


#: Đầu câu của những claim nói về TRANG BỊ trên xe — xem `_claim_text`.
#:
#: Chỉ chúng được phép nằm trong câu "Ngoài ra xe còn …" của prompt tổng hợp.
#: Bug thật trên prod 2026-08-27: lời dặn cũ không nêu tên placeholder nào, nên
#: mô hình vơ cả thông số lẫn claim slot vào — "Ngoài ra xe còn 5 chỗ ngồi" (đọc
#: như còn thừa 5 chỗ) và "Ngoài ra xe còn thuộc đúng dòng xe Quý khách đang tìm".
EQUIPMENT_CLAIM_PREFIXES: Final[tuple[str, ...]] = ("được trang bị ", "có đúng ")
