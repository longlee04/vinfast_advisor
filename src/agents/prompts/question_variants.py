"""Biến thể câu hỏi cho từng slot — chống lặp y nguyên khi phải hỏi lại.

Lặp đúng từng chữ câu hỏi vừa hỏi làm khách tưởng agent hỏng, kể cả khi logic
đằng sau đã đúng: đo trên 103 hội thoại thật, câu hỏi lặp liên tiếp là nhóm lỗi
lớn nhất còn lại sau khi vá vòng lặp intent.

[GIẢ ĐỊNH] Dùng template tĩnh, KHÔNG gọi LLM để viết lại: thêm một call mỗi lượt
chỉ để đổi cách nói là đánh đổi tệ về độ trễ và chi phí (prompt mục 3.1).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from src.agents.domain.values import SlotName
from src.agents.prompts.persona import CUSTOMER_ADDRESS
from src.agents.prompts.reply_variants import _variant_index

_ADDRESS = CUSTOMER_ADDRESS.capitalize()

# Phần tử [0] giữ NGUYÊN VĂN câu trong `slot_planning._QUESTION_TEMPLATES`: lượt
# hỏi đầu tiên phải không đổi so với trước, để thay đổi này chỉ ảnh hưởng đúng
# hành vi hỏi lại.
QUESTION_VARIANTS: Final[Mapping[SlotName, tuple[str, ...]]] = {
    SlotName.VEHICLE_TYPE: (
        f"{_ADDRESS} đang tìm ô tô điện hay xe máy điện ạ?",
        f"Dạ để em lọc đúng dòng xe, {CUSTOMER_ADDRESS} cần ô tô điện hay xe máy điện ạ?",
        f"{_ADDRESS} cho em xin loại xe nhé — ô tô điện hay xe máy điện ạ?",
        f"Dạ {CUSTOMER_ADDRESS} định mua ô tô điện hay xe máy điện ạ?",
        f"Em hỏi nhanh một chút ạ: {CUSTOMER_ADDRESS} quan tâm ô tô điện hay xe máy điện ạ?",
        f"Dạ mình bắt đầu từ loại xe nhé — {CUSTOMER_ADDRESS} cần ô tô điện hay xe máy điện ạ?",
        f"{_ADDRESS} đang nhắm ô tô điện hay xe máy điện ạ?",
        f"Dạ để em gợi ý cho sát, {CUSTOMER_ADDRESS} muốn xem ô tô điện hay xe máy điện ạ?",
    ),
    SlotName.PASSENGER_COUNT: (
        f"Xe thường chở mấy người, hoặc {CUSTOMER_ADDRESS} dùng để đi làm, giao hàng hay đi cá nhân ạ?",
        f"Dạ {CUSTOMER_ADDRESS} cho em biết xe hay chở khoảng bao nhiêu người, "
        "và chủ yếu dùng để đi làm, giao hàng hay đi cá nhân ạ?",
        f"Nhà mình thường đi mấy người một chuyến, với lại {CUSTOMER_ADDRESS} "
        "mua xe để đi làm, giao hàng hay đi cá nhân ạ?",
        f"Dạ mỗi chuyến {CUSTOMER_ADDRESS} thường đi mấy người ạ?",
        f"{_ADDRESS} hay đi một mình hay chở thêm người nhà ạ?",
        f"Dạ xe này {CUSTOMER_ADDRESS} tính chở bao nhiêu người là chính ạ?",
        f"Em hỏi thêm ạ: {CUSTOMER_ADDRESS} cần xe đủ chỗ cho mấy người ạ?",
        f"Dạ {CUSTOMER_ADDRESS} cho em xin số người hay đi cùng nhé ạ?",
    ),
    SlotName.REQUIRED_RANGE_KM: (
        f"Một ngày {CUSTOMER_ADDRESS} đi khoảng bao nhiêu ki-lô-mét ạ?",
        f"Dạ {CUSTOMER_ADDRESS} ước chừng mỗi ngày chạy bao xa ạ?",
        f"{_ADDRESS} đi lại nhiều không, tầm bao nhiêu km một ngày ạ?",
        f"Dạ quãng đường {CUSTOMER_ADDRESS} đi mỗi ngày khoảng bao nhiêu ạ?",
        f"Em hỏi để tính pin cho đúng ạ: mỗi ngày {CUSTOMER_ADDRESS} chạy chừng bao nhiêu ki-lô-mét ạ?",
        f"Dạ {CUSTOMER_ADDRESS} hay đi quanh nhà hay chạy đường dài ạ?",
        f"{_ADDRESS} cho em xin quãng đường trung bình mỗi ngày nhé ạ?",
        f"Dạ mỗi ngày {CUSTOMER_ADDRESS} di chuyển tầm bao nhiêu ạ?",
    ),
    SlotName.HOME_CHARGING: (
        f"Ở nhà {CUSTOMER_ADDRESS} có chỗ sạc qua đêm không ạ?",
        f"Dạ chỗ {CUSTOMER_ADDRESS} ở có lắp được sạc tại nhà không ạ?",
        f"{_ADDRESS} sạc xe ở nhà được hay phải dùng trạm sạc ngoài ạ?",
        "Dạ nhà mình có ổ cắm ở chỗ để xe không ạ?",
        f"Em hỏi thêm ạ: {CUSTOMER_ADDRESS} cắm sạc qua đêm ở nhà được chứ ạ?",
        f"Dạ {CUSTOMER_ADDRESS} định sạc ở nhà hay sạc tại trạm là chính ạ?",
        f"Chỗ đỗ xe của {CUSTOMER_ADDRESS} có điện để sạc không ạ?",
        f"Dạ {CUSTOMER_ADDRESS} có sạc được tại nhà không, hay hay dùng trạm ngoài ạ?",
    ),
    SlotName.BUDGET_MAX_VND: (
        f"{_ADDRESS} dự tính khoảng bao nhiêu cho chiếc xe này ạ?",
        f"Dạ để em tư vấn xe phù hợp hơn, {CUSTOMER_ADDRESS} cho em biết mức giá mong muốn khoảng bao nhiêu ạ?",
        f"{_ADDRESS} có thể chia sẻ khoảng ngân sách đang cân nhắc không ạ?",
        f"Dạ {CUSTOMER_ADDRESS} định chi khoảng bao nhiêu cho xe ạ?",
        f"Em hỏi để lọc đúng tầm giá ạ: {CUSTOMER_ADDRESS} dự trù khoảng bao nhiêu ạ?",
        f"Dạ mức giá {CUSTOMER_ADDRESS} thấy thoải mái là khoảng bao nhiêu ạ?",
        f"{_ADDRESS} cho em xin khoảng tiền dự tính nhé ạ?",
        f"Dạ {CUSTOMER_ADDRESS} đang cân nhắc tầm giá nào ạ?",
    ),
    SlotName.PURPOSE: (
        f"{_ADDRESS} mua xe để dùng vào mục đích gì ạ — đi làm, giao hàng hay đi cá nhân?",
        f"Dạ xe này {CUSTOMER_ADDRESS} dùng cho việc gì là chính ạ?",
        f"{_ADDRESS} cần xe để đi làm, chở gia đình hay chạy dịch vụ ạ?",
        f"Dạ {CUSTOMER_ADDRESS} mua xe chủ yếu để làm gì ạ?",
        f"Em hỏi thêm ạ: xe này phục vụ việc gì cho {CUSTOMER_ADDRESS} là nhiều nhất ạ?",
        f"Dạ {CUSTOMER_ADDRESS} định dùng xe đi làm, chở người nhà hay chạy dịch vụ ạ?",
        f"{_ADDRESS} cho em biết mục đích sử dụng chính nhé ạ?",
        f"Dạ xe sẽ theo {CUSTOMER_ADDRESS} vào việc gì hằng ngày ạ?",
    ),
    SlotName.MAX_LOAD_KG: (
        f"Mỗi chuyến {CUSTOMER_ADDRESS} thường chở nặng khoảng bao nhiêu ạ?",
        f"Dạ hàng {CUSTOMER_ADDRESS} chở mỗi chuyến tầm bao nhiêu ki-lô-gam ạ?",
        f"{_ADDRESS} cho em xin mức tải hay chở nhất ạ?",
        f"Dạ {CUSTOMER_ADDRESS} hay chở đồ nặng cỡ nào ạ?",
        "Em hỏi để chọn xe chịu tải đúng ạ: mỗi chuyến nặng khoảng bao nhiêu ạ?",
        f"Dạ {CUSTOMER_ADDRESS} chở hàng nhẹ hay nặng là chính ạ?",
        f"Mức hàng {CUSTOMER_ADDRESS} chở thường xuyên là bao nhiêu ạ?",
        f"Dạ {CUSTOMER_ADDRESS} cho em biết tải trọng hay dùng nhất nhé ạ?",
    ),
    SlotName.HABIT_NEED_TAGS: (
        f"{_ADDRESS} thường dùng xe thế nào, có gì đặc biệt cần lưu ý không ạ?",
        f"Dạ {CUSTOMER_ADDRESS} có yêu cầu gì thêm về xe không ạ?",
        f"Còn điều gì {CUSTOMER_ADDRESS} muốn em lưu ý khi chọn xe không ạ?",
        f"Dạ thói quen đi lại của {CUSTOMER_ADDRESS} có gì em nên biết không ạ?",
        f"{_ADDRESS} có mong muốn nào riêng về chiếc xe không ạ?",
        f"Dạ ngoài những điều trên, {CUSTOMER_ADDRESS} còn cần gì nữa không ạ?",
        f"Em nghe thêm ạ: {CUSTOMER_ADDRESS} hay dùng xe trong hoàn cảnh nào ạ?",
        f"Dạ {CUSTOMER_ADDRESS} kể em nghe cách mình hay đi lại nhé ạ?",
    ),
}


# Câu định tuyến không thuộc slot nào: nó hỏi khách muốn TRA CỨU hay TƯ VẤN,
# trước khi cây slot bắt đầu. Vẫn cần biến thể vì đo trên 103 hội thoại thật, nó
# là nguồn DUY NHẤT còn lại của lỗi lặp y nguyên câu hỏi.
ROUTING_FIELD: Final[str] = "__routing__"

ROUTING_VARIANTS: Final[tuple[str, ...]] = (
    f"{_ADDRESS} muốn tra cứu thông tin một mẫu xe cụ thể hay cần tư vấn chọn xe phù hợp ạ?",
    f"Dạ {CUSTOMER_ADDRESS} đang cần em tra cứu một mẫu xe có sẵn, hay tư vấn chọn xe theo nhu cầu ạ?",
    f"Để em hỗ trợ đúng hướng, {CUSTOMER_ADDRESS} cho em biết mình muốn hỏi một mẫu xe cụ thể "
    "hay cần em gợi ý xe phù hợp ạ?",
    f"Dạ {CUSTOMER_ADDRESS} đã nhắm sẵn mẫu nào chưa, hay để em gợi ý theo nhu cầu ạ?",
    f"{_ADDRESS} muốn em tra thông tin một xe cụ thể, hay cùng em chọn xe từ đầu ạ?",
    f"Dạ mình đi hướng nào ạ — {CUSTOMER_ADDRESS} hỏi về một mẫu có sẵn, hay để em tư vấn chọn xe ạ?",
    f"Em hỏi cho đúng việc ạ: {CUSTOMER_ADDRESS} cần tra cứu một mẫu xe, hay cần em gợi ý xe hợp nhu cầu ạ?",
    f"Dạ {CUSTOMER_ADDRESS} muốn xem thông tin một mẫu xe nhất định, hay cần em tư vấn chọn xe ạ?",
)


def _index_for(count: int, retry_count: int, seed: str) -> int:
    """Chỉ số biến thể: điểm xuất phát theo PHIÊN, bước theo số lần hỏi lại.

    **Vì sao cần `seed`** (Sếp 2026-08-26, đo trên prod): bản cũ dùng
    `min(retry_count, count - 1)`, nên mọi phiên mới đều bắt đầu ở `retry_count =
    0` và luôn rơi vào biến thể `[0]`. Kết quả: câu hỏi loại xe lặp **y nguyên 80
    lần** qua hàng chục hội thoại khác nhau. Biến thể chỉ chống lặp TRONG một hội
    thoại, không chống lặp GIỮA các hội thoại.

    Cộng `retry_count` rồi lấy dư giữ nguyên tính chất quan trọng nhất: hai lượt
    hỏi lại liên tiếp trong CÙNG phiên vẫn ra hai câu khác nhau.

    **KẸP `retry_count` trước khi cộng**, không lấy dư thẳng: lấy dư thẳng thì
    lần hỏi lại thứ tư quay về đúng câu đã hỏi ở lần đầu — tức lặp y nguyên,
    đúng thứ hàm này sinh ra để tránh. Kẹp lại thì hết biến thể là dừng ở câu
    cuối của vòng, giống hành vi cũ.

    `seed` rỗng giữ nguyên hành vi cũ, để chỗ gọi chưa có danh tính phiên không vỡ.
    """

    step = min(max(retry_count, 0), count - 1)
    return (_variant_index(count, seed) + step) % count


def get_routing_variant(retry_count: int, seed: str = "") -> str:
    """Câu định tuyến, đổi cách nói theo phiên và theo số lần đã hỏi."""

    return ROUTING_VARIANTS[_index_for(len(ROUTING_VARIANTS), retry_count, seed)]


def get_question_variant(slot: SlotName, retry_count: int, seed: str = "") -> str:
    """Câu hỏi cho `slot`, đổi cách nói theo phiên và theo số lần đã hỏi."""

    variants: Sequence[str] = QUESTION_VARIANTS[slot]
    return variants[_index_for(len(variants), retry_count, seed)]
