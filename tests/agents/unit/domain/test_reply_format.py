"""Bố cục Markdown dùng chung cho MỌI câu trả lời (`domain/reply_format`).

Ba luật ở đây áp cho cả nhánh tra cứu xe, nhánh duyệt danh mục lẫn nhánh giá lăn
bánh, nên chúng được khoá một lần tại nguồn thay vì lặp lại trong test của từng
nhánh.
"""

from __future__ import annotations

from src.agents.domain.reply_format import (
    ReplySection,
    bold,
    field_line,
    join_blocks,
    render_sections,
)


def test_two_or_more_sections_are_numbered() -> None:
    blocks = render_sections(
        [
            ReplySection("Thông số kỹ thuật", (("Kích thước", "3.967 x 1.723 x 1.578 mm"),)),
            ReplySection("Giá bán", value="từ 436.000.000 đồng."),
        ]
    )

    assert blocks == [
        "1. **Thông số kỹ thuật**:\n* **Kích thước**: 3.967 x 1.723 x 1.578 mm",
        "2. **Giá bán**: từ 436.000.000 đồng.",
    ]


def test_a_lone_section_is_not_numbered() -> None:
    """Một mình "1." trên màn hình nói rằng còn mục 2 ở đâu đó — mà không có."""

    blocks = render_sections([ReplySection("Thông số kỹ thuật", (("Kích thước", "3.967 mm"),))])

    assert blocks == ["**Thông số kỹ thuật**:\n* **Kích thước**: 3.967 mm"]


def test_empty_sections_disappear_and_the_numbering_closes_up() -> None:
    """Mục mất hết trường con thì mất luôn tiêu đề, và số thứ tự chạy lại từ đầu."""

    blocks = render_sections(
        [
            ReplySection("Thông số kỹ thuật", ()),
            ReplySection("An toàn", (("Trang bị an toàn", "ABS"),)),
            ReplySection("Ngoại thất", ()),
            ReplySection("Giá bán", value="từ 1.000.000 đồng."),
        ]
    )

    assert [block.split("**")[0] for block in blocks] == ["1. ", "2. "]
    assert "Thông số kỹ thuật" not in "".join(blocks)


def test_a_section_with_no_content_at_all_yields_nothing() -> None:
    assert render_sections([ReplySection("Giá bán")]) == []


def test_field_names_are_always_bold() -> None:
    assert field_line("Số chỗ ngồi", "5") == "* **Số chỗ ngồi**: 5"
    assert bold("Giá bán") == "**Giá bán**"


def test_blocks_are_separated_by_exactly_one_blank_line() -> None:
    """Đây là thứ tầng hiển thị dựa vào để tách đoạn — dồn lại là lỗi gốc."""

    assert join_blocks(["mở đầu", None, "", "kết"]) == "mở đầu\n\nkết"
