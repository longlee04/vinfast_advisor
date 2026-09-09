"""[FIND_NEARBY_LOCATION] Luật thuần của lượt "tìm địa điểm VinFast gần nhất".

Năm loại địa điểm, một luồng chung: showroom ô tô, showroom xe máy điện, trạm sạc
ô tô, trạm sạc xe máy, tủ đổi pin. Trước đây module này chỉ biết trạm sạc
(`FIND_CHARGING_STATION`); phần đo khoảng cách, lấy vị trí khách và dựng deep
link không đổi một dòng nào khi mở rộng — chỉ có bộ dò loại địa điểm là mới.

Nhận diện TẤT ĐỊNH, không tốn thêm một lần gọi LLM nào ở bước hiểu ý (A4-2) —
cùng cách `COMPARE_VEHICLES` đang làm: prompt trích slot không nhắc tới nhãn này,
`domain/intent_reconciliation.reconcile_intents` gắn nó bằng luật.

Vì sao bộ dò phải RIÊNG chứ không thêm mấy từ khoá vào bảng cũ: chữ "sạc" đã có
mặt trong `_PERSONAL_CRITERION_CUE` (tiêu chí tư vấn: "nhà có chỗ sạc không") và
trong cây slot (`HOME_CHARGING`). Hai câu dưới đây dùng chung một chữ nhưng cần
hai kết cục trái ngược:

    "nhà em không có chỗ sạc, tư vấn xe giúp em"   → ADVISORY (slot sạc tại nhà)
    "gần đây có trạm sạc nào không"                → FIND_NEARBY_LOCATION

Cái phân biệt chúng không phải chữ "sạc" mà là DANH TỪ ĐỊA ĐIỂM ("trạm sạc",
"trụ sạc", "showroom", "tủ đổi pin"). Bộ dò dưới đây bắt đúng danh từ đó và loại
trừ tường minh các cụm nói về sạc tại nhà.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final

from src.agents.domain.pending_slot import PendingSlotRequest
from src.agents.domain.values import Intent


class LocationKind(StrEnum):
    """Năm loại địa điểm khách có thể đi tìm.

    [KHÁC BIỆT] Giá trị ở đây là hợp đồng CÔNG KHAI (API + client), cố ý khác
    chuỗi mà bảng `locations.location_type` đang lưu (`showroom_car`,
    `car_charging_station`, …). Chuỗi trong bảng là di sản của bộ crawl
    (`data-p150/locations/manifest.json`); đổi chúng nghĩa là `UPDATE` 60.861
    hàng và sửa cả trang bản đồ `/locations` lẫn `scripts/seed_locations_data.py`
    đang đọc đúng những chuỗi ấy. Giữ một enum sạch ở domain và ánh xạ sang kho
    lưu trữ là ranh giới mà `adapters/` vốn sinh ra để giữ — xem
    `LOCATION_TYPE_BY_KIND` ngay dưới.
    """

    SHOWROOM_CAR = "SHOWROOM_CAR"
    SHOWROOM_MOTORBIKE = "SHOWROOM_MOTORBIKE"
    CHARGING_STATION_CAR = "CHARGING_STATION_CAR"
    CHARGING_STATION_MOTORBIKE = "CHARGING_STATION_MOTORBIKE"
    BATTERY_SWAP_CABINET = "BATTERY_SWAP_CABINET"
    #: [KHÁC BIỆT] Hai loại XƯỞNG DỊCH VỤ nằm NGOÀI năm loại đặc tả liệt kê.
    #: Thêm vào vì khách gõ "gara ô tô" và bảng `locations` CÓ dữ liệu cho nó —
    #: 89 xưởng ô tô + 68 xưởng đối tác + 8 xưởng xe máy. Đặc tả cho hai hướng xử
    #: lý "gara": (a) map vào `SHOWROOM_CAR`, hoặc (b) trả lời "chưa hỗ trợ".
    #: Điều kiện của cả hai đều KHÔNG đúng ở đây: (a) sai vì dữ liệu phân biệt rõ
    #: showroom bán hàng với xưởng dịch vụ, và chỉ đường cho khách tới nơi bán xe
    #: khi họ cần sửa xe là một câu trả lời sai; (b) sai vì hệ thống có dữ liệu,
    #: nên từ chối là nói dối về chính năng lực của mình.
    #:
    #: Gỡ hai thành viên này khỏi enum là cách hoàn nguyên — không chỗ nào khác
    #: viết cứng tên chúng.
    SERVICE_WORKSHOP_CAR = "SERVICE_WORKSHOP_CAR"
    SERVICE_WORKSHOP_MOTORBIKE = "SERVICE_WORKSHOP_MOTORBIKE"


#: `LocationKind` → các chuỗi `locations.location_type`. Lấy NGUYÊN VĂN từ
#: `data-p150/locations/manifest.json`, không gõ lại theo trí nhớ.
#:
#: Giá trị là TUPLE chứ không một chuỗi: xưởng ô tô nằm ở hai `location_type`
#: khác nhau (`service_car` của VinFast và `service_car_partner` của đối tác), và
#: với khách đi sửa xe thì đó là một loại. Ép 1:1 sẽ giấu mất 68 xưởng đối tác.
LOCATION_TYPE_BY_KIND: Final[dict[LocationKind, tuple[str, ...]]] = {
    LocationKind.SHOWROOM_CAR: ("showroom_car",),
    LocationKind.SHOWROOM_MOTORBIKE: ("showroom_escooter",),
    LocationKind.CHARGING_STATION_CAR: ("car_charging_station",),
    LocationKind.CHARGING_STATION_MOTORBIKE: ("bike_charging_station",),
    LocationKind.BATTERY_SWAP_CABINET: ("battery_swap_station",),
    LocationKind.SERVICE_WORKSHOP_CAR: ("service_car", "service_car_partner"),
    LocationKind.SERVICE_WORKSHOP_MOTORBIKE: ("service_escooter",),
}

KIND_BY_LOCATION_TYPE: Final[dict[str, LocationKind]] = {
    value: kind for kind, values in LOCATION_TYPE_BY_KIND.items() for value in values
}

#: Nhãn tiếng Việt gửi khách. Trùng `locations.category_name` để trang bản đồ và
#: khung chat không gọi cùng một loại bằng hai cái tên.
KIND_LABELS: Final[dict[LocationKind, str]] = {
    LocationKind.SHOWROOM_CAR: "Showroom Ô tô",
    LocationKind.SHOWROOM_MOTORBIKE: "Showroom Xe máy điện",
    LocationKind.CHARGING_STATION_CAR: "Trạm sạc Ô tô điện",
    LocationKind.CHARGING_STATION_MOTORBIKE: "Trạm sạc Xe máy điện",
    LocationKind.BATTERY_SWAP_CABINET: "Tủ đổi pin",
    LocationKind.SERVICE_WORKSHOP_CAR: "Xưởng dịch vụ Ô tô",
    LocationKind.SERVICE_WORKSHOP_MOTORBIKE: "Xưởng dịch vụ Xe máy điện",
}

#: Năm loại đặc tả liệt kê — dùng cho câu hỏi làm rõ và các nút bấm. Xưởng dịch
#: vụ cố ý KHÔNG có mặt: nó nhận diện được khi khách gõ "gara", nhưng không cần
#: chen vào một danh sách năm nút mà đa số khách chỉ dùng ba nút đầu.
PRIMARY_KINDS: Final[tuple[LocationKind, ...]] = (
    LocationKind.SHOWROOM_CAR,
    LocationKind.SHOWROOM_MOTORBIKE,
    LocationKind.CHARGING_STATION_CAR,
    LocationKind.CHARGING_STATION_MOTORBIKE,
    LocationKind.BATTERY_SWAP_CABINET,
)

#: Hai loại có ý nghĩa "sạc". Dùng để quyết định trường `charger_type` có áp dụng
#: không — showroom và tủ đổi pin thì không.
CHARGING_KINDS: Final[tuple[LocationKind, ...]] = (
    LocationKind.CHARGING_STATION_CAR,
    LocationKind.CHARGING_STATION_MOTORBIKE,
)

#: Tên slot của vị trí khách và của LOẠI địa điểm. Cả hai cố ý KHÔNG nằm trong
#: `SlotName` — cùng lý do đã ghi cho `province` ở `domain/pending_slot.py`: cây
#: slot A3-1 là các slot của luồng tư vấn CHỌN XE, còn hai giá trị này chỉ dùng
#: để xếp một danh sách địa điểm theo khoảng cách. Nhét chúng vào đó sẽ kéo
#: `require_complete`, `build_criteria` và Lớp 1 phải hiểu hai khái niệm chúng
#: không dùng.
USER_LOCATION_SLOT: Final[str] = "user_location"
LOCATION_KIND_SLOT: Final[str] = "location_kind"

# ── Bộ dò "đây là câu đi tìm một địa điểm" ────────────────────────────────────
#
# NGUYÊN NHÂN GỐC của bug "tủ đổi pin → câu từ chối chung chung": bản đầu của bộ
# dò này bắt buộc phải có một DẤU HIỆU TÌM KIẾM ("gần", "ở đâu", "tìm") bên cạnh
# danh từ địa điểm. Nhưng cách khách gõ phổ biến nhất lại là một CỤM DANH TỪ TRẦN,
# không động từ và không dấu hiệu nào cả:
#
#     "tủ đổi pin"        → trước: KHÔNG khớp → intent rỗng → OUT_OF_SCOPE
#     "showroom ô tô"     → trước: KHÔNG khớp → intent rỗng → OUT_OF_SCOPE
#     "trụ đổi pin"       → trước: KHÔNG khớp (thiếu cả "trụ" trong danh từ)
#
# Một cụm danh từ trần chỉ tên một loại địa điểm thì KHÔNG có nghĩa nào khác ngoài
# "cho tôi xem cái này ở đâu". Vì vậy dấu hiệu tìm kiếm không còn là điều kiện
# bắt buộc; thay vào đó là ba bộ LOẠI TRỪ tường minh cho đúng ba nghĩa khác mà
# cùng những chữ ấy có thể mang.

#: Danh từ chỉ ĐỊA ĐIỂM sạc/đổi pin. KHÔNG mơ hồ: không tính năng nào khác của
#: bot dùng những cụm này.
#: `chỗ` có dấu thì giữ, `cho` KHÔNG dấu thì bỏ: nó trùng nguyên văn động từ
#: "cho" trong tiếng Việt, và câu "ban quản lý không **cho** sạc dưới hầm" —
#: một ràng buộc tư vấn — bị đọc thành "chỗ sạc". Bỏ sót "cho sac" của khách gõ
#: không dấu là cái giá rẻ hơn nhiều: cụm đó hầu như luôn mang nghĩa động từ.
_STATION_NOUN = re.compile(
    r"\b(?:trạm|tram|trụ|tru|điểm|diem|cột|cot|bốt|bot|chỗ|cây|cay)\s*"
    r"(?:sạc|sac)\b|"
    r"\b(?:trạm|tram|trụ|tru|điểm|diem|tủ|tu|chỗ|cây|cay)\s*"
    r"(?:đổi|doi|thay)\s*pin\b|"
    r"\b(?:đổi|doi|thay)\s*pin\b|"
    r"\bcharging\s*station\b|\bstation\s*sạc\b|\btram\s*sac\b",
    re.IGNORECASE,
)

#: Danh từ chỉ XƯỞNG DỊCH VỤ. Cũng không mơ hồ — "gara" chỉ có một nghĩa.
_WORKSHOP_NOUN = re.compile(
    r"\bgara\b|\bga\s*ra\b|\bgarage\b|\bxưởng\b|\bxuong\b|"
    r"\b(?:trung\s*tâm|trung\s*tam)\s*(?:dịch\s*vụ|dich\s*vu|bảo\s*hành|bao\s*hanh)\b",
    re.IGNORECASE,
)
#: "bảo hành", "bảo dưỡng", "sửa xe" trơ trọi là CHỦ ĐỀ, không phải địa điểm:
#: "VF 7 được bảo hành thế nào?" là câu hỏi chính sách (golden Ngọc, 2026-08-28)
#: mà trước đây bị gắn FIND_NEARBY_LOCATION. Chỉ thành địa điểm khi đi kèm dấu
#: hiệu vị trí/tìm kiếm ("bảo dưỡng ở đâu", "tìm chỗ sửa xe").
_SERVICE_TOPIC_NOUN = re.compile(
    r"\b(?:bảo\s*dưỡng|bao\s*duong|bảo\s*hành|bao\s*hanh|sửa\s*xe|sua\s*xe)\b",
    re.IGNORECASE,
)

#: Danh từ chỉ ĐỊA ĐIỂM bán hàng. MƠ HỒ: "cửa hàng"/"showroom" vừa là một cái kho
#: hàng vừa là một cái địa chỉ — xem `_INVENTORY_QUESTION`.
_SHOWROOM_NOUN = re.compile(
    r"\bshowroom\b|\bsho\s*rum\b|\bđại\s*lý\b|\bdai\s*ly\b|"
    r"\bcửa\s*hàng\b|\bcua\s*hang\b|\bchi\s*nhánh\b|\bchi\s*nhanh\b|"
    r"\bnơi\s*(?:bán|mua)\b|\bnoi\s*(?:ban|mua)\b|\bphòng\s*trưng\s*bày\b",
    re.IGNORECASE,
)

#: Danh từ ĐỊA ĐIỂM chung, không nói rõ loại — "chỗ nào gần tôi", "địa điểm gần
#: nhất". Câu kiểu này vẫn là câu hỏi đường, nhưng phải HỎI LẠI loại.
_GENERIC_PLACE_NOUN = re.compile(
    r"\bđịa\s*điểm\b|\bdia\s*diem\b|\bchỗ\s*nào\b|\bcho\s*nao\b|"
    r"\bchỗ\s*gần\b|\bcho\s*gan\b|\bcơ\s*sở\b|\bco\s*so\b",
    re.IGNORECASE,
)

# ── Ba bộ LOẠI TRỪ ───────────────────────────────────────────────────────────

#: (1) Cụm nói về sạc TẠI NHÀ — khách đang khai một tiêu chí tư vấn
#: (`SlotName.HOME_CHARGING`), không đi tìm địa điểm nào. Bắt buộc phải rộng hơn
#: bộ danh từ ở trên: từ khi "chỗ sạc" được tính là danh từ địa điểm, câu
#: "nhà em không có chỗ sạc" khớp danh từ đó và sẽ bị đọc thành câu hỏi đường.
_HOME_CHARGING = re.compile(
    r"\b(?:sạc|sac)\s*(?:tại|tai|ở|o)\s*nhà\b|"
    r"\b(?:tại|tai|ở|o)\s*nhà\s*(?:có|co)?\s*(?:sạc|sac)\b|"
    r"\b(?:sạc|sac)\s*(?:riêng|rieng)\s*(?:tại|tai|ở|o)?\s*nhà\b|"
    r"\bnhà\b[^.?!]{0,24}?\b(?:chỗ|cho|điểm|diem|trạm|tram|trụ|tru)\s*(?:sạc|sac)\b|"
    r"\bnha\b[^.?!]{0,24}?\b(?:cho|diem|tram|tru)\s*sac\b|"
    r"\b(?:không|khong|chưa|chua)\s*có\s*(?:chỗ|cho|điểm|diem)\s*(?:sạc|sac)\b|"
    r"\bhome\s*charg",
    re.IGNORECASE,
)

#: (2) Câu hỏi THÔNG SỐ về việc sạc — "sạc ở trạm mất bao lâu", "phí sạc bao
#: nhiêu". Có danh từ địa điểm nhưng hỏi một con số, không hỏi một địa chỉ.
_CHARGING_SPEC_QUESTION = re.compile(
    r"\bbao\s*lâu\b|\bbao\s*lau\b|\bmất\s*bao\b|\bmat\s*bao\b|"
    r"\bbao\s*nhiêu\s*(?:phút|giờ|tiếng|tiền|kw)\b|"
    r"\bcông\s*suất\b|\bcong\s*suat\b|\bphí\s*sạc\b|\bphi\s*sac\b|"
    r"\b(?:giá|gia|chi\s*phí|chi\s*phi)\s*(?:sạc|sac)\b",
    re.IGNORECASE,
)

#: (4) Câu XIN TƯ VẤN XE. Danh từ địa điểm ở đây là BỐI CẢNH, không phải thứ
#: khách đi tìm: "Khu tôi trạm sạc thường phải xếp hàng…, tư vấn giúp mẫu ô tô
#: phù hợp" là một lượt `ADVISORY` kể hoàn cảnh, và "ban quản lý không cho sạc
#: dưới hầm; tôi có nên mua ô tô điện không?" cũng vậy.
#:
#: Chỉ loại trừ khi câu vừa xin tư vấn VỪA nói về XE — và vẫn nhường khi có dấu
#: hiệu vị trí mạnh, để "tư vấn giúp em trạm sạc ô tô gần nhất" không bị chặn.
_ADVISORY_REQUEST = re.compile(
    r"\b(?:tư\s*vấn|tu\s*van|gợi\s*ý|goi\s*y|nên\s*mua|nen\s*mua|"
    r"có\s*nên|co\s*nen|phù\s*hợp|phu\s*hop|nên\s*chọn|nen\s*chon|"
    r"chọn\s*xe|chon\s*xe|đáng\s*mua|dang\s*mua)\b",
    re.IGNORECASE,
)
_VEHICLE_NOUN = re.compile(
    r"\bxe\b|\bmẫu\b|\bmau\b|\bô\s*tô\b|\bo\s*to\b|\boto\b|\bmodel\b",
    re.IGNORECASE,
)

#: (3) Câu hỏi DANH MỤC — "cửa hàng có xe nào không", "showroom bán xe gì". Đây
#: là `CATALOG_BROWSE`, và nó dùng chung danh từ với nhánh này. Không loại trừ
#: tường minh thì bộ dò cướp mất đúng câu hỏi của intent kia.
_INVENTORY_QUESTION = re.compile(
    r"\b(?:có|co|bán|ban|còn|con)\b[^.?!]{0,32}?"
    r"\b(?:xe|mẫu|mau|model|loại\s*xe|loai\s*xe)\b|"
    r"\b(?:xe|mẫu|mau)\s*(?:gì|gi|nào|nao)\b|"
    r"\bdanh\s*(?:sách|sach)\s*xe\b",
    re.IGNORECASE,
)

# ── Dấu hiệu định vị ─────────────────────────────────────────────────────────

#: Câu nói thẳng về VỊ TRÍ. Đủ mạnh để một danh từ mơ hồ cũng thành câu hỏi đường.
_STRONG_FIND_CUE = re.compile(
    r"\b(?:gần|gan)\b|\bở\s*đâu\b|\bo\s*dau\b|\bchỗ\s*nào\b|\bcho\s*nao\b|"
    r"\bđịa\s*chỉ\b|\bdia\s*chi\b|\bđịa\s*điểm\b|\bdia\s*diem\b|"
    r"\b(?:tìm|tim|kiếm|kiem)\b|\bquanh\s*(?:đây|day)\b|"
    r"\bkhu\s*vực\b|\bkhu\s*vuc\b|\bchỉ\s*đường\b|\bchi\s*duong\b|"
    r"\bmap\b|\bbản\s*đồ\b|\bban\s*do\b|\bđường\s*đi\b|\bduong\s*di\b|"
    r"\bvị\s*trí\b|\bvi\s*tri\b|\bnơi\s*nào\b|\bnoi\s*nao\b",
    re.IGNORECASE,
)

#: Chỉ hỏi VỊ TRÍ, không kèm động từ "tìm/kiếm". Dùng cho nhánh động từ trần
#: ("sạc ô tô ở đâu") — ở đó "tìm" quá rộng: "tìm xe có sạc nhanh" là câu hỏi
#: danh mục, không phải câu hỏi đường.
_WHERE_CUE = re.compile(
    r"\bở\s*đâu\b|\bo\s*dau\b|\bchỗ\s*nào\b|\bcho\s*nao\b|"
    r"\bđịa\s*chỉ\b|\bdia\s*chi\b|\b(?:gần|gan)\b|"
    r"\bquanh\s*(?:đây|day)\b|\bkhu\s*vực\b|\bkhu\s*vuc\b|"
    r"\bvị\s*trí\b|\bvi\s*tri\b|\bnơi\s*nào\b|\bnoi\s*nao\b",
    re.IGNORECASE,
)

#: Động từ SẠC/ĐỔI PIN trần, không kèm danh từ địa điểm — "sạc ô tô ở đâu",
#: "sac o to o dau". Chỉ thành câu hỏi đường khi đi cùng `_WHERE_CUE`.
_CHARGE_VERB = re.compile(r"\b(?:sạc|sac)\b|\b(?:đổi|doi|thay)\s*pin\b", re.IGNORECASE)


# ── Bộ dò LOẠI địa điểm ───────────────────────────────────────────────────────
#
# [Lớp 2] Khớp theo bảng từ khoá tĩnh, KHÔNG gọi LLM. Trả về một TẬP: "trạm sạc"
# trần là câu xác định về nhóm (cả hai loại trạm sạc) nhưng chưa xác định về
# phương tiện, và trả cả hai vẫn là câu trả lời đúng — hỏi lại ở đó là hỏi một
# thứ khách không quan tâm. Chỉ tập RỖNG mới sinh câu hỏi làm rõ.

_CAR_CUE = re.compile(
    r"\bô\s*tô\b|\bo\s*to\b|\boto\b|\bxe\s*hơi\b|\bxe\s*hoi\b|\b4\s*bánh\b|"
    r"\bvf\s*\d|\bxe\s*con\b|\bcar\b",
    re.IGNORECASE,
)
_MOTORBIKE_CUE = re.compile(
    r"\bxe\s*máy\b|\bxe\s*may\b|\bxe\s*số\b|\bxe\s*so\b|\bmáy\s*điện\b|"
    r"\bmay\s*dien\b|\b2\s*bánh\b|\bmoto\b|\bscooter\b|\bxe\s*ga\b",
    re.IGNORECASE,
)
_BATTERY_SWAP_CUE = re.compile(
    r"\b(?:đổi|doi|thay)\s*pin\b|\btủ\s*pin\b|\btu\s*pin\b|\bswap\b",
    re.IGNORECASE,
)


def is_nearby_location_request(user_message: str) -> bool:
    """Lượt này có phải câu đi TÌM một địa điểm của VinFast không.

    Luật: có DANH TỪ ĐỊA ĐIỂM (hoặc động từ sạc kèm dấu hiệu vị trí), và không
    rơi vào một trong ba nghĩa khác mà cùng những chữ ấy có thể mang.

    Dấu hiệu tìm kiếm KHÔNG bắt buộc. Đó là nguyên nhân gốc của bug đã sửa: cách
    khách gõ phổ biến nhất là một cụm danh từ trần ("tủ đổi pin", "showroom ô
    tô") — không động từ, không dấu hiệu nào — và một cụm như vậy chỉ tên một
    loại địa điểm thì không có nghĩa nào khác ngoài "cho tôi xem cái này ở đâu".

    Bốn loại trừ, theo đúng thứ tự này:

    1. Sạc TẠI NHÀ → tiêu chí tư vấn (`SlotName.HOME_CHARGING`), không phải đường.
    2. Hỏi THÔNG SỐ sạc ("mất bao lâu") → câu hỏi một con số, không phải địa chỉ.
    3. XIN TƯ VẤN XE kèm nói về xe → `ADVISORY`; danh từ địa điểm chỉ là bối cảnh.
    4. Hỏi DANH MỤC ("cửa hàng có xe nào không") → `CATALOG_BROWSE`. Loại trừ này
       chỉ áp cho danh từ MƠ HỒ: "cửa hàng"/"showroom" vừa là kho hàng vừa là địa
       chỉ, còn "trạm sạc"/"gara" thì không — không ai hỏi "có trạm sạc nào
       không" với ý hỏi danh mục xe.
    """

    message = user_message or ""
    if not message.strip():
        return False
    if _HOME_CHARGING.search(message) or _CHARGING_SPEC_QUESTION.search(message):
        return False
    if _ADVISORY_REQUEST.search(message) and _VEHICLE_NOUN.search(message) and not _STRONG_FIND_CUE.search(message):
        return False

    # Danh từ KHÔNG mơ hồ: tự nó đã là câu hỏi đường, không cần dấu hiệu nào.
    if _STATION_NOUN.search(message) or _WORKSHOP_NOUN.search(message):
        return True
    if _SERVICE_TOPIC_NOUN.search(message) and (_WHERE_CUE.search(message) or _STRONG_FIND_CUE.search(message)):
        return True

    # Danh từ MƠ HỒ: nhường cho `CATALOG_BROWSE` khi câu hỏi về xe — TRỪ KHI câu
    # còn nói thẳng về vị trí. "gần đây có showroom xe máy điện nào không" khớp
    # cả hai mẫu, và ở đó "gần đây" là thứ quyết định: khách hỏi chỗ, không hỏi
    # hàng. Thiếu thứ tự ưu tiên này thì mọi câu "gần đây có … nào không" —
    # khung câu tự nhiên nhất của một câu hỏi đường — đều rơi về danh mục.
    if _SHOWROOM_NOUN.search(message) or _GENERIC_PLACE_NOUN.search(message):
        if _STRONG_FIND_CUE.search(message):
            return True
        return not _INVENTORY_QUESTION.search(message)

    # Không có danh từ địa điểm nào: chỉ còn nhánh động từ trần kèm dấu hiệu vị
    # trí ("sạc ô tô ở đâu"). Dùng `_WHERE_CUE` chứ không `_STRONG_FIND_CUE`:
    # "tìm xe có sạc nhanh" là câu hỏi danh mục, và "tìm" nằm trong bộ mạnh.
    return bool(_CHARGE_VERB.search(message)) and _WHERE_CUE.search(message) is not None


def is_charging_station_request(user_message: str) -> bool:
    """[Tương thích ngược] Câu hỏi CHỈ về trạm sạc/đổi pin.

    Giữ lại vì hai lý do, không phải vì ngại xoá: hàm này là hợp đồng mà nhánh
    `/charging-stations/nearest` cũ dựa vào, và nó vẫn diễn đạt một câu hỏi có
    thật (`is_nearby_location_request` rộng hơn — nó nhận cả câu hỏi showroom).
    """

    if not is_nearby_location_request(user_message):
        return False
    kinds = detect_location_kinds(user_message)
    return bool(kinds) and all(kind in CHARGING_KINDS for kind in kinds)


def detect_location_kinds(user_message: str) -> tuple[LocationKind, ...]:
    """Loại địa điểm khách đang nói tới; RỖNG nghĩa là chưa xác định được.

    Rỗng KHÔNG phải lỗi — nó là tín hiệu để hỏi lại một câu làm rõ. Đoán bừa
    "chắc khách tìm trạm sạc ô tô" cho câu "tìm chỗ gần tôi" sẽ trả về một danh
    sách trông rất thuyết phục và sai loại.

    Trả về TẬP chứ không một giá trị: "trạm sạc gần đây" xác định về nhóm nhưng
    chưa xác định về phương tiện, và trả cả hai loại trạm sạc vẫn là câu trả lời
    đúng — hỏi lại ở đó là bắt khách phân loại hộ hệ thống.
    """

    message = user_message or ""
    wants_car = _CAR_CUE.search(message) is not None
    wants_motorbike = _MOTORBIKE_CUE.search(message) is not None
    kinds: list[LocationKind] = []

    def _by_vehicle(car: LocationKind, motorbike: LocationKind) -> None:
        """Chọn theo phương tiện khách nêu; không nêu rõ thì lấy CẢ HAI."""

        if wants_car and not wants_motorbike:
            kinds.append(car)
        elif wants_motorbike and not wants_car:
            kinds.append(motorbike)
        else:
            kinds.extend((car, motorbike))

    # Xưởng dịch vụ xét TRƯỚC: "gara ô tô" cũng khớp `_CAR_CUE`, và nếu để nhánh
    # showroom chạy trước thì khách cần sửa xe được chỉ tới nơi bán xe.
    if _WORKSHOP_NOUN.search(message) or _SERVICE_TOPIC_NOUN.search(message):
        _by_vehicle(LocationKind.SERVICE_WORKSHOP_CAR, LocationKind.SERVICE_WORKSHOP_MOTORBIKE)

    # Tủ đổi pin xét trước trạm sạc: "đổi pin" luôn kèm chữ "pin", và cụm "trạm
    # đổi pin" cũng khớp `_STATION_NOUN`. Không xét trước thì nó bị đọc thành
    # trạm sạc.
    has_swap = _BATTERY_SWAP_CUE.search(message) is not None
    if has_swap:
        kinds.append(LocationKind.BATTERY_SWAP_CABINET)

    if _SHOWROOM_NOUN.search(message):
        _by_vehicle(LocationKind.SHOWROOM_CAR, LocationKind.SHOWROOM_MOTORBIKE)

    if not has_swap and (
        _STATION_NOUN.search(message) or (_CHARGE_VERB.search(message) and _WHERE_CUE.search(message))
    ):
        _by_vehicle(LocationKind.CHARGING_STATION_CAR, LocationKind.CHARGING_STATION_MOTORBIKE)

    # Khử trùng, giữ thứ tự khai báo trong enum để danh sách gửi khách ổn định.
    return tuple(kind for kind in LocationKind if kind in set(kinds))


def location_types_for(kinds: Iterable[LocationKind]) -> tuple[str, ...]:
    """`LocationKind` → các chuỗi `locations.location_type` repository lọc theo."""

    return tuple(value for kind in kinds for value in LOCATION_TYPE_BY_KIND.get(kind, ()))


def kind_of(location_type: str) -> LocationKind | None:
    """Chuỗi kho lưu trữ → `LocationKind`; loại lạ → `None`, không đoán.

    `None` là kết quả HỢP LỆ: bảng `locations` còn giữ năm loại xưởng dịch vụ
    (`service_car`, `service_gsm`, …) không thuộc tính năng này.
    """

    return KIND_BY_LOCATION_TYPE.get(location_type)


def label_of(location_type: str, fallback: str = "") -> str:
    """Nhãn tiếng Việt của một `location_type`; không nhận ra thì dùng `fallback`."""

    kind = kind_of(location_type)
    return KIND_LABELS[kind] if kind is not None else fallback


def charger_type_of(location_type: str) -> str | None:
    """Nhãn loại trạm sạc, hoặc `None` với loại KHÔNG phải trạm sạc.

    [KHÁC BIỆT] Trường này mang LOẠI TRẠM chứ không phải chuẩn sạc AC/DC. Bộ dữ
    liệu thật không có trường nào nói về chuẩn sạc hay số cổng — xem
    `docs/nearby-location-finder.md`. Showroom và tủ đổi pin trả `None` đúng như
    đặc tả yêu cầu: hai loại đó không có khái niệm cổng sạc nào để nói.
    """

    kind = kind_of(location_type)
    if kind is None:
        return None
    if kind is LocationKind.CHARGING_STATION_CAR:
        return "CAR_CHARGER"
    if kind is LocationKind.CHARGING_STATION_MOTORBIKE:
        return "MOTORBIKE_CHARGER"
    # Showroom, tủ đổi pin và xưởng dịch vụ: không có khái niệm cổng sạc nào.
    return None


def quick_replies_for_kinds() -> tuple[tuple[str, str], ...]:
    """Năm nút bấm `(label, value)` cho câu hỏi làm rõ loại địa điểm.

    `value` là chính NHÃN tiếng Việt, không phải mã enum: client gửi lại nó như
    một tin nhắn bình thường qua `POST /agent/turn`, đúng quy ước `QuickReplyView`
    đang giữ — nhờ vậy client chưa dựng nút bấm vẫn dùng được tính năng (khách tự
    gõ "trạm sạc ô tô" cho kết quả y hệt).
    """

    return tuple((KIND_LABELS[kind], KIND_LABELS[kind]) for kind in PRIMARY_KINDS)


# ── Vị trí khách ──────────────────────────────────────────────────────────────

#: Tiền tố khách hay gắn trước một địa danh khi trả lời "anh/chị đang ở đâu".
#:
#: Cố ý KHÔNG có `o` trần và `cho`/`chỗ`: cả hai là ĐẦU của những địa danh có
#: thật khi khách gõ không dấu ("cho lon" → "Chợ Lớn", "o mon" → "Ô Môn"), và cắt
#: chúng đi biến một địa danh đúng thành một chuỗi vô nghĩa ("Lon", "mon") mà
#: geocode chắc chắn trượt. Bỏ sót một tiền tố chỉ làm câu truy vấn dài hơn một
#: chữ — Nominatim vẫn khớp; cắt nhầm thì mất hẳn kết quả.
_LOCATION_PREFIX = re.compile(
    r"^\s*(?:(?:tôi|toi|mình|minh|em|anh|chị|chi)\s+)?"
    r"(?:đang\s+|dang\s+)?"
    r"(?:ở|tại|gần|gan|quanh|khu\s*vực|khu\s*vuc)\s+",
    re.IGNORECASE,
)

#: Câu trả lời KHÔNG mang địa danh nào. Nhận ra chúng để không lưu "không biết"
#: thành một địa chỉ rồi đem đi geocode.
_NON_LOCATION_ANSWER = re.compile(
    r"^\s*(?:không|khong|ko|k|chưa|chua|thôi|thoi|bỏ\s*qua|bo\s*qua|"
    r"không\s*biết|khong\s*biet|kb|no|skip)\s*[.!?]*\s*$",
    re.IGNORECASE,
)

#: Bán kính mặc định và các mức nới. Nới dần thay vì bắn thẳng 50 km: ở nội thành
#: một truy vấn 5 km đã trả về hàng trăm điểm, và tính khoảng cách cho tất cả chỉ
#: để vứt đi phần lớn là lãng phí đúng đường chạy mà p95 ≤ 6s đang đo.
#:
#: `MAX_SEARCH_RADIUS_KM` = 50 KHÔNG phải một con số tự chọn: nó là trần cứng của
#: `src/locations/domain/values.MAX_RADIUS_KM`, và đặt lớn hơn ở đây sẽ nhận
#: `InvalidRadiusError` ngay tại biên module Locations.
SEARCH_RADII_KM: Final[tuple[Decimal, ...]] = (
    Decimal("5"),
    Decimal("15"),
    Decimal("50"),
)
MAX_SEARCH_RADIUS_KM: Final[Decimal] = SEARCH_RADII_KM[-1]

#: Số địa điểm gửi khách. PRD không chốt con số; 5 là trần trên của khoảng 3–5 mà
#: bản mô tả tính năng nêu, và danh sách ngắn hơn thì `results` tự ngắn theo.
DEFAULT_LOCATION_LIMIT: Final[int] = 5


def location_text_from(user_message: str) -> str | None:
    """Địa danh khách vừa gõ, hoặc `None` khi câu không mang địa danh nào.

    Bộ trích của `PendingSlotServiceImpl` cho slot `user_location`. Cắt tiền tố
    ("ở", "gần", "tôi đang ở") vì Nominatim tìm theo tên địa danh, và "gần Cầu
    Giấy" khớp kém hơn hẳn "Cầu Giấy".
    """

    text = " ".join((user_message or "").split())
    if not text or _NON_LOCATION_ANSWER.match(text):
        return None
    stripped = _LOCATION_PREFIX.sub("", text).strip(" ,.!?;:")
    candidate = stripped or text.strip(" ,.!?;:")
    # Một chuỗi toàn chữ số không phải địa danh. Cắt ở đây thay vì để Nominatim
    # trả về một kết quả ngẫu nhiên ở đầu kia thế giới.
    if not candidate or candidate.isdigit():
        return None
    return candidate


def location_kind_from(user_message: str) -> str | None:
    """Bộ trích của `PendingSlotServiceImpl` cho slot `location_kind`.

    Trả chuỗi các mã enum nối bằng dấu phẩy (hoặc `None` khi không nhận ra) vì
    `conversation_sessions.pending_slot_request` lưu JSON phẳng và một câu có thể
    xác định nhiều loại cùng lúc ("showroom" → cả ô tô lẫn xe máy).
    """

    kinds = detect_location_kinds(user_message)
    return ",".join(kind.value for kind in kinds) if kinds else None


def parse_location_kinds(raw: object) -> tuple[LocationKind, ...]:
    """Dựng lại tập loại từ payload đã lưu; giá trị lạ bị bỏ, không raise.

    Cùng lựa chọn với `PendingSlotRequest.from_payload`: một `ValueError` ở đây sẽ
    giết lượt của khách vì một cột dữ liệu cũ.
    """

    if isinstance(raw, LocationKind):
        return (raw,)
    if isinstance(raw, str):
        tokens = [token.strip() for token in raw.split(",")]
    elif isinstance(raw, Sequence):
        tokens = [str(token).strip() for token in raw]
    else:
        return ()
    valid = {kind.value: kind for kind in LocationKind}
    found = {valid[token] for token in tokens if token in valid}
    return tuple(kind for kind in LocationKind if kind in found)


@dataclass(frozen=True, slots=True)
class UserLocation:
    """Toạ độ khách, kèm cách nó được lấy về.

    `source` không phải trang trí: `maps_url` chỉ gắn `origin` khi toạ độ đến từ
    trình duyệt hoặc từ một địa danh khách tự gõ — cả hai đều là thứ khách chủ
    động đưa. Không có nguồn thứ ba (không IP, không hỏi trước khi cần).
    """

    latitude: float
    longitude: float
    source: str = "browser"
    label: str | None = None

    def to_payload(self) -> dict[str, object]:
        """Dạng JSON để lưu vào `conversation_sessions.user_location`."""

        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "source": self.source,
            "label": self.label,
        }

    @classmethod
    def from_payload(cls, payload: object) -> UserLocation | None:
        """Dựng lại từ JSON; payload hỏng → `None` chứ không raise.

        Cùng lựa chọn với `PendingSlotRequest.from_payload`: một `ValueError` ở
        đây sẽ giết lượt của khách vì một cột dữ liệu cũ.
        """

        if not isinstance(payload, dict):
            return None
        latitude, longitude = payload.get("latitude"), payload.get("longitude")
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            return None
        if isinstance(latitude, bool) or isinstance(longitude, bool):
            return None
        if not (-90.0 <= float(latitude) <= 90.0 and -180.0 <= float(longitude) <= 180.0):
            return None
        source = payload.get("source")
        label = payload.get("label")
        return cls(
            latitude=float(latitude),
            longitude=float(longitude),
            source=source if isinstance(source, str) else "browser",
            label=label if isinstance(label, str) else None,
        )


def maps_directions_url(
    *,
    destination_latitude: float,
    destination_longitude: float,
    origin: UserLocation | None = None,
) -> str:
    """Deep link "Chỉ đường" của Google Maps.

    Đây là URL scheme công khai, KHÔNG phải Directions API: không key, không
    quota, không lần gọi mạng nào từ phía ta.

    `origin` được gắn khi đã biết toạ độ khách — chính là lý do đi lấy toạ độ
    trước khi trả kết quả. Thiếu nó, Google Maps phải tự xin quyền vị trí một lần
    nữa trên máy khách, và khách vừa từ chối quyền đó ở trang này thì tuyến đường
    không bao giờ dựng được.
    """

    destination = f"{destination_latitude},{destination_longitude}"
    if origin is None:
        return f"https://www.google.com/maps/dir/?api=1&destination={destination}"
    return (
        f"https://www.google.com/maps/dir/?api=1&origin={origin.latitude},{origin.longitude}&destination={destination}"
    )


def pending_for_user_location(
    *,
    user_message: str,
    kinds: Sequence[LocationKind] = (),
    asked_at: datetime | None = None,
) -> PendingSlotRequest:
    """Bản ghi "đang chờ khách cho biết vị trí".

    Giữ nguyên câu hỏi gốc VÀ loại địa điểm đã chốt trong `partial_form`: lượt
    sau, sau khi có toạ độ, nhánh này phải biết khách đang hỏi showroom hay trạm
    sạc. Không giữ thì câu trả lời "Cầu Giấy" đứng một mình không còn chút thông
    tin nào về loại địa điểm.
    """

    return PendingSlotRequest(
        intent=Intent.FIND_NEARBY_LOCATION.value,
        missing_slot=USER_LOCATION_SLOT,
        partial_form={
            "original_message": user_message,
            LOCATION_KIND_SLOT: ",".join(kind.value for kind in kinds),
        },
        asked_at=asked_at or datetime.now(UTC),
    )


def pending_for_location_kind(*, user_message: str, asked_at: datetime | None = None) -> PendingSlotRequest:
    """Bản ghi "đang chờ khách cho biết LOẠI địa điểm".

    Đứng riêng khỏi `pending_for_user_location` vì hai câu hỏi khác nhau và có
    hai bộ trích khác nhau. Chỉ MỘT bản ghi chờ tồn tại mỗi phiên
    (`conversation_sessions.pending_slot_request`), nên hai câu hỏi này nối tiếp
    nhau chứ không hỏi cùng lúc: chốt loại trước (một cú bấm nút), rồi mới tới vị
    trí (cần quyền trình duyệt).
    """

    return PendingSlotRequest(
        intent=Intent.FIND_NEARBY_LOCATION.value,
        missing_slot=LOCATION_KIND_SLOT,
        partial_form={"original_message": user_message},
        asked_at=asked_at or datetime.now(UTC),
    )


def round_distance_km(distance_km: Decimal | float | None) -> float | None:
    """Khoảng cách làm tròn 1 chữ số thập phân, đúng như hợp đồng gửi client."""

    if distance_km is None:
        return None
    return round(float(distance_km), 1)


def format_distance(distance_km: float | None) -> str:
    """Chuỗi khoảng cách đọc được. Dưới 1 km đổi sang mét: "0.4 km" đọc chậm hơn
    "khoảng 400 m", và đây là con số khách quyết định dựa vào."""

    if distance_km is None:
        return "chưa rõ khoảng cách"
    if distance_km < 1:
        return f"khoảng {int(round(distance_km * 1000, -1))} m"
    return f"{distance_km:.1f} km"


def join_labels(labels: Sequence[str]) -> str:
    """ "A, B và C" — dùng trong câu chữ nói về nhiều loại địa điểm."""

    cleaned = [label.strip() for label in labels if label and label.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return f"{', '.join(cleaned[:-1])} và {cleaned[-1]}"


__all__ = [
    "CHARGING_KINDS",
    "DEFAULT_LOCATION_LIMIT",
    "KIND_BY_LOCATION_TYPE",
    "KIND_LABELS",
    "PRIMARY_KINDS",
    "LOCATION_KIND_SLOT",
    "LOCATION_TYPE_BY_KIND",
    "MAX_SEARCH_RADIUS_KM",
    "SEARCH_RADII_KM",
    "USER_LOCATION_SLOT",
    "LocationKind",
    "UserLocation",
    "charger_type_of",
    "detect_location_kinds",
    "format_distance",
    "is_charging_station_request",
    "is_nearby_location_request",
    "join_labels",
    "kind_of",
    "label_of",
    "location_kind_from",
    "location_text_from",
    "location_types_for",
    "maps_directions_url",
    "parse_location_kinds",
    "pending_for_location_kind",
    "pending_for_user_location",
    "quick_replies_for_kinds",
    "round_distance_km",
]
