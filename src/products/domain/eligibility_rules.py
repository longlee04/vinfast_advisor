"""Bộ đánh giá `promotions.eligibility_rules` — DSL JSON, TẤT ĐỊNH, không qua LLM (plan Customer 360 §5.5).

Cú pháp: node = {"all": [node…]} | {"any": [node…]} | lá {"field": F, OP: V} với đúng một OP.
`{}` = không điều kiện. Toán tử: eq, in, gte, lte, exists (+ all/any).

Đánh giá 3 trị (Kleene) trên ngữ cảnh của một CƠ HỘI (slot + thông tin khách tự nói):
- lá thiếu field → UNKNOWN(field) → kết quả NEED_INFO, và field thiếu cũng là câu hỏi gợi ý;
- `all`: có FALSE → FALSE; không thì có UNKNOWN → UNKNOWN; không thì TRUE;
- `any`: có TRUE → TRUE; không thì có UNKNOWN → UNKNOWN; không thì FALSE.

Luật không đúng DSL (vd. metadata crawler `{"source_url": …}`) → `INVALID_RULE`: ưu đãi bị
loại khỏi gợi ý và hiện ở /admin/promotions là "Cần dựng luật" — không bao giờ "khớp mọi khách".

THUẦN Python.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final


class Eligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NEED_INFO = "NEED_INFO"
    INELIGIBLE = "INELIGIBLE"
    INVALID_RULE = "INVALID_RULE"


class _Tri(StrEnum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


#: Field hợp lệ và kiểu giá trị. Nguồn: slot hội thoại + insight khách tự nói (plan §5.5).
FIELD_TYPES: Final[dict[str, str]] = {
    "vehicle_type": "enum",
    "vehicle_model": "str",
    "budget_max_vnd": "number",
    "registration_province": "str",
    "purpose_bucket": "enum",
    "home_charging": "bool",
    "passenger_count": "number",
    "payment_method": "enum",
    "trade_in": "enum",
    "current_vehicle_brand": "str",
    "customer_group": "enum",
    "purchase_timeframe": "enum",
}
FIELD_LABELS: Final[dict[str, str]] = {
    "vehicle_type": "Loại xe",
    "vehicle_model": "Mẫu xe",
    "budget_max_vnd": "Ngân sách",
    "registration_province": "Tỉnh đăng ký",
    "purpose_bucket": "Mục đích",
    "home_charging": "Sạc tại nhà",
    "passenger_count": "Số người",
    "payment_method": "Hình thức thanh toán",
    "trade_in": "Đổi xe cũ",
    "current_vehicle_brand": "Hãng xe đang đi",
    "customer_group": "Nhóm khách",
    "purchase_timeframe": "Thời điểm định mua",
}
#: Câu hỏi gợi ý cho TVV khi thiếu field (NEED_INFO) — MẪU CÂU, không qua LLM.
FIELD_QUESTION_HINTS: Final[dict[str, str]] = {
    "vehicle_type": "Anh/chị đang tìm ô tô điện hay xe máy điện ạ?",
    "vehicle_model": "Anh/chị đang quan tâm mẫu xe nào ạ?",
    "budget_max_vnd": "Anh/chị dự kiến ngân sách khoảng bao nhiêu ạ?",
    "registration_province": "Anh/chị dự định đăng ký xe ở tỉnh nào ạ?",
    "purpose_bucket": "Anh/chị dùng xe chủ yếu cho việc gì ạ?",
    "home_charging": "Nhà mình có chỗ sạc xe không ạ?",
    "passenger_count": "Xe thường đi mấy người ạ?",
    "payment_method": "Anh/chị định trả thẳng hay trả góp ạ?",
    "trade_in": "Anh/chị có muốn đổi xe cũ khi mua xe mới không ạ?",
    "current_vehicle_brand": "Hiện anh/chị đang đi xe hãng nào ạ?",
    "customer_group": "Anh/chị có thuộc nhóm được ưu đãi riêng (công an/quân đội, VNPost, hội viên VinClub) không ạ?",
    "purchase_timeframe": "Anh/chị dự định mua xe trong khoảng thời gian nào ạ?",
}
OPERATORS: Final[frozenset[str]] = frozenset({"eq", "in", "gte", "lte", "exists"})


class RuleValidationError(ValueError):
    def __init__(self, errors: Sequence[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = tuple(errors)


@dataclass(frozen=True, slots=True)
class EligibilityResult:
    status: Eligibility
    reasons: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()

    @property
    def question_hints(self) -> tuple[str, ...]:
        return tuple(FIELD_QUESTION_HINTS[name] for name in self.missing_fields if name in FIELD_QUESTION_HINTS)


@dataclass(slots=True)
class _Outcome:
    value: _Tri
    reasons: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def validate_rules(rules: Any, path: str = "$") -> list[str]:
    """Danh sách lỗi cú pháp (rỗng = hợp lệ). Admin lưu luật sai → 422 với đúng các lỗi này."""

    if not isinstance(rules, Mapping):
        return [f"{path}: phải là object"]
    if not rules:
        return []
    keys = set(rules)
    if keys & {"all", "any"}:
        if len(keys) != 1:
            return [f"{path}: node all/any không được có khoá khác"]
        key = next(iter(keys))
        children = rules[key]
        if not isinstance(children, list) or not children:
            return [f"{path}.{key}: phải là danh sách không rỗng"]
        errors: list[str] = []
        for index, child in enumerate(children):
            if not isinstance(child, Mapping) or not child:
                errors.append(f"{path}.{key}[{index}]: phải là node không rỗng")
            else:
                errors.extend(validate_rules(child, f"{path}.{key}[{index}]"))
        return errors
    if "field" not in keys:
        return [f"{path}: thiếu 'field' hoặc 'all'/'any' (khoá: {', '.join(sorted(keys))})"]
    name = rules["field"]
    if name not in FIELD_TYPES:
        return [f"{path}: UNKNOWN_FIELD:{name}"]
    operators = keys - {"field"}
    if len(operators) != 1 or not operators <= OPERATORS:
        return [f"{path}: cần đúng một toán tử trong {sorted(OPERATORS)}"]
    operator = next(iter(operators))
    operand = rules[operator]
    kind = FIELD_TYPES[name]
    if operator in {"gte", "lte"} and (
        kind != "number" or isinstance(operand, bool) or not isinstance(operand, int | float)
    ):
        return [f"{path}: {operator} chỉ dùng cho field số"]
    if operator == "in" and (not isinstance(operand, list) or not operand):
        return [f"{path}: 'in' cần danh sách không rỗng"]
    if operator == "exists" and not isinstance(operand, bool):
        return [f"{path}: 'exists' cần true/false"]
    return []


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value)
    return value


def _present(value: Any) -> bool:
    return value not in (None, "", [], "__declined__")


def _leaf(node: Mapping[str, Any], context: Mapping[str, Any]) -> _Outcome:
    name = str(node["field"])
    label = FIELD_LABELS.get(name, name)
    operator = next(key for key in node if key != "field")
    operand = node[operator]
    value = context.get(name)
    if operator == "exists":
        if _present(value):
            return _Outcome(
                _Tri.TRUE if operand else _Tri.FALSE,
                [f"{label}: đã có"],
                failed=[] if operand else [f"{label} phải để trống"],
            )
        return _Outcome(_Tri.TRUE) if not operand else _Outcome(_Tri.UNKNOWN, missing=[name])
    if not _present(value):
        return _Outcome(_Tri.UNKNOWN, missing=[name])
    if operator == "eq":
        ok = _norm(value) == _norm(operand)
        text = f"{label} = {operand}"
    elif operator == "in":
        ok = _norm(value) in {_norm(item) for item in operand}
        text = f"{label} {value} thuộc {{{', '.join(str(item) for item in operand)}}}"
    else:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return _Outcome(_Tri.FALSE, failed=[f"{label} không phải số"])
        ok = number >= float(operand) if operator == "gte" else number <= float(operand)
        text = f"{label} {'≥' if operator == 'gte' else '≤'} {operand:,}".replace(",", ".")
    return _Outcome(_Tri.TRUE, [text]) if ok else _Outcome(_Tri.FALSE, failed=[f"Không đạt: {text}"])


def _eval(node: Mapping[str, Any], context: Mapping[str, Any]) -> _Outcome:
    if "all" in node or "any" in node:
        is_all = "all" in node
        children = [_eval(child, context) for child in node["all" if is_all else "any"]]
        values = [child.value for child in children]
        decisive = _Tri.FALSE if is_all else _Tri.TRUE
        if decisive in values:
            winners = [child for child in children if child.value is decisive]
            return _Outcome(
                decisive,
                reasons=[reason for child in winners for reason in child.reasons],
                failed=[reason for child in winners for reason in child.failed],
            )
        if _Tri.UNKNOWN in values:
            return _Outcome(
                _Tri.UNKNOWN,
                reasons=[reason for child in children for reason in child.reasons],
                missing=[name for child in children for name in child.missing],
            )
        return _Outcome(
            _Tri.TRUE if is_all else _Tri.FALSE,
            reasons=[reason for child in children for reason in child.reasons],
            failed=[reason for child in children for reason in child.failed],
        )
    return _leaf(node, context)


def evaluate(rules: Mapping[str, Any] | None, context: Mapping[str, Any]) -> EligibilityResult:
    """Kết quả cho MỘT ưu đãi trên ngữ cảnh của MỘT cơ hội."""

    if not rules:
        return EligibilityResult(Eligibility.ELIGIBLE, reasons=("Không có điều kiện",))
    if validate_rules(rules):
        return EligibilityResult(Eligibility.INVALID_RULE)
    outcome = _eval(rules, context)
    if outcome.value is _Tri.TRUE:
        return EligibilityResult(Eligibility.ELIGIBLE, reasons=tuple(outcome.reasons))
    if outcome.value is _Tri.UNKNOWN:
        return EligibilityResult(
            Eligibility.NEED_INFO,
            reasons=tuple(outcome.reasons),
            missing_fields=tuple(dict.fromkeys(outcome.missing)),
        )
    return EligibilityResult(Eligibility.INELIGIBLE, failed=tuple(outcome.failed[:1]))


__all__ = [
    "FIELD_QUESTION_HINTS",
    "FIELD_TYPES",
    "Eligibility",
    "EligibilityResult",
    "RuleValidationError",
    "evaluate",
    "validate_rules",
]
