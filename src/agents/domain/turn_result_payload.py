"""Versioned, bounded replay payloads for customer-visible turn results."""

from __future__ import annotations

import json
import types
from collections.abc import Mapping
from dataclasses import MISSING, fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar, cast, get_args, get_origin, get_type_hints
from uuid import UUID

from src.agents.contracts import RecommendedVehicleView, TurnResult, VehicleFacts
from src.agents.domain.conversation_memory import TurnOutcome, TurnOutcomeStatus

PAYLOAD_VERSION = 1
MAX_PAYLOAD_BYTES = 256 * 1024
_T = TypeVar("_T")

# Optional display-heavy fields are removed in stable order before core strings
# are shortened. This makes cap behavior deterministic across processes.
_OPTIONAL_FIELDS = (
    "tco_card",
    "nearby_locations",
    "comparison",
    "test_drive_card",
    "vehicle_details",
    "next_step_panel",
    "navigate",
    "quick_replies",
    "options",
)


def serialize_turn_result(result: TurnResult) -> dict[str, object]:
    """Encode all explicit customer-visible fields under 256 KiB."""

    payload: dict[str, object] = {
        "version": PAYLOAD_VERSION,
        "fields": _result_fields(result),
        "payload_truncated": False,
    }
    if _encoded_size(payload) <= MAX_PAYLOAD_BYTES:
        return payload

    values = dict(cast(Mapping[str, object], payload["fields"]))
    for name in _OPTIONAL_FIELDS:
        values.pop(name, None)
        payload["fields"] = values
        payload["payload_truncated"] = True
        if _encoded_size(payload) <= MAX_PAYLOAD_BYTES:
            return payload

    for name in ("lookup_facts", "recommendations"):
        value = values.get(name)
        if isinstance(value, list):
            _fit_list(payload, values, name, value)
            if _encoded_size(payload) <= MAX_PAYLOAD_BYTES:
                return payload

    for name in ("answer", "pending_question", "terminal_reason"):
        value = values.get(name)
        if isinstance(value, str):
            _fit_string(payload, values, name, value)
    return payload


def deserialize_turn_result(payload: object, outcome: TurnOutcome) -> TurnResult:
    """Decode replay payload; malformed payload falls back to typed outcome columns."""

    fallback = _fallback(outcome)
    if not isinstance(payload, Mapping) or payload.get("version") != PAYLOAD_VERSION:
        return fallback
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, Mapping):
        return fallback

    decoded: dict[str, Any] = {}
    annotations = get_type_hints(TurnResult)
    for field in fields(TurnResult):
        raw = raw_fields.get(field.name, MISSING)
        if raw is MISSING:
            decoded[field.name] = getattr(fallback, field.name)
            continue
        try:
            decoded[field.name] = _decode_value(annotations[field.name], raw)
        except (TypeError, ValueError, KeyError):
            decoded[field.name] = getattr(fallback, field.name)
    try:
        return TurnResult(**decoded)
    except (TypeError, ValueError):
        return fallback


