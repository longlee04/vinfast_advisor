"""[FIND_NEARBY_LOCATION] Bộ nhận diện phải TỔNG QUÁT, không vá theo log.

Bug đã sửa: khách gõ "tủ đổi pin" / "showroom ô tô" và nhận về câu từ chối chung
chung. Nguyên nhân gốc là bộ dò bắt buộc phải có một dấu hiệu tìm kiếm ("gần",
"ở đâu") bên cạnh danh từ địa điểm — trong khi cách gõ phổ biến nhất lại là một
cụm danh từ trần.

File này cố ý **không** kiểm sáu câu trong log triệu chứng bằng một danh sách
riêng: sáu câu đó chỉ là mẫu, và một bộ test chép đúng chúng sẽ xanh với một bản
vá `if message == "tủ đổi pin"`. Thay vào đó là ba nhóm:

1. **Sinh tổ hợp** — mọi cách gọi × mọi khung câu, kể cả khung RỖNG (cụm danh từ
   trần). Sáu câu trong log nằm trong tập này như những điểm bình thường.
2. **Biến thể thật** — viết tắt, không dấu, câu dài, sai chính tả.
3. **Không được cướp** — câu của `CATALOG_BROWSE` và `ADVISORY` dùng chung từ
   vựng, phải ở nguyên nhánh cũ.
"""

from __future__ import annotations

import pytest

from src.agents.domain.intent_reconciliation import reconcile_intents
from src.agents.domain.nearby_location import (
    LocationKind,
    detect_location_kinds,
    is_nearby_location_request,
)
from src.agents.domain.turn_understanding import reconcile_scope
from src.agents.domain.values import Intent, ScopeLabel

# ── 1. Sinh tổ hợp: cách gọi × khung câu ─────────────────────────────────────

#: Cách khách gọi từng loại. Lấy từ bảng từ vựng nghiệp vụ, cộng các biến thể
#: quan sát được trong log.
PHRASES: dict[LocationKind, tuple[str, ...]] = {
    LocationKind.SHOWROOM_CAR: (
        "showroom ô tô",
        "showroom xe hơi",
        "cửa hàng ô tô VinFast",
        "đại lý ô tô",
        "showroom xe ô tô điện",
    ),
    LocationKind.SHOWROOM_MOTORBIKE: (
        "showroom xe máy điện",
        "cửa hàng xe máy điện",
        "đại lý xe máy điện",
    ),
    LocationKind.CHARGING_STATION_CAR: (
        "trạm sạc ô tô",
        "trụ sạc ô tô điện",
        "chỗ sạc xe hơi điện",
        "điểm sạc ô tô",
    ),
    LocationKind.CHARGING_STATION_MOTORBIKE: (
        "trạm sạc xe máy điện",
        "trụ sạc xe máy",
        "chỗ sạc xe máy điện",
    ),
    LocationKind.BATTERY_SWAP_CABINET: (
        "tủ đổi pin",
        "trụ đổi pin",
        "chỗ đổi pin",
        "trạm đổi pin",
    ),
    LocationKind.SERVICE_WORKSHOP_CAR: (
        "gara ô tô",
        "gara ô tô điện",
        "xưởng dịch vụ ô tô",
    ),
}

#: Khung câu khách hay dùng. `"{}"` là khung RỖNG — cụm danh từ trần, và cũng là
#: chính con bug: nó không mang động từ lẫn dấu hiệu tìm kiếm nào.
FRAMES: tuple[str, ...] = (
    "{}",
    "{} gần nhất",
    "{} gần đây",
    "{} ở đâu",
    "tôi muốn tìm {}",
    "tìm {} giúp tôi",
    "cho tôi địa chỉ {}",
    "gần đây có {} nào không",
    "chỉ đường tới {}",
    "vị trí {}",
    "{} ở khu vực này",
)


def _cases() -> list[tuple[str, LocationKind]]:
    return [(frame.format(phrase), kind) for kind, phrases in PHRASES.items() for phrase in phrases for frame in FRAMES]


@pytest.mark.parametrize(("message", "kind"), _cases())
def test_every_phrase_in_every_frame_is_recognized(message: str, kind: LocationKind) -> None:
    """Mọi cách gọi × mọi khung câu đều phải ra đúng intent và đúng loại."""

    assert is_nearby_location_request(message) is True, message
    intents = reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=[],
    )
    assert intents == [Intent.FIND_NEARBY_LOCATION], message
    assert kind in detect_location_kinds(message), message


# ── 2. Biến thể thật: viết tắt, không dấu, câu dài ───────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        # Không dấu — cách gõ nhanh trên điện thoại.
        "sac o to o dau",
        "doi pin cho toi",
        "tram sac gan nhat",
        "showroom o to gan day",
        # Câu dài, có ngữ cảnh thừa.
        "mình đang ở Cầu Giấy, quanh đây có tủ đổi pin nào không",
        "xe sắp hết pin rồi, trạm sạc ô tô gần nhất ở đâu vậy em",
        "cho anh hỏi đại lý xe máy điện VinFast khu vực Thanh Xuân",
        # Chỉ nêu loại, không nêu phương tiện.
        "trạm sạc",
        "showroom",
        "đổi pin",
        # Hỏi đường tường minh.
        "chỉ đường tới trạm sạc",
        "bản đồ trạm đổi pin",
    ],
)
def test_real_world_variants_are_recognized(message: str) -> None:
    assert is_nearby_location_request(message) is True, message


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("showroom xe máy điện ở đâu", LocationKind.SHOWROOM_MOTORBIKE),
        ("cho tôi địa chỉ trạm sạc xe máy điện gần đây", LocationKind.CHARGING_STATION_MOTORBIKE),
        ("trụ sạc ô tô gần nhất", LocationKind.CHARGING_STATION_CAR),
        ("gần đây có chỗ đổi pin không", LocationKind.BATTERY_SWAP_CABINET),
        ("tìm đại lý xe máy điện", LocationKind.SHOWROOM_MOTORBIKE),
        ("vị trí trạm đổi pin", LocationKind.BATTERY_SWAP_CABINET),
        ("sac o to o dau", LocationKind.CHARGING_STATION_CAR),
        ("doi pin cho toi", LocationKind.BATTERY_SWAP_CABINET),
        ("gara xe máy điện gần đây", LocationKind.SERVICE_WORKSHOP_MOTORBIKE),
    ],
)
def test_kind_is_resolved_for_unseen_phrasings(message: str, expected: LocationKind) -> None:
    assert expected in detect_location_kinds(message), message


