"""Nạp PERSONA PROMPT của Vivi (`vivi_persona.md`) và điền ngữ cảnh vào chỗ trống.

Prompt nằm trong file `.md` riêng để người viết nội dung sửa giọng mà không đụng
code. Chỗ trống dùng cú pháp `{ten}` nhưng được điền bằng `str.replace` chứ
không phải `str.format`: chữ khách/tên xe có thể chứa `{`/`}` và `format` sẽ nổ.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Final

PERSONA_PATH: Final = Path(__file__).with_name("vivi_persona.md")
#: Chữ điền khi thiếu dữ liệu — nói rõ là CHƯA CÓ, để model không tự bịa vào chỗ trống.
UNKNOWN: Final = "chưa có"


@lru_cache(maxsize=1)
def load_persona_template() -> str:
    return PERSONA_PATH.read_text(encoding="utf-8")


def render_persona_prompt(
    *,
    active_vehicle: str | None,
    last_bot_question: str,
    filled_slots: Mapping[str, str],
    vehicle_facts: Mapping[str, str],
) -> str:
    slots_text = "; ".join(f"{key}: {value}" for key, value in filled_slots.items()) or UNKNOWN
    facts_text = "; ".join(f"{key}: {value}" for key, value in vehicle_facts.items()) or UNKNOWN
    values = {
        "{active_vehicle}": active_vehicle or UNKNOWN,
        "{last_bot_question}": last_bot_question or UNKNOWN,
        "{filled_slots}": slots_text,
        "{vehicle_facts}": facts_text,
    }
    text = load_persona_template()
    for placeholder, value in values.items():
        text = text.replace(placeholder, value)
    return text


__all__ = ["PERSONA_PATH", "load_persona_template", "render_persona_prompt"]