def _result_fields(result: TurnResult) -> dict[str, object]:
    """Explicit field matrix; new public fields must be intentionally added here."""

    return {
        "answer": result.answer,
        "pending_question": result.pending_question,
        "terminal_reason": result.terminal_reason,
        "lookup_facts": _json_value(result.lookup_facts),
        "conversation_state": result.conversation_state,
        "options": _json_value(result.options),
        "vehicle_type": result.vehicle_type,
        "awaiting_review": result.awaiting_review,
        "review_id": _json_value(result.review_id),
        "turn_status": result.turn_status,
        "recommendations": _json_value(result.recommendations),
        "test_drive_card": _json_value(result.test_drive_card),
        "vehicle_details": _json_value(result.vehicle_details),
        "next_step_panel": _json_value(result.next_step_panel),
        "navigate": _json_value(result.navigate),
        "quick_replies": _json_value(result.quick_replies),
        "comparison": _json_value(result.comparison),
        "nearby_locations": _json_value(result.nearby_locations),
        "tco_card": _json_value(result.tco_card),
    }


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (UUID, Decimal, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {item.name: _json_value(getattr(value, item.name)) for item in fields(value)}
    raise TypeError(f"unsupported turn result payload value: {type(value).__name__}")


def _decode_items(annotation: Any, items: object) -> list[Any]:
    """Giải mã từng phần tử trong lưới đỡ riêng; phần tử hỏng thì BỎ, không ném.

    Đây là đường CỨU khi payload chính đã hỏng. Một đường cứu tự ném lỗi là không
    cứu được gì: lượt đi ra bằng 500 thay vì bằng phần dữ liệu còn đọc được.
    """

    if not isinstance(items, list | tuple):
        return []
    decoded: list[Any] = []
    for item in items:
        try:
            value = _decode_value(annotation, item)
        except Exception:  # noqa: BLE001 — mọi kiểu hỏng đều chỉ là "bỏ phần tử này"
            continue
        if value is not None:
            decoded.append(value)
    return decoded


def _fallback(outcome: TurnOutcome) -> TurnResult:
    return TurnResult(
        session_id=str(outcome.conversation_id),
        answer=outcome.answer,
        pending_question=outcome.pending_question,
        terminal_reason=outcome.terminal_reason,
        lookup_facts=cast(list[VehicleFacts], _decode_items(VehicleFacts, outcome.lookup_facts)),
        awaiting_review=outcome.status is TurnOutcomeStatus.WAITING_REVIEW,
        review_id=outcome.review_id,
        turn_status=outcome.status.value,
        recommendations=cast(
            list[RecommendedVehicleView],
            _decode_items(RecommendedVehicleView, outcome.recommendations),
        ),
    )


def _decode_value(annotation: Any, value: object) -> object:
    if value is None:
        return None
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (types.UnionType,):
        for candidate in args:
            if candidate is type(None):
                continue
            try:
                return _decode_value(candidate, value)
            except (TypeError, ValueError, KeyError):
                continue
        raise ValueError("malformed union value")
    if origin is list:
        if not isinstance(value, list):
            raise TypeError("expected list")
        return [_decode_value(args[0], item) for item in value]
    if origin is tuple:
        if not isinstance(value, list):
            raise TypeError("expected list")
        item_type = args[0] if args and args[-1] is not Ellipsis else args[0]
        return tuple(_decode_value(item_type, item) for item in value)
    if origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            raise TypeError("expected object")
        return {str(key): _decode_value(args[1], item) for key, item in value.items()}
    if origin is types.UnionType:
        raise ValueError("malformed union value")
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if annotation is UUID:
        return UUID(value) if isinstance(value, str) else (_ for _ in ()).throw(TypeError("expected UUID"))
    if annotation is datetime:
        return (
            datetime.fromisoformat(value)
            if isinstance(value, str)
            else (_ for _ in ()).throw(TypeError("expected datetime"))
        )
    if annotation is Decimal:
        return Decimal(str(value))
    if is_dataclass(annotation):
        if not isinstance(value, Mapping):
            raise TypeError("expected object")
        hints = get_type_hints(annotation)
        kwargs: dict[str, object] = {}
        for item in fields(annotation):
            if item.name in value:
                kwargs[item.name] = _decode_value(hints[item.name], value[item.name])
        return cast(Any, annotation)(**kwargs)
    if annotation is Any or annotation is object:
        return value
    if annotation is bool:
        return value if isinstance(value, bool) else (_ for _ in ()).throw(TypeError("expected bool"))
    if annotation is str:
        return value if isinstance(value, str) else (_ for _ in ()).throw(TypeError("expected str"))
    return annotation(value)


def _encoded_size(payload: Mapping[str, object]) -> int:
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def _fit_string(payload: dict[str, object], values: dict[str, object], name: str, value: str) -> None:
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        values[name] = value[:middle]
        if _encoded_size(payload) <= MAX_PAYLOAD_BYTES:
            low = middle
        else:
            high = middle - 1
    values[name] = value[:low]


def _fit_list(payload: dict[str, object], values: dict[str, object], name: str, value: list[object]) -> None:
    while value and _encoded_size(payload) > MAX_PAYLOAD_BYTES:
        value.pop()
    values[name] = value
