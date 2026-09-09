"""[A4-3] Relax Layer 1 criteria and ask one narrowing question."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Final, Protocol
from uuid import UUID

from src.agents.contracts import FilterCriteria
from src.agents.domain.feature_discrimination import select_discriminating_features
from src.agents.domain.feature_followup import wants_more_features
from src.agents.domain.slot_mapping import PURPOSE_BUCKET_LABEL, purpose_bucket
from src.agents.domain.values import PurposeBucket, SlotValue, VehicleType
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS, FEATURE_LABELS, askable_for
from src.agents.prompts.reply_variants import feature_question_body


class CandidateTuningLimitError(ValueError):
    """Raised when candidate tuning cannot perform requested operation."""


def _scale_budget(multiplier: Decimal):
    def step(criteria: FilterCriteria) -> FilterCriteria | None:
        if criteria.budget_max_vnd is None:
            return None
        return replace(criteria, budget_max_vnd=criteria.budget_max_vnd * multiplier)

    return step


def _drop_range(criteria: FilterCriteria) -> FilterCriteria | None:
    if criteria.required_range_km is None:
        return None
    return replace(criteria, required_range_km=None)


def _drop_budget(criteria: FilterCriteria) -> FilterCriteria | None:
    if criteria.budget_max_vnd is None:
        return None
    return replace(criteria, budget_max_vnd=None)


_RELAX_LADDER = (
    _scale_budget(Decimal("1.10")),
    _scale_budget(Decimal("1.20")),
    _drop_range,
    _drop_budget,
)
MAX_RELAX_STEPS = len(_RELAX_LADDER)


class _Differentiator(Protocol):
    async def ask(
        self,
        candidate_ids: tuple[UUID, ...],
        *,
        vehicle_type: VehicleType | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: PurposeBucket | None = None,
        force_full_list: bool = False,
    ) -> str | None: ...


class _DifferentiatorSource(Protocol):
    async def discriminating_feature_map(self, vehicle_ids: Sequence[UUID]) -> dict[UUID, dict[str, str]]: ...

    async def active_feature_codes(self, vehicle_type: VehicleType) -> frozenset[str]: ...


MAX_DIFFERENTIATORS_PER_QUESTION = 3

#: Ngưỡng độ dài phần còn lại sau khi cắt tiền tố trùng nhãn. Cắt xong mà chỉ còn
#: vài chữ thì dòng đó mất nghĩa — thà giữ nguyên câu lặp còn hơn.
_MIN_TRIMMED_DESCRIPTION = 30

#: Nhãn tiếng Việt của loại xe cho câu mở lượt 2 (T3 guard: loại xe được SUY
#: chứ không phải khách nói thì câu hỏi phải nêu lại để khách phản đối được —
#: "Với ô tô cho gia đình, ..." chứ không phải "Anh/chị quan tâm...").
_VEHICLE_TYPE_LABEL: Final[Mapping[VehicleType, str]] = {
    VehicleType.CAR: "ô tô",
    VehicleType.ELECTRIC_MOTORBIKE: "xe máy điện",
}


@dataclass(frozen=True, slots=True)
class _FeatureSelection:
    """Kết quả chọn mã tính năng, dùng chung cho `ask()` và `choose()`."""

    codes: tuple[str, ...]
    labels: tuple[str, ...]
    type_label: str | None
    purpose_label: str | None


@dataclass(frozen=True, slots=True)
class DelegatedFeatureChoice:
    """Tính năng agent tự chốt khi khách giao việc, kèm câu nói ra lựa chọn đó.

    `feature_codes` đi vào `feature_mentions` của lượt — đúng đường mà câu trả
    lời của khách vẫn đi, nên `scoring._feature_mention_reasons` cộng điểm y hệt
    như khách tự chọn. `message` là thứ khách đọc: agent chốt gì thì phải nói ra,
    không chốt ngầm.
    """

    feature_codes: tuple[str, ...]
    message: str


def _vietnamese_list(labels: tuple[str, ...]) -> str:
    """Liệt kê tiếng Việt: dấu phẩy giữa, chữ "và" trước mục cuối.

    `" và ".join` cho ba mục ra "a và b và c" — đọc như máy nói, và câu chốt hộ
    khách là câu khách đọc kỹ nhất trong cả luồng.
    """

    if len(labels) <= 1:
        return "".join(labels)
    return f"{', '.join(labels[:-1])} và {labels[-1]}"


def _without_leading_label(label: str, description: str) -> str:
    """Bỏ phần mở đầu của mô tả khi nó LẶP đúng cái nhãn vừa in đậm.

    Sếp 2026-08-26, thấy khi chạy lại câu khách thật từ log:

        - **cảnh báo điểm mù**: Cảnh báo điểm mù nhận biết phương tiện ở khu vực…
        - **kết nối Bluetooth**: Kết nối Bluetooth ghép điện thoại với hệ thống…

    Mô tả trong `feature_definitions` viết như một câu độc lập nên phải tự nêu
    chủ ngữ; ghép sau nhãn thì chủ ngữ đó thành thừa. Cắt ở tầng hiển thị chứ
    KHÔNG sửa dữ liệu — cùng mô tả đó còn dùng cho vector matching, ở đó tên
    tính năng nằm trong chuỗi là có ích.

    Chỉ cắt khi khớp TOÀN BỘ nhãn và phần còn lại vẫn thành câu. Khớp một phần
    ("móc gắn ghế trẻ em ISOFIX" với "Móc ISOFIX cố định…") thì để nguyên: cắt
    nửa vời còn khó đọc hơn lặp.
    """

    remainder = description.strip()
    if not remainder.casefold().startswith(label.casefold()):
        return description
    remainder = remainder[len(label) :].lstrip(" ,:-–—")
    if len(remainder) < _MIN_TRIMMED_DESCRIPTION:
        return description
    return remainder[0].upper() + remainder[1:]


def _with_context(body: str, selection: _FeatureSelection, *, subject: str, subject_capitalized: str) -> str:
    """Ghép tiền tố "Với <loại xe> cho <mục đích>" vào thân câu."""

    type_label = selection.type_label
    purpose_label = selection.purpose_label
    if type_label is not None and purpose_label is not None:
        return f"Với {type_label} cho {purpose_label}, {subject} {body}"
    if type_label is not None:
        return f"Với {type_label}, {subject} {body}"
    if purpose_label is not None:
        return f"Với nhu cầu {purpose_label}, {subject} {body}"
    return f"{subject_capitalized} {body}"


@dataclass(frozen=True, slots=True)
class CatalogDifferentiator:
    """Đổi feature phân biệt của A1-5 thành câu hỏi chọn mở (T7/6A).

    Chỉ đọc để sinh câu hỏi — không đụng vào tập candidate (PRD 8.7.3). Ưu tiên
    feature CHIA được tập ứng viên; không feature nào chia được thì hỏi mở
    toàn bộ allowlist (Sếp 2026-08-21: đủ lượt 1 là lượt 2 luôn hỏi, không còn
    bỏ qua vì catalog thiếu dữ liệu duyệt). Chỉ trả `None` khi allowlist cũng
    rỗng (không biết loại xe/mục đích và candidate không có feature nào).
    """

    catalog: _DifferentiatorSource
    askable: frozenset[str] = frozenset()

    async def ask(
        self,
        candidate_ids: tuple[UUID, ...],
        *,
        vehicle_type: VehicleType | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: PurposeBucket | None = None,
        force_full_list: bool = False,
        seed: str = "",
    ) -> str | None:
        """`force_full_list` (Sếp 2026-08-21): khách hỏi lại "tính năng nào
        khác" — bỏ qua bước chọn feature PHÂN BIỆT ĐƯỢC, liệt kê thẳng toàn bộ
        allowlist. Nếu chỉ đúng một feature phân biệt được (ca thường gặp),
        chọn-theo-phân-biệt sẽ LUÔN trả lại đúng feature đó — không có cách
        nào "khác" để đưa ra nếu vẫn ưu tiên tiêu chí phân biệt.
        """

        selection = await self._select(
            candidate_ids,
            vehicle_type=vehicle_type,
            purpose=purpose,
            purpose_bucket_hint=purpose_bucket_hint,
            force_full_list=force_full_list,
        )
        if selection is None:
            return None
        # Thân câu hỏi MỞ "những tính năng nào" — khách chọn một gợi ý hoặc nêu
        # tính năng khác, không bị ép chọn đúng một.
        #
        # Sếp 2026-08-26: mỗi tính năng MỘT DÒNG kèm giải thích. Bản cũ nối mọi
        # tên bằng chữ "hay" thành một dòng; với allowlist đầy đủ thì ra hai
        # mươi lăm mục trong một câu, không ai đọc nổi. Và một cái tên trần
        # ("Bluetooth") không nói được nó dùng để làm gì.
        descriptions = await self._descriptions_for(selection.codes)
        lines = "\n".join(
            f"- **{label}**: {_without_leading_label(label, descriptions[code])}"
            if code in descriptions
            else f"- **{label}**"
            for code, label in zip(selection.codes, selection.labels, strict=True)
        )
        body = feature_question_body(seed)
        return f"{_with_context(body, selection, subject='anh/chị', subject_capitalized='Anh/chị')}\n{lines}"

    async def _descriptions_for(self, codes: tuple[str, ...]) -> dict[str, str]:
        """Mô tả từ catalog. Nguồn chưa hỗ trợ / DB lỗi → danh sách không có phần
        giải thích, chứ không vỡ cả câu hỏi lượt 2."""

        reader = getattr(self.catalog, "feature_descriptions", None)
        if not callable(reader):
            return {}
        try:
            return await reader(list(codes))
        except Exception:
            return {}

    async def choose(
        self,
        candidate_ids: tuple[UUID, ...],
        *,
        vehicle_type: VehicleType | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: PurposeBucket | None = None,
    ) -> DelegatedFeatureChoice | None:
        """Khách giao việc chọn cho agent → CHỐT tính năng, không hỏi lại.

        Dùng đúng bộ mã mà `ask()` sẽ đưa ra hỏi, chỉ khác chỗ kết: `ask()` để
        ngỏ và chờ lượt sau, còn ở đây không còn ai để chờ — khách vừa nói "em
        chọn giúp anh". Trả `None` khi allowlist rỗng để chỗ gọi rơi về HỎI như
        cũ: một câu chốt rỗng ruột là im lặng nuốt mất lời nhờ của khách.

        `force_full_list` KHÔNG có ở đây. Chốt hộ khách thì lấy đúng tập tính
        năng phân biệt được tập ứng viên, không đọc cả allowlist ra — nghe như
        agent gán cho khách mọi thứ nó biết.
        """

        selection = await self._select(
            candidate_ids,
            vehicle_type=vehicle_type,
            purpose=purpose,
            purpose_bucket_hint=purpose_bucket_hint,
            force_full_list=False,
        )
        if selection is None:
            return None
        body = f"ưu tiên {_vietnamese_list(selection.labels)} ạ."
        return DelegatedFeatureChoice(
            feature_codes=selection.codes,
            message=_with_context(body, selection, subject="em", subject_capitalized="Em"),
        )

    async def _select(
        self,
        candidate_ids: tuple[UUID, ...],
        *,
        vehicle_type: VehicleType | None,
        purpose: SlotValue | None,
        purpose_bucket_hint: PurposeBucket | None,
        force_full_list: bool,
    ) -> _FeatureSelection | None:
        """Chọn mã tính năng + nhãn + nhãn ngữ cảnh. `None` = không có gì để đưa.

        Tách ra từ `ask()` khi thêm `choose()`: hai lối kết khác nhau nhưng phải
        chọn CÙNG một bộ mã. Hai bản chép tay của cùng phép chọn là hai bản sẽ
        lệch nhau — đúng bài học `FEATURE_LABELS` ở `_first_name` dưới đây.
        """

        ids = list(candidate_ids)
        feature_map = await self.catalog.discriminating_feature_map(ids)
        code_map: dict[UUID, frozenset[str]] = {vid: frozenset() for vid in ids}
        for vid, codes in feature_map.items():
            code_map[vid] = frozenset(codes.keys())
        if not code_map:
            return None
        bucket = purpose_bucket_hint if purpose_bucket_hint is not None else purpose_bucket(purpose)
        if self.askable:
            askable = self.askable
        elif vehicle_type is not None:
            try:
                askable = await self.catalog.active_feature_codes(vehicle_type)
            except Exception:
                # DB lỗi giữa lượt: rơi về bảng cứng cũ thay vì vỡ cả câu hỏi
                # lượt 2 — hậu quả sai ở đây chỉ là allowlist hẹp hơn, không
                # phải sai loại xe/sai dữ liệu (T7 mở rộng, Bước 2).
                askable = askable_for(vehicle_type, bucket)
            if not askable:
                askable = askable_for(vehicle_type, bucket)
        else:
            askable = frozenset().union(*code_map.values())
        if force_full_list:
            # Khách chủ động xin xem hết — không cắt ở MAX_DIFFERENTIATORS_PER_
            # QUESTION (cap đó chỉ để câu hỏi MỞ ĐẦU gọn, không áp cho lúc khách
            # đã hỏi thẳng "còn gì khác").
            codes = tuple(sorted(askable))
        else:
            codes = select_discriminating_features(
                candidate_features=code_map,
                askable=askable,
                limit=MAX_DIFFERENTIATORS_PER_QUESTION,
            )
            if not codes:
                # Sếp 2026-08-21: đủ lượt 1 (ngân sách) thì lượt 2 luôn hỏi,
                # không còn điều kiện "phải chia được tập ứng viên" — catalog
                # thiếu dữ liệu duyệt (chưa xe nào có/đủ feature) không phải
                # lý do bỏ hẳn.
                codes = tuple(sorted(askable))[:MAX_DIFFERENTIATORS_PER_QUESTION]
        if not codes:
            return None
        # Mã không có nhãn nào bị LOẠI khỏi cả `codes` lẫn `labels`, không phải
        # chỉ khỏi câu chữ: giữ nó trong `codes` sẽ để nhánh chốt-hộ ghi một mã
        # câm vào `feature_mentions`, và không ai đọc log hiểu nó từ đâu ra.
        labelled = tuple((code, self._first_name(feature_map, code)) for code in codes)
        labelled = tuple((code, label) for code, label in labelled if label)
        if not labelled:
            return None
        return _FeatureSelection(
            codes=tuple(code for code, _ in labelled),
            labels=tuple(label for _, label in labelled),
            type_label=_VEHICLE_TYPE_LABEL.get(vehicle_type) if vehicle_type is not None else None,
            purpose_label=PURPOSE_BUCKET_LABEL.get(bucket),
        )

    def _first_name(self, feature_map: dict[UUID, dict[str, str]], code: str) -> str:
        """Nhãn hiển thị cho `code` — ưu tiên `FEATURE_LABELS` tiếng Việt.

        Bug thật 2026-08-21: trước đây ưu tiên NGƯỢC LẠI (tên catalog trước,
        `FEATURE_LABELS` chỉ dự phòng) — `feature_definitions.name` của
        `ANTI_THEFT`/`BATTERY_REMOVABLE` trong DB đang là tiếng Anh ("Anti
        Theft", "Battery Removable", chỉ `HIGH_PAYLOAD` có sẵn tiếng Việt "Tải
        trọng lớn"), nên câu hỏi lượt 2 lẫn cả tiếng Anh giữa các dòng. Ba mã
        lượt 2 luôn có nhãn tiếng Việt kiểm soát được ở `FEATURE_LABELS`, đáng
        tin hơn tên catalog thô — chỉ rơi về catalog cho mã KHÔNG nằm trong
        allowlist chốt (vd `self.askable` override truyền mã lạ).
        """

        curated = FEATURE_LABELS.get(code) or FEATURE_DISPLAY_LABELS.get(code)
        if curated is not None:
            return curated
        for codes in feature_map.values():
            if code in codes and codes[code].strip():
                return codes[code].replace("?", "").strip()
        # Không có nhãn nào: trả RỖNG, không trả mã. Mã thô mang gạch dưới và
        # chữ số — `synthesis.RAW_STRUCTURED_PATTERN` chặn cả pitch vì chúng, và
        # khách đọc "7_SEATER" thì cũng không hiểu gì hơn. Chỗ gọi lọc bỏ mục rỗng.
        return ""


@dataclass(frozen=True, slots=True)
class CandidateTuningServiceImpl:
    """Apply bounded, non-compounded relax steps and narrow candidates."""

    differentiator: _Differentiator | None = None

    def relax(self, criteria: FilterCriteria, relax_count: int) -> FilterCriteria:
        """Apply the next deterministic relaxation while retaining physical needs."""

        if relax_count < 0 or relax_count >= MAX_RELAX_STEPS:
            raise CandidateTuningLimitError("candidate relax limit reached")
        for step in _RELAX_LADDER[relax_count:]:
            relaxed = step(criteria)
            if relaxed is not None:
                return relaxed
        return criteria

    async def narrow_question(
        self,
        candidate_ids: Sequence[UUID],
        *,
        vehicle_type: VehicleType | str | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: PurposeBucket | str | None = None,
        user_message: str = "",
        force_full_list: bool = False,
        seed: str = "",
    ) -> str | None:
        """Ask differentiator once for non-empty candidates; `None` bỏ lượt 2 (5A)."""
        ids = tuple(candidate_ids)
        if not ids:
            raise CandidateTuningLimitError("cannot narrow empty candidates")
        if self.differentiator is None:
            return None
        try:
            resolved_vehicle_type = VehicleType(vehicle_type) if isinstance(vehicle_type, str) else vehicle_type
        except ValueError:
            resolved_vehicle_type = None
        try:
            resolved_bucket = (
                PurposeBucket(purpose_bucket_hint) if isinstance(purpose_bucket_hint, str) else purpose_bucket_hint
            )
        except ValueError:
            resolved_bucket = None
        return await self.differentiator.ask(
            ids,
            vehicle_type=resolved_vehicle_type,
            purpose=purpose,
            purpose_bucket_hint=resolved_bucket,
            force_full_list=force_full_list or wants_more_features(user_message),
            seed=seed,
        )

    async def delegated_features(
        self,
        candidate_ids: Sequence[UUID],
        *,
        vehicle_type: VehicleType | str | None = None,
        purpose: SlotValue | None = None,
        purpose_bucket_hint: PurposeBucket | str | None = None,
    ) -> DelegatedFeatureChoice | None:
        """Khách giao việc chọn → chốt hộ. `None` để chỗ gọi rơi về HỎI như cũ.

        Cùng khuôn `narrow_question`: quy chuỗi về enum ở đây, tầng dưới chỉ nhận
        kiểu đã chuẩn.
        """

        ids = tuple(candidate_ids)
        if not ids:
            raise CandidateTuningLimitError("cannot narrow empty candidates")
        if self.differentiator is None:
            return None
        try:
            resolved_vehicle_type = VehicleType(vehicle_type) if isinstance(vehicle_type, str) else vehicle_type
        except ValueError:
            resolved_vehicle_type = None
        try:
            resolved_bucket = (
                PurposeBucket(purpose_bucket_hint) if isinstance(purpose_bucket_hint, str) else purpose_bucket_hint
            )
        except ValueError:
            resolved_bucket = None
        return await self.differentiator.choose(
            ids,
            vehicle_type=resolved_vehicle_type,
            purpose=purpose,
            purpose_bucket_hint=resolved_bucket,
        )
