"""Chuẩn hoá đầu ra LLM thành slot dùng được — tất định, không I/O (spec mục 5).

Đúng HAI chỗ được phép "đoán" trong lõi v2, và cả hai đều là bảng/regex có sẵn,
không phải LLM: tên xe (`entity_catalog`) và tiền (`budget_parsing`). Mọi trường
còn lại chỉ được cắt khoảng trắng và kiểm kiểu — không khớp thì BỎ, không bịa.

Module này KHÔNG import `understand.py`: chiều phụ thuộc là
`adapter -> understand -> validate -> domain`, một chiều, không vòng.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from src.agents.domain.budget_parsing import parse_budget_range
from src.agents.domain.entity_catalog import build_vehicle_aliases
from src.agents.domain.text_normalization import normalize, squash
from src.agents.domain.values import SlotName, SlotValue, VehicleType

#: Nút bấm frontend gửi lên nguyên chuỗi (`__lichlaithu__|<iso>|<showroom>`).
#: `policy` so khớp NGUYÊN VĂN chuỗi này, `act` là chỗ tách DUY NHẤT (bẫy mục 12)
#: — nên ở đây tuyệt đối không chạm vào nó.
#:
#: Tiền tố là MÃ NÚT ĐẦY ĐỦ, không phải hai dấu gạch dưới: nhận ra nút ≠ tách
#: nút. Với `"__"`, mọi chuỗi khách gõ mở đầu bằng gạch dưới (hoặc một mã nút
#: khác của frontend) đều được trả về nguyên văn như một lựa chọn hợp lệ, rồi
#: `act` mới phát hiện không tách nổi — sai ở tầng khó thấy nhất.
BUTTON_PREFIX = "__lichlaithu__"

#: Trần hợp lý của hai slot số. Ngoài khoảng là LLM đọc nhầm (số điện thoại,
#: năm sản xuất, tiền) — bỏ hẳn còn hơn để `policy` coi là khách đã trả lời.
MAX_SEATS = 9
MAX_DAILY_KM = 1000

#: Cách khách trỏ vào danh sách vừa đề xuất, đã ở dạng `normalize` (không dấu,
#: thường) vì khoá tra bảng này luôn đi qua `normalize` trước. `-1` là "cái cuối".
ORDINAL_WORDS: Mapping[str, int] = {
    "dau": 1,
    "dau tien": 1,
    "mau dau": 1,
    "mau dau tien": 1,
    "cai dau tien": 1,
    "thu nhat": 1,
    "so 1": 1,
    "mau 1": 1,
    "thu hai": 2,
    "cai thu hai": 2,
    "mau hai": 2,
    "mau thu hai": 2,
    "so 2": 2,
    "mau 2": 2,
    "thu ba": 3,
    "cai thu ba": 3,
    "mau ba": 3,
    "mau thu ba": 3,
    "so 3": 3,
    "mau 3": 3,
    "cuoi": -1,
    "cai cuoi": -1,
    "cuoi cung": -1,
    "mau cuoi": -1,
    "cai cuoi cung": -1,
}

#: Danh từ khách hay đặt trước số thứ tự. Bóc đi rồi mới tra bảng — nếu không
#: thì bảng phải liệt kê tích Descartes danh từ × số, và "chiếc thứ 3" vẫn trượt.
_LEADING_NOUNS: frozenset[str] = frozenset({"cai", "mau", "chiec", "xe", "con"})
#: Từ đánh dấu "đây là số thứ tự", bóc sau danh từ.
_ORDINAL_MARKERS: frozenset[str] = frozenset({"thu", "so"})
#: Số đếm viết chữ. `tu`/`bon` cùng là 4; `nhat`/`mot` cùng là 1.
_NUMBER_WORDS: Mapping[str, int] = {
    "nhat": 1,
    "mot": 1,
    "hai": 2,
    "ba": 3,
    "tu": 4,
    "bon": 4,
    "nam": 5,
    "sau": 6,
    "bay": 7,
    "tam": 8,
    "chin": 9,
    "muoi": 10,
}

_VEHICLE_TYPES = frozenset(item.value for item in VehicleType)

#: Tiền tố HÃNG trong tên catalog ("VinFast VF 8 All New"). Khách gần như không
#: bao giờ gõ nó — nên mọi alias phải có cả bản BỎ tiền tố. Cách viết tách rời
#: ("vin fast") cũng nằm đây vì khách gõ cả hai kiểu; `squash` gộp chúng lại.
_BRAND_JOINED = "vinfast"
_BRAND_SPACED = "vin fast"
_BRAND_PREFIXES: tuple[tuple[str, ...], ...] = (tuple(_BRAND_SPACED.split()), (_BRAND_JOINED,))

#: Khoá dòng xe một token phải dài từng này ký tự trở lên. "vf" là tên DÒNG SẢN
#: PHẨM của cả hãng, không phải một mẫu: coi nó là khoá dòng thì "xe vf" trỏ bừa
#: vào một chiếc bất kỳ. "evo", "klara", "amio" thì ngược lại — đúng là tên mẫu.
_MIN_FAMILY_KEY_CHARS = 3

#: Trần cửa sổ token khi quét câu khách. Tên xe dài nhất của catalog thật
#: ("VinFast VF 8 Eco Extended Range") là 7 token kể cả tiền tố hãng.
_MAX_SCAN_TOKENS = 8


def _brand_stripped(display_name: str) -> str:
    """Tên đã chuẩn hoá, BỎ tiền tố hãng. "VinFast VF 8 All New" → "vf 8 all new".

    Không bỏ khi tên chỉ còn mỗi tiền tố: một xe tên đúng "VinFast" (dữ liệu
    rác) không được biến thành chuỗi rỗng rồi nuốt mọi alias về nó.
    """

    tokens = normalize(display_name or "").split()
    for prefix in _BRAND_PREFIXES:
        size = len(prefix)
        if len(tokens) > size and tuple(tokens[:size]) == prefix:
            return " ".join(tokens[size:])
    return " ".join(tokens)


def _alias_forms(*names: str) -> set[str]:
    """Mọi cách gõ của một nhóm tên đồng nghĩa, qua đúng bộ sinh alias của domain.

    `build_vehicle_aliases` lo phần khó (viết liền, số đọc thành chữ); ở đây chỉ
    NẠP THÊM các biến thể tiền tố hãng mà nó không biết là đồng nghĩa với nhau.
    """

    variants = sorted({name for name in (n.strip() for n in names) if name})
    return {alias.alias for alias in build_vehicle_aliases(variants) if alias.alias}


def _name_forms(display_name: str, stripped: str) -> set[str]:
    """Alias của MỘT xe: nguyên văn catalog, bản bỏ hãng, và bản "vin fast" tách rời."""

    if not stripped or stripped == normalize(display_name):
        return _alias_forms(display_name)
    return _alias_forms(display_name, stripped, f"{_BRAND_SPACED} {stripped}")


def _family_forms(key: str) -> set[str]:
    """Alias của một DÒNG xe: "vf 8", "vf8", "vf tam", "vinfast vf 8", "vin fast vf 8"."""

    return _alias_forms(key, f"{_BRAND_JOINED} {key}", f"{_BRAND_SPACED} {key}")


def _usable_family_key(key: str) -> bool:
    tokens = key.split()
    if not tokens:
        return False
    return len(tokens) > 1 or len(key) >= _MIN_FAMILY_KEY_CHARS


def _family_key_by_index(stripped_names: Sequence[str]) -> tuple[str, ...]:
    """Tên (đã bỏ hãng) → khoá DÒNG xe, suy từ CHÍNH danh mục chứ không bảng cứng.

    Hai nhịp, và thứ tự là phần đắt giá:

    1. **Tiền tố chung**: tiền tố dài nhất mà từ hai xe trở lên cùng có
       ("vf 8" của ba bản VF 8, "klara" của Klara Neo + Klara S).
    2. **Từ chỉ BẢN**: token đứng NGAY SAU một tiền tố chung — "all", "eco",
       "plus", "neo", "s". Đây là chỗ danh mục tự khai ra danh sách trim word,
       nên thêm một bản mới vào catalog là bảng này tự dài ra.

    Rồi khoá dòng của MỌI xe = cắt trước từ chỉ bản đầu tiên. Nhịp 2 là thứ giúp
    "VinFast VF 9 Plus" — chỉ có một bản, không tiền tố chung nào — vẫn có khoá
    "vf 9", tức khách gõ "vf9" vẫn ra xe.
    """

    token_lists = [name.split() for name in stripped_names]
    owners: dict[str, set[int]] = {}
    for index, tokens in enumerate(token_lists):
        for size in range(1, len(tokens)):
            owners.setdefault(" ".join(tokens[:size]), set()).add(index)

    trim_words: set[str] = set()
    for index, tokens in enumerate(token_lists):
        for size in range(len(tokens) - 1, 0, -1):
            key = " ".join(tokens[:size])
            if len(owners.get(key, ())) > 1 and _usable_family_key(key):
                trim_words.add(tokens[size])
                break

    keys: list[str] = []
    for tokens in token_lists:
        cut = next((pos for pos, token in enumerate(tokens) if pos > 0 and token in trim_words), len(tokens))
        candidate = " ".join(tokens[:cut])
        keys.append(candidate if _usable_family_key(candidate) else " ".join(tokens))
    return tuple(keys)


@dataclass(frozen=True, slots=True)
class VehicleRef:
    """Một xe trong danh bạ của lượt này: id để hành động, tên để nói và để khớp."""

    vehicle_id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class VehicleDirectory:
    """Danh bạ xe của MỘT lượt: tên → id, và tên + alias để nhét vào prompt.

    Bước 3 dựng nó từ catalog thật; ở đây không có I/O nào, nên test chạy được
    bằng ba dòng dữ liệu.
    """

    refs: tuple[VehicleRef, ...] = ()
    by_alias: Mapping[str, str] = field(default_factory=dict, init=False, compare=False, repr=False)
    by_squash: Mapping[str, str] = field(default_factory=dict, init=False, compare=False, repr=False)
    name_by_id: Mapping[str, str] = field(default_factory=dict, init=False, compare=False, repr=False)
    alias_by_name: Mapping[str, tuple[str, ...]] = field(default_factory=dict, init=False, compare=False, repr=False)
    family_by_alias: Mapping[str, tuple[str, ...]] = field(default_factory=dict, init=False, compare=False, repr=False)
    family_by_squash: Mapping[str, tuple[str, ...]] = field(default_factory=dict, init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        refs = tuple(self.refs)
        object.__setattr__(self, "refs", refs)
        stripped = [_brand_stripped(ref.display_name) for ref in refs]
        by_alias: dict[str, str] = {}
        by_squash: dict[str, str] = {}
        forms: dict[str, tuple[str, ...]] = {}
        forms_by_index: list[tuple[str, ...]] = []
        for index, ref in enumerate(refs):
            # `sorted`: `build_vehicle_aliases` dựng alias qua `set`, thứ tự đổi
            # mỗi tiến trình. Prompt và thứ tự tranh chấp alias phải ổn định.
            names = tuple(sorted(_name_forms(ref.display_name, stripped[index])))
            forms_by_index.append(names)
            forms[ref.display_name] = names
            for form in names:
                by_alias.setdefault(form, ref.vehicle_id)
                by_squash.setdefault(squash(form), ref.vehicle_id)

        family_keys = _family_key_by_index(stripped)
        # Nhóm theo TIỀN TỐ chứ không theo "cùng khoá": "vf 8 eco extended range"
        # có khoá riêng là "vf 8 eco", nhưng nó vẫn là một bản của dòng "vf 8" —
        # gom theo khoá sẽ để nó rơi ra ngoài `family("VF 8")`.
        members: dict[str, tuple[str, ...]] = {}
        for key in family_keys:
            if key in members:
                continue
            prefix = key.split()
            members[key] = tuple(
                refs[index].vehicle_id for index, name in enumerate(stripped) if name.split()[: len(prefix)] == prefix
            )

        family_by_alias: dict[str, tuple[str, ...]] = {}
        family_by_squash: dict[str, tuple[str, ...]] = {}
        for index, ref in enumerate(refs):
            group = members.get(family_keys[index], (ref.vehicle_id,))
            for form in forms_by_index[index]:
                family_by_alias.setdefault(form, group)
                family_by_squash.setdefault(squash(form), group)
        for key, group in members.items():
            target = self._family_target(key, group, stripped, refs)
            for form in sorted(_family_forms(key)):
                # `setdefault`: alias của một BẢN cụ thể luôn thắng alias của dòng.
                by_alias.setdefault(form, target)
                by_squash.setdefault(squash(form), target)
                family_by_alias.setdefault(form, group)
                family_by_squash.setdefault(squash(form), group)

        object.__setattr__(self, "by_alias", by_alias)
        object.__setattr__(self, "by_squash", by_squash)
        object.__setattr__(self, "name_by_id", {ref.vehicle_id: ref.display_name for ref in refs})
        object.__setattr__(self, "alias_by_name", forms)
        object.__setattr__(self, "family_by_alias", family_by_alias)
        object.__setattr__(self, "family_by_squash", family_by_squash)

    @staticmethod
    def _family_target(key: str, group: Sequence[str], stripped: Sequence[str], refs: Sequence[VehicleRef]) -> str:
        """Khách nói tên DÒNG thì trỏ vào bản nào.

        "All New" trước — đó là bản đang bán chính của dòng, và là bản khách nghĩ
        tới khi nói trống không "VF 8". Không có thì bản tên NGẮN NHẤT: tên càng
        ngắn càng ít phụ kiện/pin mở rộng, tức bản gốc của dòng.
        """

        name_by_id = {refs[index].vehicle_id: stripped[index] for index in range(len(refs))}
        preferred = f"{key} all new"
        for vehicle_id in group:
            if name_by_id.get(vehicle_id) == preferred:
                return vehicle_id
        return min(group, key=lambda vehicle_id: (len(name_by_id.get(vehicle_id, "")), name_by_id.get(vehicle_id, "")))

    def resolve(self, mention: str) -> str | None:
        """Một cách khách gõ tên xe → `vehicle_id`. Không khớp → `None`, không đoán.

        Hai vòng, và vòng hai không thừa: catalog ghi "VinFast VF 9 Plus" còn
        khách gõ "vin fast vf9" — cùng một chiếc xe, nhưng khác nhau ở đúng chỗ
        đặt dấu cách. `squash` bỏ hẳn khoảng trắng nên hai chuỗi đó gặp nhau.
        """

        key = normalize(mention or "")
        if not key:
            return None
        found = self.by_alias.get(key)
        return found if found is not None else self.by_squash.get(key.replace(" ", ""))

    def family(self, mention: str) -> tuple[str, ...]:
        """Tên một dòng (hoặc một bản) → id của MỌI bản trong dòng, theo thứ tự catalog.

        `resolve` trả về đúng một chiếc để chọn/hỏi giá; chỗ nào cần cả bộ (so
        sánh, duyệt danh mục) thì đọc ở đây thay vì tự đoán lại từ tên.
        """

        key = normalize(mention or "")
        if not key:
            return ()
        found = self.family_by_alias.get(key)
        return found if found is not None else self.family_by_squash.get(key.replace(" ", ""), ())

    def scan(self, text: str) -> tuple[str, ...]:
        """Câu khách → id các xe được nhắc tên, TẤT ĐỊNH, không qua LLM.

        Cửa sổ token dài trước ngắn sau: "VF 8 Plus Extended Range" phải ra một
        chiếc, không phải dòng "VF 8" rồi bỏ rơi phần đuôi. Từ khoá lấy từ chính
        `by_alias`/`by_squash` của danh bạ này — không có bảng tên xe thứ hai để
        lệch với catalog.
        """

        tokens = normalize(text or "").split()
        if not tokens or not self.by_alias:
            return ()
        found: dict[str, None] = {}
        position = 0
        while position < len(tokens):
            matched = 0
            for size in range(min(_MAX_SCAN_TOKENS, len(tokens) - position), 0, -1):
                vehicle_id = self.resolve(" ".join(tokens[position : position + size]))
                if vehicle_id is not None:
                    found.setdefault(vehicle_id, None)
                    matched = size
                    break
            position += matched or 1
        return tuple(found)

    def name_of(self, vehicle_id: str | None) -> str | None:
        if not vehicle_id:
            return None
        return self.name_by_id.get(vehicle_id)

    def prompt_lines(self, *, max_aliases: int = 6) -> tuple[str, ...]:
        """Khối "danh sách xe" của prompt: tên chuẩn — vài cách viết khác."""

        lines: list[str] = []
        for ref in self.refs:
            canonical = normalize(ref.display_name)
            others = [form for form in self.alias_by_name.get(ref.display_name, ()) if form != canonical]
            shown = others[:max_aliases]
            lines.append(f"{ref.display_name} — {', '.join(shown)}" if shown else ref.display_name)
        return tuple(lines)


def resolve_vehicle_ids(mentions: Iterable[str], directory: VehicleDirectory) -> tuple[str, ...]:
    """Tên xe LLM trả về → id, giữ thứ tự, khử trùng, bỏ tên không khớp."""

    seen: dict[str, None] = {}
    for mention in mentions:
        vehicle_id = directory.resolve(mention)
        if vehicle_id is not None:
            seen.setdefault(vehicle_id, None)
    return tuple(seen)


def budget_slots(budget_text: str | None) -> dict[SlotName, SlotValue]:
    """Câu tiền của khách → tối đa ba slot SỐ NGUYÊN. Không hiểu → không slot nào.

    `int(...)` không thừa: `budget_parsing` tính bằng `Decimal` bên trong, mà
    `SlotValue` không nhận `Decimal` (bẫy mục 12) — đây là chỗ chặn cuối.
    """

    parsed = parse_budget_range(budget_text)
    if parsed.is_empty:
        return {}
    slots: dict[SlotName, SlotValue] = {}
    if parsed.max_vnd is not None:
        slots[SlotName.BUDGET_MAX_VND] = int(parsed.max_vnd)
    if parsed.min_vnd is not None:
        slots[SlotName.BUDGET_MIN_VND] = int(parsed.min_vnd)
    if parsed.stated_vnd is not None:
        slots[SlotName.BUDGET_STATED_VND] = int(parsed.stated_vnd)
    return slots


def vehicle_type_slot(raw: str | None) -> str | None:
    """Chỉ nhận đúng hai giá trị của `VehicleType`; thứ khác → bỏ."""

    candidate = (raw or "").strip().upper().replace(" ", "_")
    return candidate if candidate in _VEHICLE_TYPES else None


def _clean_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _bounded_int(value: object, *, maximum: int) -> int | None:
    """Số nguyên trong [1, maximum]; ngoài khoảng hoặc không đọc được → bỏ hẳn.

    Trần là bắt buộc chứ không phải trang trí: LLM đọc "0912…" thành `seats`
    hay "đi 30000 km một năm" thành `daily_km` thì `policy` coi như khách đã
    trả lời, ngừng hỏi, và scoring nhận một con số vô nghĩa.
    """

    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= maximum else None


def _feature_list(values: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        text = (value or "").strip()
        if text:
            seen.setdefault(text, None)
    return list(seen)


def validate_slots(
    *,
    vehicle_type: str | None = None,
    budget_text: str | None = None,
    purpose: str | None = None,
    seats: int | None = None,
    daily_km: int | None = None,
    features: Iterable[str] = (),
    region: str | None = None,
) -> dict[SlotName, SlotValue]:
    """Slot LLM trả về → mapping khoá `SlotName`, giá trị đúng kiểu `SlotValue`.

    Trường nào không dùng được thì VẮNG MẶT, không bao giờ là `None`: `policy`
    hợp nhất slot bằng "có khoá thì ghi đè", một `None` lọt vào là xoá mất câu
    trả lời cũ của khách.
    """

    slots: dict[SlotName, SlotValue] = {}
    kind = vehicle_type_slot(vehicle_type)
    if kind is not None:
        slots[SlotName.VEHICLE_TYPE] = kind
    slots.update(budget_slots(budget_text))
    purpose_text = _clean_text(purpose)
    if purpose_text is not None:
        slots[SlotName.PURPOSE] = purpose_text
    seat_count = _bounded_int(seats, maximum=MAX_SEATS)
    if seat_count is not None:
        slots[SlotName.PASSENGER_COUNT] = seat_count
    km = _bounded_int(daily_km, maximum=MAX_DAILY_KM)
    if km is not None:
        slots[SlotName.REQUIRED_RANGE_KM] = km
    tags = _feature_list(features)
    if tags:
        slots[SlotName.HABIT_NEED_TAGS] = tags
    province = _clean_text(region)
    if province is not None:
        slots[SlotName.REGISTRATION_PROVINCE] = province
    return slots


def _strip_leading(key: str, words: frozenset[str]) -> str:
    parts = key.split()
    while parts and parts[0] in words:
        parts.pop(0)
    return " ".join(parts)


def _ordinal_index(key: str) -> int | None:
    """Lời trỏ đã `normalize` → số thứ tự 1-based, `-1` là "cái cuối".

    Bảng `ORDINAL_WORDS` chỉ phủ các cách nói trọn vẹn. Sau đó bóc dần
    danh từ ("cái", "mẫu", "chiếc") rồi từ đánh dấu ("thứ", "số") để
    "cái thứ 2", "chiếc thứ 3", "thu 2", "thứ tư" cùng về một con số —
    thay vì đòi bảng liệt kê mọi tổ hợp.
    """

    key = key.strip()
    if not key:
        return None
    if key.isdigit():
        return int(key)
    if key in ORDINAL_WORDS:
        return ORDINAL_WORDS[key]
    reduced = _strip_leading(key, _LEADING_NOUNS)
    if reduced in ORDINAL_WORDS:
        return ORDINAL_WORDS[reduced]
    core = _strip_leading(reduced, _ORDINAL_MARKERS)
    if core in ORDINAL_WORDS:
        return ORDINAL_WORDS[core]
    if core.isdigit():
        return int(core)
    return _NUMBER_WORDS.get(core)


def resolve_choice_ref(
    choice_ref: str | None,
    *,
    recommended_ids: Sequence[str],
    vehicle_ids: Sequence[str] = (),
    directory: VehicleDirectory | None = None,
) -> str | None:
    """Lời trỏ của khách → một `vehicle_id` trong `recommended_ids`, hoặc `None`.

    Thứ tự xét không được đảo:
    1. Chuỗi NÚT giữ nguyên văn (không phải lời khách, `act` mới tách).
    2. Đã là một id đang đề xuất.
    3. Tên xe đã giải được ở `vehicle_ids` và tên đó nằm trong danh sách đề xuất.
    4. Tên xe tra danh bạ.
    5. Số thứ tự / từ thứ tự.
    """

    raw = (choice_ref or "").strip()
    if raw.startswith(BUTTON_PREFIX):
        return raw
    ids = tuple(recommended_ids)
    if raw and raw in ids:
        return raw
    # Chốt chặn PHẢI đứng trước vòng `vehicle_ids`: khách không trỏ vào đâu cả
    # (`choice_ref` trống) mà chỉ tình cờ nhắc tên một xe đang đề xuất thì trước
    # đây hàm này TỰ CHỌN hộ xe đó — tức bịa ra một lượt CHOICE khách chưa hề
    # nói. `policy._pick_vehicle` vẫn đọc `u.vehicle_ids` riêng, nên không mất gì.
    if not raw or not ids:
        return None
    for vehicle_id in vehicle_ids:
        if vehicle_id in ids:
            return vehicle_id
    if directory is not None:
        by_name = directory.resolve(raw)
        if by_name is not None and by_name in ids:
            return by_name
    index = _ordinal_index(normalize(raw))
    if index is None:
        return None
    if index == -1:
        return ids[-1]
    return ids[index - 1] if 1 <= index <= len(ids) else None
