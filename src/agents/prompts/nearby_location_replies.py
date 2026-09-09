"""[FIND_NEARBY_LOCATION] Câu chữ tất định của nhánh tìm địa điểm.

Tách khỏi service cùng lý do `prompts/comparison_replies.py` đã tách: câu gửi
khách là thứ hay được sửa nhất và bởi người ít đọc code nhất. Để nó nằm cạnh
logic thì mỗi lần đổi một dấu phẩy là một lần chạm vào file quyết định nghiệp vụ.

Các câu ở đây là câu DỰ PHÒNG và câu HỎI. Câu dẫn cho một danh sách tìm được thì
do LLM viết từ chính danh sách đó (`build_nearby_location_prompt`) — nếu không,
giọng của nhánh này lệch hẳn khỏi phần còn lại của hội thoại.
"""

from __future__ import annotations

from typing import Final

#: Hỏi LOẠI địa điểm. Nêu đủ năm lựa chọn ngay trong câu chữ: client chưa dựng
#: nút bấm vẫn dùng được tính năng bằng cách gõ tên loại, đúng quy ước mà
#: `QuickReplyView` đang giữ ("client chưa hỗ trợ nút bấm vẫn dùng được").
ASK_LOCATION_KIND_QUESTION: Final[str] = (
    "Dạ Quý khách muốn tìm loại địa điểm nào ạ? "
    "Em hỗ trợ tìm Showroom Ô tô, Showroom Xe máy điện, Trạm sạc Ô tô điện, "
    "Trạm sạc Xe máy điện và Tủ đổi pin."
)

#: Hỏi lại LOẠI khi câu vừa rồi không nhận ra loại nào
#: (`domain/pending_slot.MAX_CLARIFY_TURNS` cho phép đúng một lần hỏi lại).
ASK_LOCATION_KIND_RETRY: Final[str] = (
    "Dạ em chưa rõ Quý khách cần tìm loại nào ạ. "
    "Quý khách chọn giúp em một trong năm loại: Showroom Ô tô, Showroom Xe máy điện, "
    "Trạm sạc Ô tô điện, Trạm sạc Xe máy điện, hoặc Tủ đổi pin nhé."
)

#: Câu chốt khi đã hỏi hết lượt mà vẫn chưa rõ loại.
LOCATION_KIND_GIVE_UP: Final[str] = (
    "Dạ chưa rõ loại địa điểm nên em chưa tìm giúp Quý khách được. "
    "Khi nào tiện, Quý khách nhắn lại loại cần tìm, em tra ngay ạ. "
    "Trong lúc đó em vẫn hỗ trợ Quý khách về xe bình thường nhé."
)

#: Lời mời chia sẻ vị trí. `{kinds}` là nhãn loại đã chốt, viết thường.
ASK_LOCATION_QUESTION_TEMPLATE: Final[str] = (
    "Dạ, để tìm {kinds} gần nhất em cần biết Quý khách đang ở đâu ạ. "
    'Quý khách bấm "Chia sẻ vị trí của bạn" để em lấy vị trí tự động, '
    "hoặc gõ giúp em tên khu vực (ví dụ: Cầu Giấy, Hà Nội)."
)

#: Hỏi lại lần cuối khi câu vừa rồi không mang địa danh nào.
ASK_LOCATION_RETRY: Final[str] = (
    "Dạ em chưa nhận ra khu vực ạ. Quý khách cho em xin tên quận/huyện hoặc "
    "tỉnh/thành (ví dụ: Cầu Giấy, Hà Nội), hoặc bấm chia sẻ vị trí giúp em nhé."
)

#: Câu chốt khi đã hỏi hết lượt mà vẫn chưa có vị trí. Cần một câu tường minh ở
#: đây (khác `province`, vốn im lặng thả lượt về pipeline): bot vừa hỏi vị trí
#: hai lần, im lặng đổi chủ đề sau đó là bỏ rơi khách giữa câu hỏi của chính mình.
LOCATION_GIVE_UP: Final[str] = (
    "Dạ chưa xác định được khu vực nên em chưa tìm được địa điểm giúp Quý khách. "
    "Khi nào tiện, Quý khách nhắn lại tên khu vực hoặc bật chia sẻ vị trí, "
    "em tìm ngay ạ. Trong lúc đó em vẫn hỗ trợ Quý khách về xe bình thường nhé."
)

#: Geocode không ra kết quả. KHÔNG ném lỗi ra ngoài — xem `ports.GeocodePort`.
GEOCODE_FAILED_TEMPLATE: Final[str] = (
    'Dạ em chưa tra được vị trí "{location_text}" ạ. '
    'Quý khách thử gõ rõ hơn (ví dụ: "Cầu Giấy, Hà Nội") '
    "hoặc bấm chia sẻ vị trí để em tìm chính xác hơn nhé."
)

#: Không có địa điểm nào trong bán kính đã quét. Nêu RÕ bán kính: "không tìm
#: thấy" mà không kèm con số thì khách không biết nên gõ lại một khu vực rộng hơn
#: hay kết luận là quanh đó thật sự chưa có.
NO_RESULT_TEMPLATE: Final[str] = (
    "Dạ quanh vị trí của Quý khách trong bán kính {radius_km:.0f} km "
    "em chưa thấy {kinds} nào trong dữ liệu hiện có ạ. "
    "Quý khách thử gõ một khu vực khác giúp em, hoặc gọi hotline VinFast 1900 23 23 89 "
    "để được hỗ trợ nhanh nhất nhé."
)

#: Câu dẫn dự phòng khi chưa nối LLM hoặc lời gọi thất bại. Cố ý CHỈ nói số
#: lượng, không nhắc lại địa chỉ của địa điểm nào: những dữ liệu đó đã có trong
#: card, và chép chúng vào một câu viết tay là dựng một bộ định dạng thứ hai.
FALLBACK_LEAD_TEMPLATE: Final[str] = (
    "Dạ em tìm được {count} {kinds} gần Quý khách nhất, "
    'sắp xếp từ gần tới xa ạ. Quý khách bấm "Chỉ đường" ở địa điểm muốn tới nhé.'
)

#: `{distance}` đến từ `domain/nearby_location.format_distance`, vốn ĐÃ tự thêm
#: "khoảng" cho quãng dưới 1 km ("khoảng 600 m"). Template vì vậy không được thêm
#: chữ đó lần nữa — bản đầu viết "cách khoảng {distance}" và câu gửi khách đọc
#: thành "cách khoảng khoảng 600 m".
NEAREST_HINT_TEMPLATE: Final[str] = "Gần nhất là {name}, cách {distance}."


__all__ = [
    "ASK_LOCATION_KIND_QUESTION",
    "ASK_LOCATION_KIND_RETRY",
    "ASK_LOCATION_QUESTION_TEMPLATE",
    "ASK_LOCATION_RETRY",
    "FALLBACK_LEAD_TEMPLATE",
    "GEOCODE_FAILED_TEMPLATE",
    "LOCATION_GIVE_UP",
    "LOCATION_KIND_GIVE_UP",
    "NEAREST_HINT_TEMPLATE",
    "NO_RESULT_TEMPLATE",
]