def test_typeless_question_still_asks_instead_of_guessing() -> None:
    """Nới bộ dò KHÔNG được biến "tìm chỗ gần tôi" thành một phỏng đoán."""

    assert is_nearby_location_request("tìm chỗ gần tôi") is True
    assert detect_location_kinds("tìm chỗ gần tôi") == ()


# ── 3. Không được cướp intent của nhánh khác ─────────────────────────────────


@pytest.mark.parametrize(
    "message",
    [
        # `CATALOG_BROWSE` — dùng chung danh từ "cửa hàng"/"showroom".
        "cửa hàng có xe nào không",
        "cửa hàng có những xe gì",
        "showroom có xe nào không",
        "showroom bán những mẫu nào",
        "đại lý còn xe VF 3 không",
        # `ADVISORY` — danh từ địa điểm chỉ là bối cảnh của một câu xin tư vấn.
        "nhà em không có chỗ sạc, tư vấn xe giúp em",
        "nhà em có trạm sạc riêng rồi",
        "Tôi ở chung cư, ban quản lý không cho sạc dưới hầm; vậy tôi có nên mua ô tô điện không?",
        "Khu tôi trạm sạc thường phải xếp hàng và hay bị xe khác chiếm chỗ, tư vấn giúp mẫu ô tô phù hợp.",
        "sạc tại nhà được không",
        # Câu hỏi THÔNG SỐ, không phải địa chỉ.
        "xe này sạc ở trạm sạc nhanh mất bao lâu",
        "phí sạc ở trạm là bao nhiêu",
        # Không liên quan.
        "VF 5 giá bao nhiêu",
        "so sánh VF 3 và VF 5",
        "",
    ],
)
def test_other_intents_are_not_stolen(message: str) -> None:
    assert is_nearby_location_request(message) is False, message


def test_catalog_browse_still_reaches_its_own_intent() -> None:
    """Hồi quy trực tiếp: câu danh mục vẫn về `CATALOG_BROWSE`, không rơi sang đây."""

    intents = reconcile_intents(
        user_message="cửa hàng có xe máy điện nào",
        raw_intents=[Intent.CATALOG_BROWSE],
        normalized_slots={},
        vehicle_mentions=[],
    )
    assert Intent.CATALOG_BROWSE in intents
    assert Intent.FIND_NEARBY_LOCATION not in intents


def test_advisory_turn_keeps_its_intent() -> None:
    intents = reconcile_intents(
        user_message="nhà em không có chỗ sạc, tư vấn xe giúp em",
        raw_intents=[Intent.ADVISORY],
        normalized_slots={},
        vehicle_mentions=[],
    )
    assert Intent.FIND_NEARBY_LOCATION not in intents


# ── 4. Cổng phạm vi không được giết lượt đã nhận diện được ───────────────────


@pytest.mark.parametrize(
    "message",
    ["tủ đổi pin", "showroom ô tô", "trụ đổi pin", "tôi muốn tìm gara ô tô"],
)
def test_deterministic_evidence_beats_an_out_of_scope_guess(message: str) -> None:
    """Nguyên nhân gốc THỨ HAI: nhãn OUT_OF_SCOPE của LLM giết lượt trước router.

    Cụm hai chữ không nhắc VinFast rất dễ bị bộ phân loại phạm vi chấm là lạc đề.
    Nhánh này có bằng chứng tất định (một danh từ địa điểm có thật), nên bằng
    chứng phải thắng một phỏng đoán — nếu không, sửa bộ dò intent là vô nghĩa:
    intent gắn đúng mà lượt vẫn chết ở cổng.
    """

    intents = reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=[],
    )
    scope = reconcile_scope(
        raw_scope=ScopeLabel.OUT_OF_SCOPE,
        intents=intents,
        user_message=message,
        vehicle_mentions=[],
    )
    assert scope is ScopeLabel.IN_SCOPE, message


@pytest.mark.parametrize("message", ["mai Hà Nội có mưa không", "tư vấn cổ phiếu giúp tôi", "kể chuyện cười đi"])
def test_genuinely_out_of_scope_turns_are_still_blocked(message: str) -> None:
    """Cửa hậu ở trên phải HẸP: không được nới cổng phạm vi cho lượt nào khác."""

    intents = reconcile_intents(
        user_message=message,
        raw_intents=[],
        normalized_slots={},
        vehicle_mentions=[],
    )
    scope = reconcile_scope(
        raw_scope=ScopeLabel.OUT_OF_SCOPE,
        intents=intents,
        user_message=message,
        vehicle_mentions=[],
    )
    assert scope is ScopeLabel.OUT_OF_SCOPE, message
