"""Nhận diện câu hỏi "còn tính năng nào khác không" sau câu hỏi lượt 2 (T7).

Sếp 2026-08-21: khách hỏi lại kiểu này không nêu tên xe cụ thể nên không khớp
`CATALOG_LOOKUP` (`route_intent.py` yêu cầu `vehicle_mentions`), và không sinh
slot mới nên `route_after_layer1._turn_added_a_slot` cũng không cho quay lại
lượt 2 — khách bị lờ đi, hệ thống đi thẳng tới đề xuất. Mẫu câu này là lối
thoát riêng cho đúng ca đó.
"""

from __future__ import annotations

import re

_FEATURE_WORD = r"(?:tính\s*năng|tinh\s*nang)"
_OTHER_WORD = r"(?:khác|khac)"

#: Khách XIN GỢI Ý tính năng, không nêu tên tính năng nào.
#:
#: Đọc từ `turn_traces` prod 2026-08-26: "tính năng nào phù hợp với anh nhất" bị
#: đóng lượt vì lạc đề. Câu đó không có chữ "khác" nên ba nhánh dưới không khớp,
#: mà nó vẫn dẫn tới đúng một việc: mở danh sách tính năng cho khách xem.
#:
#: Từ khi bỏ bước CHỦ ĐỘNG hỏi tính năng (`routing.route_after_layer1`), đây là
#: đường DUY NHẤT còn lại để khách thấy danh sách — nên nó phải bắt được cả lời
#: xin gợi ý, không chỉ lời xin xem thêm.
_FEATURE_ADVICE = r"(?:phù\s*hợp|phu\s*hop|hợp|hop|nên|nen|tốt|tot|cần|can|hay)"

_WANTS_MORE_FEATURES_PATTERN = re.compile(
    rf"{_FEATURE_WORD}.{{0,10}}(?:nào\s*)?{_OTHER_WORD}|"
    rf"{_OTHER_WORD}.{{0,10}}{_FEATURE_WORD}|"
    rf"(?:còn|con)\s*(?:{_FEATURE_WORD}|gì|gi)\s*(?:nào\s*)?{_OTHER_WORD}|"
    rf"{_FEATURE_WORD}\s*(?:nào|nao|gì|gi)\s*(?:là\s*|la\s*)?{_FEATURE_ADVICE}",
    re.IGNORECASE,
)


def wants_more_features(user_message: str) -> bool:
    """Khách muốn nghe thêm lựa chọn tính năng khác — không phải câu trả lời chọn."""

    return _WANTS_MORE_FEATURES_PATTERN.search(user_message) is not None
