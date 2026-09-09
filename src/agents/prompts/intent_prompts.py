"""Intent field schema shared by slot extraction prompts."""

from __future__ import annotations

from src.agents.domain.values import Intent

INTENT_FIELD_DESCRIPTION: dict[str, object] = {
    "type": "array",
    "items": {"type": "string", "enum": [member.value for member in Intent]},
    "description": (
        "Ý định của lượt này. Thêm ADVISORY khi khách muốn chọn xe, hỏi xe có phù hợp "
        "không, hoặc cung cấp nhu cầu như số người, ngân sách, mục đích, quãng đường hay "
        "điều kiện sạc. Thêm CATALOG_LOOKUP khi khách hỏi giá, thông số, sự khác nhau hoặc "
        "tình trạng của mẫu xe được nêu tên. Thêm CATALOG_BROWSE khi khách hỏi cửa hàng "
        "ĐANG CÓ NHỮNG XE NÀO theo LOẠI xe (xe máy điện, ô tô điện, hoặc 'xe' nói chung) "
        "mà KHÔNG nêu tên mẫu xe cụ thể và KHÔNG nêu tiêu chí cá nhân nào. "
        "Câu vừa cung cấp nhu cầu vừa hỏi đích danh mẫu "
        "xe phải trả cả ADVISORY và CATALOG_LOOKUP. Câu chỉ so sánh mẫu xe không tự trở "
        "thành ADVISORY. Không đủ dấu hiệu thì để danh sách rỗng.\n"
        "Phân biệt ba nhánh — khác nhau ở thứ khách ĐƯA VÀO:\n"
        "- 'các xe máy điện có trong cửa hàng' → CATALOG_BROWSE (tên LOẠI xe, không có "
        "tên mẫu, không có tiêu chí).\n"
        "- 'xe máy điện nào đang bán', 'danh sách xe máy điện', 'cửa hàng có những xe gì', "
        "'có xe nào không', 'show tất cả xe', 'có những mẫu ô tô nào' → CATALOG_BROWSE.\n"
        "- 'gợi ý cho tôi các xe máy điện và ô tô điện có trong cửa hàng' → CATALOG_BROWSE "
        "(hỏi hai LOẠI cùng lúc vẫn là một lượt liệt kê, không tách thành hai yêu cầu).\n"
        "- 'gợi ý xe máy điện cho tôi' → CATALOG_BROWSE khi câu KHÔNG kèm ngân sách hay "
        "nhu cầu nào; chữ 'gợi ý' một mình chưa đủ để thành ADVISORY.\n"
        "- 'VF5 giá bao nhiêu', 'Klara giá bao nhiêu' → CATALOG_LOOKUP (có TÊN MẪU xe cụ "
        "thể, không phải tên loại).\n"
        "- 'VF9 đi', 'VF 9 nhé', hoặc chỉ 'VF9' sau khi xem danh mục → CATALOG_LOOKUP; "
        "'đi'/'nhé' chỉ là từ đệm xác nhận mẫu khách muốn xem, không phải thiếu intent.\n"
        "- 'tất cả các mẫu VF8 hiện tại', 'danh sách các phiên bản Klara đang bán' → "
        "CATALOG_LOOKUP (từ 'tất cả'/'danh sách' không biến TÊN MẪU thành tên loại).\n"
        "- 'tôi đang cân nhắc VF 5 và VF 7 nhưng loại VF 5' → ADVISORY (khách đang "
        "chọn/loại phương án; vẫn ghi nhận cả hai tên mẫu để memory giữ đúng trạng thái).\n"
        "- 'tôi cần xe chở được 5 người, ngân sách 700 triệu' → ADVISORY (có tiêu chí cá "
        "nhân nên phải chọn hộ, không phải liệt kê).\n"
        "- 'xe máy điện nào chạy được 100km' → ADVISORY (đã có tiêu chí lọc).\n"
        "Thêm MORE_FEATURES khi khách VỪA được hỏi quan tâm tính năng nào và "
        "xin xem thêm lựa chọn khác ngoài các tính năng vừa gợi ý, không nêu "
        "tiêu chí cá nhân mới — ví dụ 'còn tính năng nào khác không', 'ngoài "
        "mấy cái đó ra thì sao', 'cho xem hết luôn'. MORE_FEATURES đi kèm intent "
        "khác trong cùng lượt nếu khách vừa hỏi thêm vừa nêu tiêu chí mới."
    ),
}

intent_field_description = INTENT_FIELD_DESCRIPTION
