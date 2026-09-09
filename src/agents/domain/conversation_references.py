"""Deterministic resolution of common vehicle references from working memory."""

from __future__ import annotations

import re
from collections.abc import Sequence

_MODEL = re.compile(r"\bVF\s*-?\s*(E?\d+)\b", re.IGNORECASE)
_ELIMINATED = re.compile(
    r"\b(?:loại|loai|bỏ|bo)\s+(?:mẫu\s+|mau\s+|xe\s+)?VF\s*-?\s*(E?\d+)\b",
    re.IGNORECASE,
)
_REMAINING_CUE = re.compile(r"\bmẫu\s+còn\s+lại\b|\bmau\s+con\s+lai\b", re.IGNORECASE)
_SECOND_CUE = re.compile(r"\bmẫu\s+thứ\s+hai\b|\bmau\s+thu\s+hai\b", re.IGNORECASE)
_ELIMINATED_CUE = re.compile(
    r"\bmẫu\s+(?:tôi\s+)?vừa\s+(?:loại|bỏ)\b|"
    r"\bmau\s+(?:toi\s+)?vua\s+(?:loai|bo)\b",
    re.IGNORECASE,
)
_LAST_CUE = re.compile(r"\bmẫu\s+vừa\s+nói\b|\bmau\s+vua\s+noi\b", re.IGNORECASE)
_STATE_ELIMINATED = re.compile(r"Đã loại:\s*([^;.]+)", re.IGNORECASE)
_STATE_ACTIVE = re.compile(r"Đang xem:\s*([^;.]+)", re.IGNORECASE)


#: Khách trỏ vào chiếc ĐANG XEM mà không gọi tên: "xe này", "chiếc này",
#: "mẫu này", "em nó", "con này".
#:
#: Prod 2026-08-27: sau khi xem bản đề xuất, khách gõ *"xe này sạc đầy mất bao
#: lâu"* và nhận về... một bản đề xuất mới. `intents` rỗng, không có tên xe nào
#: để bấu víu, nên lượt rơi xuống nhánh chạy lại chấm điểm. Đây chính là lối
#: "hỏi thêm về xe" trong luồng ba lối, và nó chưa từng chạy được lượt nào.
_CURRENT_VEHICLE_PRONOUN: re.Pattern[str] = re.compile(
    r"\b(?:xe|chiếc|chiec|mẫu|mau|bản|ban|con|em)\s*(?:này|nay|đó|do|ấy|ay)\b",
    re.IGNORECASE,
)


def refers_to_current_vehicle(user_message: str) -> bool:
    """Câu có trỏ vào chiếc đang xem mà không gọi tên không."""

    return _CURRENT_VEHICLE_PRONOUN.search(user_message or "") is not None


def resolve_vehicle_references(
    *, user_message: str, conversation_context: str, raw_mentions: Sequence[str]
) -> list[str]:
    """Resolve a narrow allowlist of references, otherwise preserve raw mentions."""

    models = _ordered_models(conversation_context)
    eliminated = [f"VF {match.upper()}" for match in _ELIMINATED.findall(conversation_context)]
    canonical_eliminated = _models_from_state(_STATE_ELIMINATED, conversation_context)
    canonical_active = _models_from_state(_STATE_ACTIVE, conversation_context)
    if _SECOND_CUE.search(user_message) and len(models) >= 2:
        return [models[1]]
    if _ELIMINATED_CUE.search(user_message) and (canonical_eliminated or eliminated):
        return [(canonical_eliminated or eliminated)[-1]]
    if _REMAINING_CUE.search(user_message):
        if canonical_active:
            return [canonical_active[-1]]
        candidates = [model for model in models if model not in set(eliminated)]
        if len(candidates) == 1:
            return candidates
        if candidates:
            return [candidates[-1]]
    if _LAST_CUE.search(user_message) and models:
        return [models[-1]]
    explicit: list[str] = []
    current_models = set(_ordered_models(user_message))
    for mention in raw_mentions:
        model = _MODEL.search(mention)
        if model is not None:
            canonical = f"VF {model.group(1).upper()}"
            if canonical in current_models:
                explicit.append(mention)
        elif model is None and mention.casefold() in user_message.casefold():
            explicit.append(mention)
    return _canonical_mentions(explicit)


def _ordered_models(text: str) -> list[str]:
    return _canonical_mentions([f"VF {match}" for match in _MODEL.findall(text)])


def _canonical_mentions(mentions: Sequence[str]) -> list[str]:
    ordered: list[str] = []
    for mention in mentions:
        match = _MODEL.search(mention)
        canonical = f"VF {match.group(1).upper()}" if match else mention.strip()
        if canonical and canonical not in ordered:
            ordered.append(canonical)
    return ordered


def _models_from_state(pattern: re.Pattern[str], text: str) -> list[str]:
    match = pattern.search(text)
    return _ordered_models(match.group(1)) if match else []
