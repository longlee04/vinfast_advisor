"""[A3-2] Hỏi GỘP mọi tiêu chí còn thiếu trong MỘT tin nhắn, sau khi đã biết loại xe.

Luồng cũ hỏi tuần tự từng slot một: "ô tô điện hay xe máy điện ạ?" → khách trả
lời → "anh/chị dự tính khoảng bao nhiêu ạ?" → khách trả lời → … Mỗi lượt đúng
một câu, nên một cuộc tư vấn tốn bốn năm lượt qua lại trước khi thấy chiếc xe
đầu tiên.

Luồng mới giữ nguyên BƯỚC MỘT và chỉ gộp phần còn lại:

    1. Chưa biết `vehicle_type` → vẫn hỏi RIÊNG một câu "ô tô điện hay xe máy
       điện ạ?". Đây là quyết định nghiệp vụ, không phải chỗ tiết kiệm được một
       lượt: hai loại phương tiện có hai cây slot khác nhau, và mọi câu hỏi phía
       sau (mục đích, yêu cầu đặc biệt) chỉ viết đúng được khi đã biết loại xe.
    2. Đã biết `vehicle_type` → MỘT tin nhắn hỏi hết các tiêu chí còn thiếu,
       dạng danh sách đánh số.

Câu chữ của mục 2 và 3 khác nhau theo loại xe, không dùng chung một bản: hỏi một
khách mua xe máy điện rằng họ cần xe cho "kinh doanh dịch vụ" hay có yêu cầu gì
về "kích thước xe" là hỏi bằng từ vựng của một sản phẩm khác.

Danh sách được dựng TỪ SLOT CÒN THIẾU chứ không phải ba câu cố định: khách nói
"tôi cần tư vấn xe ô tô 700 triệu" đã cho sẵn ngân sách, nên hỏi lại nó trong
danh sách là hỏi một điều vừa được trả lời.

Định dạng Markdown theo quy ước chung ở `domain/reply_format`: tên trường in đậm,
mục lớn đánh số, xuống dòng thật giữa các mục.

THUẦN Python (mục 6.5b): không SQLAlchemy/FastAPI/LangGraph/LLM SDK. Template
tĩnh, KHÔNG gọi LLM — cùng lý do với `prompts/question_variants`: thêm một lần
gọi mỗi lượt chỉ để đổi cách nói là đánh đổi tệ về độ trễ và chi phí (mục 3.1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from src.agents.domain.reply_format import bold, italic
from src.agents.domain.values import SlotName, VehicleType

#: Các CHỦ ĐỀ được gộp vào tin nhắn, theo đúng thứ tự trình bày.
#:
#: **HAI chủ đề, không phải ba** (Sếp 2026-08-26). Bản trước có thêm "yêu cầu
#: đặc biệt" gợi ý cả kích thước, quãng đường lẫn tính năng thông minh — ba
#: hướng trong một mục, nên khách trả lời đúng một hướng rồi thôi.
#:
#: Mọi trường còn lại (số chỗ, quãng đường mỗi ngày, sạc tại nhà, tính năng)
#: KHÔNG hỏi nữa, vì không trường nào trong đó CHẶN được việc đề xuất:
#:
#: - số chỗ chỉ CỘNG ĐIỂM xếp hạng (`domain/scoring` line ~382), không lọc;
#: - quãng đường chỉ chạm 2 trong 8 khoản của bảng chi phí — đo trên VF 8, phần
#:   đổi theo quãng đường chiếm 2,4% tổng ở 20 km/ngày và 8,8% ở 80 km/ngày, nên
#:   hơn 91% con số đã biết trước khi khách nói gì; thiếu thì mặc định 30 km/ngày
#:   và NÓI RA giả định (`nodes/tco`), rẻ hơn một lượt hỏi;
#: - tính năng đã bỏ hẳn khỏi bước hỏi (`routing.route_after_layer1`).
#:
#: Cả bốn vẫn được NHẶT bình thường khi khách tự nhắc, ở bất kỳ lượt nào — đó là
#: việc của `extract_slots`, không phải của câu hỏi.
#:
#: Slot nào đã có giá trị thì chủ đề của nó biến mất khỏi danh sách.
INTAKE_TOPICS: Final[tuple[SlotName, ...]] = (
    SlotName.BUDGET_MAX_VND,
    SlotName.PURPOSE,
)

#: Số mục tối thiểu để một danh sách đánh số có nghĩa. Còn đúng một tiêu chí
#: thiếu thì câu hỏi đơn của `question_variants` ngắn hơn và tự nhiên hơn — một
#: danh sách một phần tử nói rằng còn mục 2 ở đâu đó.
MIN_TOPICS: Final[int] = 2

_OPENING: Final[Mapping[VehicleType, str]] = {
    VehicleType.CAR: (
        "Dạ, em rất vui được hỗ trợ Quý khách chọn ô tô điện VinFast. "
        "Quý khách cho em biết thêm về nhu cầu của mình nhé:"
    ),
    VehicleType.ELECTRIC_MOTORBIKE: (
        "Dạ, VinFast hiện có nhiều mẫu xe máy điện cho những nhu cầu khác nhau. "
        "Để em tư vấn chính xác hơn, Quý khách cho em biết thêm một số thông tin nhé:"
    ),
}

_CLOSING: Final[Mapping[VehicleType, str]] = {
    VehicleType.CAR: ("Dựa trên thông tin Quý khách chia sẻ, em sẽ tư vấn mẫu xe phù hợp nhất ạ."),
    VehicleType.ELECTRIC_MOTORBIKE: ("Dựa trên thông tin này, em sẽ gợi ý mẫu xe phù hợp nhất với Quý khách ạ."),
}

#: Nhãn + câu hỏi của từng chủ đề, VIẾT RIÊNG cho từng loại xe.
#:
#: Ngân sách dùng chung một câu vì nó là cùng một câu hỏi ở cả hai nhánh; chủ đề
#: còn lại thì không — ví dụ của ô tô ("chở gia đình 5 người") không áp được cho
#: xe máy điện, và ngược lại.
#:
#: **Mục 2 là câu MỞ kèm ví dụ mẫu, không phải câu chọn nhãn** (Sếp 2026-08-26).
#: Bản trước hỏi đóng — "mục đích gì (gia đình, cá nhân, công việc, kinh doanh
#: dịch vụ)" — nên thu về đúng một nhãn và không gì khác. Câu mở kèm ví dụ CÓ SỐ
#: thu về nhiều trường trong cùng một câu trả lời, vì khách bắt chước dạng của
#: ví dụ: nêu "30 km mỗi ngày" thì được cả quãng đường, nêu "gia đình 5 người"
#: thì được cả số chỗ. Đó là cách lấy bốn trường mà chỉ tốn MỘT mục.
#:
#: Ví dụ phải giữ con số thật trong đó. Bỏ số đi ("đi làm hằng ngày, cuối tuần
#: đi chơi") thì khách cũng trả lời không số, và quãng đường lại về mặc định.
_TOPICS: Final[Mapping[VehicleType, Mapping[SlotName, tuple[str, str]]]] = {
    VehicleType.CAR: {
        SlotName.BUDGET_MAX_VND: (
            "Ngân sách",
            "Quý khách dự kiến khoảng bao nhiêu cho chiếc xe này ạ?",
        ),
        SlotName.PURPOSE: (
            "Nhu cầu & thói quen đi lại",
            "Quý khách cần xe cho việc gì và thường đi lại ra sao ạ?\n"
            + italic("ví dụ: đi làm khoảng 30 km mỗi ngày, cuối tuần chở gia đình 5 người đi chơi"),
        ),
    },
    VehicleType.ELECTRIC_MOTORBIKE: {
        SlotName.BUDGET_MAX_VND: (
            "Ngân sách",
            "Quý khách dự kiến khoảng bao nhiêu cho chiếc xe này ạ?",
        ),
        SlotName.PURPOSE: (
            "Nhu cầu & thói quen đi lại",
            "Quý khách cần xe cho việc gì và thường đi lại ra sao ạ?\n"
            + italic("ví dụ: đi học khoảng 15 km mỗi ngày, thỉnh thoảng chở thêm đồ"),
        ),
    },
}


def build_combined_intake_question(*, vehicle_type: VehicleType, unanswered: Sequence[SlotName]) -> str | None:
    """Tin nhắn hỏi gộp, hoặc `None` khi không đủ chủ đề để đáng gộp.

    `None` là tín hiệu cho người gọi quay về câu hỏi đơn của `question_variants` —
    hàm này cố ý không tự chọn thay, vì việc chọn biến thể theo số lần đã hỏi
    thuộc về ở đó.
    """

    topics = _TOPICS.get(vehicle_type)
    if topics is None:
        return None
    pending = [slot for slot in INTAKE_TOPICS if slot in set(unanswered) and slot in topics]
    if len(pending) < MIN_TOPICS:
        return None
    items = "\n".join(
        f"{index}. {bold(topics[slot][0])}: {topics[slot][1]}" for index, slot in enumerate(pending, start=1)
    )
    return "\n\n".join((_OPENING[vehicle_type], items, _CLOSING[vehicle_type]))


__all__ = ["INTAKE_TOPICS", "MIN_TOPICS", "build_combined_intake_question"]
