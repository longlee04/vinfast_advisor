"""Đối chiếu MỘT chiếc xe với nhu cầu khách đã kể — THUẦN, tất định.

Vì sao có file này: prod vòng 9 cho thấy khách hỏi thẳng "có hợp với nhu cầu
của tôi không" và lõi đáp "em ghi nhận anh/chị chọn VF 2. Anh/chị muốn em tính
chi phí…" — tức câu hỏi ĐÁNH GIÁ bị nuốt hoàn toàn. Không có chỗ nào trong lõi
v2 so số của xe với thứ khách vừa kể; `synthesis` có làm việc đó nhưng chỉ ở
lượt ĐỀ XUẤT, và nó là một bộ viết (LLM), không phải một câu trả lời có/không.

Ở đây KHÔNG có I/O và KHÔNG gọi LLM: vào là số của xe + nhu cầu đã chuẩn hoá,
ra là một kết luận ba mức kèm 1–3 lý do. Nhờ thuần nên cùng một câu hỏi luôn
nhận cùng một kết luận — thứ mà một bộ viết không hứa được.

Chữ tiếng Việt sinh ở đây (chứ không ở `render`) vì lý do sinh ra nó là SỐ: mỗi
lý do phải nói ra đúng con số đã so. Hai luật bù lại: (1) không bao giờ chép
chữ khách tự gõ vào lý do — mọi lý do dựng từ số và cụm cố định, nên
`render.assert_clean` không có gì để chặn; (2) tiền đi qua ĐÚNG
`render.format_number` mà cả lõi đang dùng, không có bộ định dạng thứ hai.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from src.agents.core.actions import FIT_PARTIAL, FIT_UNFIT, FIT_YES
from src.agents.core.render import format_number
from src.agents.domain.text_normalization import normalize
from src.agents.domain.values import SlotName, SlotValue

#: Mã tiêu chí — `act`/`render` đọc mã chứ không dò chữ trong lý do.
MISS_SEATS = "seats"
MISS_RANGE = "range"
MISS_TRUNK = "trunk"
MISS_PRICE = "price"

#: [GIẢ ĐỊNH] Một chuyến "đi xa" ở Việt Nam (Hà Nội → Ninh Bình, Sài Gòn →
#: Vũng Tàu và về) nằm quanh 300 km. Dưới mức này thì khách phải sạc giữa
#: đường — vẫn đi được, nên là "hợp một phần", không phải "chưa hợp".
LONG_TRIP_RANGE_KM = 300
#: [GIẢ ĐỊNH] Cốp dưới mức này thì cả nhà đi chơi phải xếp đồ lên ghế.
FAMILY_TRUNK_LITRES = 250
#: Mức NỚI ngân sách khi đi tìm mẫu thay thế. Khách nói "500 triệu" là nói một
#: khoảng, không phải một hàng rào: một chiếc 550 triệu chạy xa gấp rưỡi vẫn
#: đáng để họ nghe. Nới quá tay thì thành mời một chiếc gấp đôi tiền, nên 20%.
BUDGET_TOLERANCE = 0.2
#: Trần số lý do đọc cho khách. Nhiều hơn ba là đọc bảng thông số, không phải
#: trả lời câu hỏi "có hợp không".
MAX_REASONS = 3

#: Cụm (đã bỏ dấu) cho biết khách đi XA, không phải đi trong phố.
_LONG_TRIP_WORDS: tuple[str, ...] = (
    "di xa",
    "choi xa",
    "duong dai",
    "du lich",
    "ve que",
    "lien tinh",
    "di tinh",
    "phuot",
)
#: Cụm cho biết xe chở CẢ NHÀ (kéo theo yêu cầu cốp và số chỗ).
_FAMILY_WORDS: tuple[str, ...] = ("gia dinh", "ca nha", "vo con", "dua don con", "dua don ca nha")
#: Cụm cho biết khách CHỞ ĐỒ — cũng kéo cốp vào đối chiếu, dù đi một mình.
_CARGO_WORDS: tuple[str, ...] = ("nhieu do", "cho do", "do dac", "cho hang", "hang hoa", "chat do")
#: Thẻ nhu cầu đóng (`domain/need_tags.NeedTag`) nói cùng một việc.
_LONG_TRIP_TAGS = frozenset({"LONG_RANGE"})
_FAMILY_TAGS = frozenset({"FAMILY_TRIP"})

#: Khoá thông số của catalog. Cùng tên cột `tools/compare_vehicles` và
#: `VehicleFacts.specs` đang dùng — chép sang bộ tên riêng là dựng nguồn sự
#: thật thứ hai, và lần đổi cột tiếp theo sẽ làm module này im lặng mù đi.
_SEATS_KEYS = ("seat_count",)
_RANGE_KEYS = ("range_km", "range_max_km")
_TRUNK_KEYS = ("cargo_volume_standard_l",)


@dataclass(frozen=True, slots=True)
class VehicleSpec:
    """Số của một chiếc xe, đã rút gọn về đúng bốn thứ khách hỏi."""

    vehicle_id: str
    name: str = ""
    seats: int | None = None
    range_km: int | None = None
    trunk_litres: int | None = None
    price_vnd: int | None = None


@dataclass(frozen=True, slots=True)
class CustomerNeed:
    """Nhu cầu khách đã kể, đã chuẩn hoá về số và cờ."""

    budget_max_vnd: int | None = None
    passenger_count: int | None = None
    required_range_km: int | None = None
    #: Khách nói tới chuyến đi xa (mục đích tự do hoặc thẻ `LONG_RANGE`).
    long_trip: bool = False
    #: Xe chở cả nhà — kéo theo yêu cầu cốp.
    family: bool = False
    #: Khách nói tới chở đồ ("nhiều đồ", "chở hàng") — cũng kéo cốp vào đối chiếu.
    cargo: bool = False


@dataclass(frozen=True, slots=True)
class FitAssessment:
    """Kết luận một lượt đối chiếu. `verdict` là một trong ba mã `FIT_*`."""

    verdict: str
    reasons: tuple[str, ...] = ()
    #: Mã tiêu chí xe TRƯỢT — rỗng nghĩa là không trượt gì (hoặc không đủ số).
    missed: tuple[str, ...] = ()
    #: Số tiêu chí THẬT SỰ đối chiếu được. `0` nghĩa là kết luận không dựa trên
    #: con số nào — chỗ gọi phải im lặng thay vì đọc một câu nghe như đánh giá.
    checked: int = 0
    alternative_id: str = ""
    alternative_name: str = ""


@dataclass(frozen=True, slots=True)
class _Check:
    code: str
    ok: bool
    reason: str


def _int(value: object) -> int | None:
    """Số nguyên từ một giá trị catalog bất kỳ, hoặc `None`.

    Catalog trả cả `Decimal`, cả chuỗi "326.00", cả chuỗi rỗng và cả chữ. Ném
    lỗi ở đây là để một ô dữ liệu lệch giết cả lượt trả lời.
    """

    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip().replace(",", ".")))
    except (TypeError, ValueError):
        return None


def build_spec(*, vehicle_id: str, name: str, specs: Mapping[str, object], price_vnd: object = None) -> VehicleSpec:
    """`VehicleFacts.specs` / `ComparedVehicleView.specs` → `VehicleSpec`.

    Một hàm cho CẢ HAI nguồn vì hai nguồn dùng chung bộ tên cột (cùng
    `adapters/catalog_reader`). Ô xe máy (`range_max_km`) đọc chung khoá tầm
    chạy với ô tô (`range_km`): với câu hỏi "đi xa được không" thì hai cột đó
    là một thứ.
    """

    def first(keys: Sequence[str]) -> int | None:
        for key in keys:
            value = _int(specs.get(key))
            if value is not None:
                return value
        return None

    return VehicleSpec(
        vehicle_id=str(vehicle_id),
        name=name or "",
        seats=first(_SEATS_KEYS),
        range_km=first(_RANGE_KEYS),
        trunk_litres=first(_TRUNK_KEYS),
        price_vnd=_int(price_vnd),
    )


def _has_word(text: str, words: Sequence[str]) -> bool:
    normalized = normalize(text or "")
    return any(word in normalized for word in words)


def customer_need(slots: Mapping[SlotName, SlotValue], *, user_message: str = "") -> CustomerNeed:
    """Slot đã chốt (+ CÂU khách vừa gõ) → nhu cầu để đối chiếu.

    Mục đích là chữ TỰ DO ("đi chơi cùng gia đình", "đi chơi xa"): đọc nó bằng
    `normalize` (bỏ dấu) rồi dò cụm, đúng lối `understand._spoken_vehicle_type`
    đọc "xe máy". Thẻ nhu cầu đóng nói cùng một việc thì cũng tính.

    `user_message` là nguồn THỨ HAI, không phải nguồn dự phòng: lượt prod vòng
    10 ("gia đình tôi có 4 người, tôi muốn sử dụng đi chơi xa") về slot chỉ có
    `seats=4` — LLM đọc câu đó là một lời khai số người. Chỉ đọc slot thì cụm
    "đi chơi xa" biến mất và VF 2 (210 km) được kết luận là "hợp". Chữ khách vừa
    gõ luôn có mặt ở `act`, nên không có lý do gì để mất nó.
    """

    purpose = slots.get(SlotName.PURPOSE)
    purpose_text = purpose if isinstance(purpose, str) and not purpose.startswith("__") else ""
    spoken = f"{purpose_text} {user_message or ''}"
    raw_tags = slots.get(SlotName.HABIT_NEED_TAGS)
    tags = {str(tag).upper() for tag in raw_tags} if isinstance(raw_tags, list) else set()
    return CustomerNeed(
        budget_max_vnd=_int(slots.get(SlotName.BUDGET_MAX_VND)),
        passenger_count=_int(slots.get(SlotName.PASSENGER_COUNT)),
        required_range_km=_int(slots.get(SlotName.REQUIRED_RANGE_KM)),
        long_trip=_has_word(spoken, _LONG_TRIP_WORDS) or bool(tags & _LONG_TRIP_TAGS),
        family=_has_word(spoken, _FAMILY_WORDS) or bool(tags & _FAMILY_TAGS),
        cargo=_has_word(spoken, _CARGO_WORDS),
    )


def need_phrase(need: CustomerNeed) -> str:
    """Nhu cầu đã đọc ra được → một cụm tiếng Việt ngắn, hoặc rỗng.

    Dùng cho câu dẫn bài đề xuất khi khách chưa gõ mục đích bằng chữ: thứ `fit`
    đem ra xếp hạng phải là thứ khách đọc được ở dòng đầu bài.
    """

    parts = [
        phrase
        for flag, phrase in ((need.family, "chở cả nhà"), (need.long_trip, "đi xa"), (need.cargo, "chở nhiều đồ"))
        if flag
    ]
    return ", ".join(parts)


def _seat_check(spec: VehicleSpec, need: CustomerNeed) -> _Check | None:
    if spec.seats is None or need.passenger_count is None:
        return None
    if spec.seats >= need.passenger_count:
        return _Check(MISS_SEATS, True, f"xe {spec.seats} chỗ, đủ cho {need.passenger_count} người nhà mình")
    return _Check(MISS_SEATS, False, f"xe chỉ {spec.seats} chỗ, thiếu so với {need.passenger_count} người cần chở")


def _range_check(spec: VehicleSpec, need: CustomerNeed) -> _Check | None:
    if spec.range_km is None:
        return None
    if need.required_range_km is not None:
        text = f"tầm chạy {spec.range_km} km mỗi lần sạc"
        if spec.range_km >= need.required_range_km:
            return _Check(MISS_RANGE, True, f"{text}, dư cho {need.required_range_km} km anh/chị đi")
        return _Check(MISS_RANGE, False, f"{text}, chưa tới {need.required_range_km} km anh/chị cần")
    if not need.long_trip:
        return None
    if spec.range_km >= LONG_TRIP_RANGE_KM:
        return _Check(MISS_RANGE, True, f"tầm chạy ~{spec.range_km} km/lần sạc, đi xa vẫn thoải mái")
    return _Check(MISS_RANGE, False, f"tầm chạy ~{spec.range_km} km/lần sạc, đi xa phải sạc dọc đường")


def _trunk_check(spec: VehicleSpec, need: CustomerNeed) -> _Check | None:
    if spec.trunk_litres is None or not (need.family or need.long_trip or need.cargo):
        return None
    text = f"khoang hành lý {spec.trunk_litres} lít"
    if spec.trunk_litres >= FAMILY_TRUNK_LITRES:
        return _Check(MISS_TRUNK, True, f"{text}, đủ đồ cho cả nhà")
    return _Check(MISS_TRUNK, False, f"{text}, chở đồ cả nhà đi xa sẽ chật")


def _price_check(spec: VehicleSpec, need: CustomerNeed) -> _Check | None:
    if spec.price_vnd is None or need.budget_max_vnd is None:
        return None
    price = format_number(float(spec.price_vnd), "đ")
    if spec.price_vnd <= need.budget_max_vnd:
        return _Check(MISS_PRICE, True, f"giá từ {price}, nằm trong mức anh/chị dự tính")
    budget = format_number(float(need.budget_max_vnd), "đ")
    return _Check(MISS_PRICE, False, f"giá từ {price}, cao hơn mức {budget} anh/chị dự tính")


def _checks(spec: VehicleSpec, need: CustomerNeed) -> tuple[_Check, ...]:
    found = (_seat_check(spec, need), _range_check(spec, need), _trunk_check(spec, need), _price_check(spec, need))
    return tuple(check for check in found if check is not None)


def _verdict(checks: Sequence[_Check]) -> str:
    misses = [check for check in checks if not check.ok]
    if not checks:
        return FIT_PARTIAL
    if not misses:
        return FIT_YES
    return FIT_PARTIAL if len(misses) < len(checks) else FIT_UNFIT


def _within_budget_tolerance(spec: VehicleSpec, need: CustomerNeed) -> bool:
    """Mẫu thay thế có nằm trong mức ngân sách đã NỚI không.

    Không có số thì coi như hợp lệ: thiếu giá là chuyện của dữ liệu, không phải
    một lý do để giấu chiếc xe đi.
    """

    if need.budget_max_vnd is None or spec.price_vnd is None:
        return True
    return spec.price_vnd <= need.budget_max_vnd * (1 + BUDGET_TOLERANCE)


def _better(
    spec: VehicleSpec, need: CustomerNeed, alternatives: Sequence[VehicleSpec], missed: Sequence[str]
) -> VehicleSpec | None:
    """Mẫu khác VÁ được đúng chỗ đang thiếu, trong mức ngân sách đã nới.

    Không xếp hạng bằng "điểm cao hơn": hai mẫu cùng một điểm mà lệch nhau ở
    đúng tiêu chí khách vừa nêu thì điểm không nói được gì. Cái khách cần là
    một chiếc KHÔNG còn thiếu thứ chiếc kia thiếu.

    Chỗ thiếu là TẦM CHẠY thì trong số các mẫu vá được, chiếc chạy xa nhất mới
    là câu trả lời: khách vừa nói họ đi xa, và một chiếc chỉ vừa đủ ngưỡng sẽ
    kéo họ quay lại đúng câu hỏi này ở chuyến sau. Đổi lại phải chặn giá bằng
    `BUDGET_TOLERANCE` — không thì "chạy xa nhất" luôn là chiếc đắt nhất dải.
    """

    ranked: list[tuple[tuple[int, int, int], VehicleSpec]] = []
    for index, other in enumerate(alternatives):
        if other.vehicle_id == spec.vehicle_id or not _within_budget_tolerance(other, need):
            continue
        checks = _checks(other, need)
        by_code = {check.code: check for check in checks}
        if not all(by_code.get(code) is not None and by_code[code].ok for code in missed):
            continue
        wants_reach = MISS_RANGE in missed
        # Chỗ thiếu là tầm chạy thì GIÁ đã được `_within_budget_tolerance` gác
        # rồi — đếm nó thêm lần nữa ở đây là để chiếc 550 triệu chạy 470 km thua
        # chiếc 500 triệu chạy 326 km, đúng thứ khách vừa nói là không đủ.
        misses = sum(1 for check in checks if not check.ok and not (wants_reach and check.code == MISS_PRICE))
        reach = -(other.range_km or 0) if wants_reach else 0
        ranked.append(((misses, reach, index), other))
    if not ranked:
        return None
    return min(ranked, key=lambda item: item[0])[1]


def assess(spec: VehicleSpec, need: CustomerNeed, alternatives: Sequence[VehicleSpec] = ()) -> FitAssessment:
    """Xe này có hợp nhu cầu không — kết luận ba mức, 1–3 lý do, kèm mẫu thay thế.

    Lý do TRƯỢT đứng trước lý do ĐẠT: khách hỏi "có hợp không" là để nghe chỗ
    không hợp; đọc ba câu khen rồi mới tới chỗ thiếu là giấu câu trả lời.
    """

    checks = _checks(spec, need)
    if not checks:
        return FitAssessment(
            verdict=FIT_PARTIAL,
            reasons=("em chưa có đủ số liệu của xe và nhu cầu để khẳng định chắc chắn",),
        )
    misses = tuple(check for check in checks if not check.ok)
    hits = tuple(check for check in checks if check.ok)
    reasons = tuple(check.reason for check in (*misses, *hits))[:MAX_REASONS]
    missed = tuple(check.code for check in misses)
    verdict = _verdict(checks)
    better = _better(spec, need, alternatives, missed) if verdict != FIT_YES else None
    return FitAssessment(
        verdict=verdict,
        reasons=reasons,
        missed=missed,
        checked=len(checks),
        alternative_id=better.vehicle_id if better is not None else "",
        alternative_name=better.name if better is not None else "",
    )


def _score(spec: VehicleSpec, need: CustomerNeed) -> tuple[int, int, int]:
    """Khoá xếp hạng DUY NHẤT của lượt so sánh: ít trượt trước, rồi nhiều tiêu
    chí đối chiếu được hơn, rồi — khi khách đi xa — tầm chạy dài hơn.

    Tầm chạy chỉ phá thế hoà khi khách THẬT SỰ đi xa. Lượt prod vòng 10: hai mẫu
    cùng đạt hết tiêu chí đếm được nên lõi đọc "bám sát ngang nhau", trong khi
    một chiếc chạy 470 km và chiếc kia 210 km — với người vừa nói "đi chơi xa"
    thì đó không phải là ngang nhau.
    """

    checks = _checks(spec, need)
    misses = sum(1 for check in checks if not check.ok)
    reach = -(spec.range_km or 0) if need.long_trip else 0
    return (misses, misses - len(checks), reach)


def tied(first: VehicleSpec, second: VehicleSpec, need: CustomerNeed) -> bool:
    """Hai mẫu có ngang nhau theo ĐÚNG khoá `compare_fit` đang xếp không.

    Có mặt để `act` không phải chép lại khoá xếp hạng — chép là dựng nguồn sự
    thật thứ hai, và dòng kết luận sẽ nói ngược với thứ tự ngay dưới nó.
    """

    return _score(first, need) == _score(second, need)


def compare_fit(specs: Sequence[VehicleSpec], need: CustomerNeed) -> tuple[tuple[VehicleSpec, FitAssessment], ...]:
    """Xếp vài mẫu theo ĐỘ HỢP với cùng một nhu cầu — mẫu hợp nhất đứng đầu.

    Lượt prod vòng 9: "VF2 với VF3 thì cái nào hợp với nhu cầu của tôi hơn" —
    khách hỏi một câu XẾP HẠNG, còn bảng so sánh chỉ đặt hai cột số cạnh nhau
    và để khách tự xếp. Thứ hạng ở đây trả lời đúng câu đó.

    Ít TRƯỢT trước, rồi nhiều ĐẠT hơn, cuối cùng giữ thứ tự khách nêu. Không
    cộng điểm có trọng số: không có tài liệu nào chốt tiêu chí nào nặng hơn
    tiêu chí nào, mà một bảng trọng số bịa ra thì không giải thích được cho
    khách vì sao mẫu này thắng.
    """

    ranked = []
    for index, spec in enumerate(specs):
        ranked.append(((*_score(spec, need), index), spec, assess(spec, need)))
    ranked.sort(key=lambda item: item[0])
    return tuple((spec, assessment) for _, spec, assessment in ranked)


__all__ = [
    "BUDGET_TOLERANCE",
    "FAMILY_TRUNK_LITRES",
    "LONG_TRIP_RANGE_KM",
    "MAX_REASONS",
    "MISS_PRICE",
    "MISS_RANGE",
    "MISS_SEATS",
    "MISS_TRUNK",
    "CustomerNeed",
    "FitAssessment",
    "VehicleSpec",
    "assess",
    "build_spec",
    "compare_fit",
    "customer_need",
    "need_phrase",
    "tied",
]
