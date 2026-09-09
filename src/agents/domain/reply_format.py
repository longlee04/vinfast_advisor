"""Định dạng Markdown dùng chung cho MỌI câu trả lời gửi khách.

Trước file này, mỗi nơi dựng câu trả lời tự quyết định cách xuống dòng và tự
viết bullet của riêng nó (`- Nhóm: giá trị` ở `catalog_reply`, `- Giá niêm yết:`
ở `pricing_reply`, `1. Ô tô điện — …` ở `catalog_browse`). Hệ quả không phải là
"mỗi chỗ một kiểu cho vui": tầng hiển thị chỉ có MỘT bộ quy tắc render, nên bất
kỳ câu nào lệch khỏi quy tắc đó sẽ bị đổ về một khối chữ liền mạch.

Một quy ước duy nhất, khai ở đây:

    <đoạn mở đầu, không bullet>

    1. **Tên mục lớn**:
    * **Tên trường**: giá trị
    * **Tên trường**: giá trị

    2. **Tên mục lớn**: giá trị gọn trong một dòng

    <đoạn kết + disclaimer>

Ba luật:

1. Tên trường LUÔN bọc `**…**`. Tầng hiển thị (`frontend/src/components/common/
   rich-text.tsx`) render `**…**` thành chữ đậm thật, nên đây là in đậm chứ
   không phải hai dấu sao lọt ra màn hình.
2. Mục lớn CHỈ đánh số khi có từ hai mục. Một mình "1." trên màn hình là một
   danh sách một phần tử — nó nói rằng còn mục 2 ở đâu đó.
3. Các khối cách nhau đúng một dòng trống; các dòng trong cùng một mục cách nhau
   một lần xuống dòng. Đây là thứ tầng hiển thị dựa vào để tách đoạn.

THUẦN Python: không SQLAlchemy/FastAPI/LangGraph/LLM SDK.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

#: Ký tự bullet của một trường con. `*` chứ không `-`: mẫu format chuẩn dùng `*`,
#: và tầng hiển thị chấp nhận cả hai nên đổi qua lại chỉ tạo ra hai kiểu cùng tồn
#: tại trong một cuộc hội thoại.
BULLET: str = "*"


def bold(text: str) -> str:
    """Bọc một nhãn thành chữ đậm Markdown."""

    return f"**{text}**"


def italic(text: str) -> str:
    """Bọc thành chữ nghiêng Markdown — dùng cho phần PHỤ, không phải nội dung.

    Sếp 2026-08-26: dòng ví dụ trong câu hỏi phải "xuống dưới và in nghiêng mờ
    hơn một xíu". Nó là gợi ý CÁCH TRẢ LỜI, không phải một câu hỏi thứ hai —
    nằm cùng dòng với câu hỏi thì mắt đọc nó như một vế phải trả lời nốt.
    """

    return f"*{text}*"


def field_line(label: str, value: str) -> str:
    """Một dòng bullet `* **Tên trường**: giá trị`."""

    return f"{BULLET} {bold(label)}: {value}"


@dataclass(frozen=True, slots=True)
class ReplySection:
    """Một mục lớn: hoặc một danh sách trường con, hoặc một giá trị gọn.

    `value` và `fields` loại trừ nhau. Mục chỉ có đúng một con số (giá bán) mà
    phải xuống dòng thành một bullet đơn độc thì dài hơn mà không rõ hơn.
    """

    title: str
    fields: tuple[tuple[str, str], ...] = ()
    value: str | None = None
    #: Dòng thường (không phải cặp nhãn–giá trị), ví dụ danh sách dòng xe.
    lines: tuple[str, ...] = field(default_factory=tuple)

    def is_empty(self) -> bool:
        return not self.fields and not self.lines and not self.value


def render_sections(sections: Sequence[ReplySection]) -> list[str]:
    """Dựng các khối văn bản của những mục CÓ nội dung, đánh số khi có ≥2 mục.

    Trả về danh sách khối để nơi gọi tự ghép với đoạn mở đầu/đoạn kết của mình —
    hàm này không biết câu trả lời bắt đầu và kết thúc bằng gì.
    """

    present = [section for section in sections if not section.is_empty()]
    numbered = len(present) > 1
    return [_render_section(section, index if numbered else None) for index, section in enumerate(present, start=1)]


def _render_section(section: ReplySection, index: int | None) -> str:
    prefix = f"{index}. " if index is not None else ""
    heading = f"{prefix}{bold(section.title)}"
    if section.value is not None:
        return f"{heading}: {section.value}"
    body = [field_line(label, value) for label, value in section.fields]
    body.extend(f"{BULLET} {line}" for line in section.lines)
    return "\n".join([f"{heading}:", *body])


def join_blocks(blocks: Iterable[str | None]) -> str:
    """Ghép các khối bằng đúng một dòng trống, bỏ khối rỗng."""

    return "\n\n".join(block for block in blocks if block)


__all__ = [
    "BULLET",
    "ReplySection",
    "bold",
    "field_line",
    "italic",
    "join_blocks",
    "render_sections",
]
