"""Biến thể lời chào / lời từ chối — chống lặp y nguyên GIỮA các hội thoại.

THUẦN Python — không import FastAPI/SQLAlchemy/LLM SDK.

**Đo trên prod 2026-08-26** (Sếp: "lặp lại liên tục như vậy cũng hơi tệ"):

    80 lần  "Anh/chị có đang tìm kiếm ô tô điện hay xe máy điện không ạ?"
    28 lần  "Em chỉ hỗ trợ tư vấn từ dữ liệu sản phẩm và chính sách VinFast…"
    27 lần  "Chào anh/chị ạ. Em có thể hỗ trợ chọn xe, tra cứu giá hoặc thông tin VinFast."

Ba câu này **giống nhau từng chữ** qua hàng chục hội thoại khác nhau.

`prompts/question_variants.py` đã có biến thể, nhưng nó chọn theo `retry_count`
nên chỉ chống lặp TRONG một hội thoại: mỗi phiên mới bắt đầu lại từ `retry_count
= 0` và luôn rơi vào biến thể `[0]`. Lặp giữa các phiên vẫn nguyên.

Lối ra là chọn theo **danh tính phiên** thay vì chỉ theo số lần hỏi lại.

**Vì sao KHÔNG gọi LLM viết lại**: cùng lý do `question_variants` đã chốt — thêm
một lời gọi mỗi lượt chỉ để đổi cách nói là đánh đổi tệ về độ trễ và chi phí. Và
với câu từ chối thì còn tệ hơn: nó là RÀO CHẮN phạm vi, để mô hình viết lại là mở
đúng cái cửa mà nó đang canh.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Final


def _variant_index(count: int, seed: str) -> int:
    """Chỉ số biến thể, TẤT ĐỊNH theo `seed`.

    **Không dùng `hash()`**: Python băm chuỗi kèm `PYTHONHASHSEED` ngẫu nhiên mỗi
    tiến trình, nên cùng một phiên sẽ nhận câu khác nhau sau mỗi lần restart
    backend — không tái lập được, và test thì đỏ ngẫu nhiên. `blake2s` cho cùng
    một kết quả ở mọi tiến trình, mọi máy, mọi phiên bản.

    `seed` rỗng → biến thể đầu. Chỗ gọi nào chưa có danh tính phiên vẫn chạy
    đúng như trước, không vỡ.
    """

    if count <= 0:
        raise ValueError("variant list must not be empty")
    if not seed:
        return 0
    digest = hashlib.blake2s(seed.encode("utf-8"), digest_size=4).digest()
    return int.from_bytes(digest, "big") % count


def pick_variant(variants: Sequence[str], seed: str) -> str:
    """Chọn một biến thể, TẤT ĐỊNH theo `seed`. Xem `_variant_index`."""

    return variants[_variant_index(len(variants), seed)]


#: Lời chào. Sếp 2026-08-26: "dài hơn 1 chút thì tốt" — bản cũ một câu cụt
#: ("Chào anh/chị ạ. Em có thể hỗ trợ chọn xe, tra cứu giá hoặc thông tin
#: VinFast.") đọc như một dòng trạng thái, không như một người mở lời.
#:
#: Mỗi biến thể kết bằng một câu MỜI khách nói tiếp — lời chào không có lối đi
#: tiếp thì khách phải tự nghĩ ra câu hỏi, và đó là lúc hội thoại chết.
SOCIAL_VARIANTS: Final[tuple[str, ...]] = (
    "Dạ em chào anh/chị ạ. Em là trợ lý tư vấn xe điện VinFast, có thể giúp anh/chị "
    "chọn xe theo nhu cầu, tra cứu giá và thông số, hoặc giải đáp về chi phí sử dụng. "
    "Anh/chị đang quan tâm tới điều gì để em hỗ trợ ngay ạ?",
    "Dạ em chào anh/chị. Em tư vấn được các việc như gợi ý xe hợp với nhu cầu đi lại, "
    "tra thông tin và giá của từng mẫu, hay ước tính chi phí sử dụng hằng tháng. "
    "Anh/chị cho em biết mình đang cần gì nhé ạ?",
    "Dạ vâng, em chào anh/chị ạ. Anh/chị cần em tư vấn chọn xe, tra cứu một mẫu xe cụ thể, "
    "hay tìm hiểu chi phí sử dụng đều được ạ. Anh/chị bắt đầu từ đâu để em theo cùng nhé?",
    "Em chào anh/chị ạ. Em ở đây để tư vấn chọn xe điện VinFast hợp với việc đi lại hằng ngày, "
    "và tra giúp giá cùng thông số của bất kỳ mẫu nào anh/chị đang để ý. "
    "Anh/chị muốn bắt đầu từ đâu ạ?",
    "Dạ em chào anh/chị. Em tư vấn chọn xe theo nhu cầu, tra giá từng phiên bản và ước tính chi phí "
    "sử dụng đều được hết ạ. Anh/chị đang tìm xe cho riêng mình, cho gia đình hay để chạy dịch vụ ạ?",
    "Dạ em chào anh/chị ạ. Dù anh/chị mới bắt đầu tìm hiểu hay đã nhắm sẵn một mẫu, em đều hỗ trợ "
    "được: chọn xe theo nhu cầu, so giá các phiên bản, hoặc tính chi phí đi lại hằng tháng. "
    "Anh/chị cần em bắt đầu từ phần nào ạ?",
    "Em chào anh/chị ạ. Em nắm thông tin sản phẩm và chính sách VinFast, nên anh/chị cứ hỏi thoải "
    "mái về việc chọn xe, giá bán, thông số hay chi phí nuôi xe. Anh/chị đang băn khoăn điều gì "
    "nhất ạ?",
    "Dạ vâng ạ, em chào anh/chị. Em có thể tư vấn chọn xe theo cách anh/chị hay đi lại, tra giá và "
    "thông số từng mẫu, hoặc ước tính chi phí sử dụng lâu dài. Anh/chị muốn em giúp phần nào trước ạ?",
)


#: Lời từ chối khi câu hỏi nằm ngoài phạm vi. Dựng thành CẶP
#: `(giới hạn, lối đi tiếp)` vì `domain/scope.py` trả về hai trường riêng, còn
#: `nodes/classify_scope.py` cần đúng một chuỗi đã ghép — hai nơi PHẢI ra cùng
#: một câu cho cùng một phiên, nếu không khách gặp hai lời từ chối khác nhau tuỳ
#: lượt bị đóng ở cửa tất định hay ở nhãn của bộ phân loại.
#:
#: Bản cũ cụt ở chỗ nó chỉ NÓI KHÔNG. Mỗi biến thể ở đây giữ nguyên nội dung từ
#: chối nhưng nói rõ vì sao có giới hạn đó, rồi mở đúng ba lối: hỏi việc trong
#: phạm vi, hoặc gặp tư vấn viên.
FOREIGN_DOMAIN_VARIANTS: Final[tuple[tuple[str, str], ...]] = (
    (
        "Dạ em xin lỗi, câu này nằm ngoài phần em phụ trách. Em chỉ tư vấn dựa trên dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "nên những gì ngoài đó em không dám trả lời để tránh đưa thông tin sai.",
        "Anh/chị có thể hỏi em về nhu cầu chọn xe VinFast, giá và thông số từng mẫu, hoặc chi phí "
        "sử dụng. Nếu cần trao đổi sâu hơn, em xin phép chuyển sang tư vấn viên giúp anh/chị ạ.",
    ),
    (
        "Dạ phần này em chưa hỗ trợ được ạ. Em chỉ làm việc với dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "nên ngoài phạm vi đó em không có căn cứ để trả lời anh/chị.",
        "Em có thể giúp anh/chị chọn xe hợp nhu cầu, tra giá và thông số, hoặc ước tính chi phí "
        "sử dụng. Anh/chị cũng có thể yêu cầu em chuyển sang tư vấn viên bất cứ lúc nào ạ.",
    ),
    (
        "Dạ em xin phép không trả lời câu này ạ. Kiến thức của em giới hạn trong dữ liệu sản phẩm và chính sách VinFast đã được xác minh — "
        "nói ngoài phạm vi đó thì em không bảo đảm được độ chính xác cho anh/chị.",
        "Còn về xe VinFast thì anh/chị cứ hỏi em thoải mái: chọn xe theo nhu cầu, giá và thông số, "
        "hay chi phí sử dụng hằng tháng. Cần người hỗ trợ trực tiếp thì em chuyển tư vấn viên ngay ạ.",
    ),
    (
        "Dạ câu này em đành chịu ạ. Em được xây dựng để trả lời trong phạm vi dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "nên bước ra ngoài là em không còn gì để đối chiếu.",
        "Trong phạm vi đó thì em giúp được nhiều: chọn xe theo nhu cầu, giá từng phiên bản, chi phí "
        "sử dụng. Anh/chị muốn gặp người thật thì em chuyển tư vấn viên ngay ạ.",
    ),
    (
        "Dạ em rất tiếc, chuyện này ngoài hiểu biết của em. Em chỉ trả lời được từ dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "còn lại em không dám đoán để anh/chị khỏi nhận thông tin sai.",
        "Em quay lại phần em rành nhé: chọn xe hợp nhu cầu, giá và thông số các mẫu, hay chi phí đi "
        "lại hằng tháng. Anh/chị cần tư vấn viên hỗ trợ trực tiếp thì em nối máy ngay ạ.",
    ),
    (
        "Dạ em không trả lời được câu này ạ. Mọi câu trả lời của em đều phải dựa trên dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "và câu này thì không có nguồn nào để em dựa vào.",
        "Đổi lại, anh/chị hỏi em về việc chọn xe, giá bán hay chi phí sử dụng thì em trả lời được "
        "ngay. Muốn trao đổi kỹ hơn thì em mời tư vấn viên vào cùng ạ.",
    ),
    (
        "Dạ nội dung này nằm ngoài phần em được giao ạ. Em làm việc trong phạm vi dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "nên em xin phép không trả lời để tránh nói sai với anh/chị.",
        "Em vẫn ở đây cho mọi thắc mắc về xe VinFast: chọn xe theo nhu cầu, giá và thông số, chi phí "
        "sử dụng. Hoặc anh/chị bảo em một tiếng, em chuyển sang tư vấn viên ạ.",
    ),
    (
        "Dạ em xin phép dừng ở đây với câu này ạ. Em chỉ chắc chắn được với dữ liệu sản phẩm và chính sách VinFast đã được xác minh, "
        "ngoài phạm vi đó em không có cơ sở nào để trả lời cho đúng.",
        "Còn về xe thì anh/chị hỏi em thoải mái nhé: chọn xe hợp nhu cầu, giá từng phiên bản, chi phí "
        "sử dụng hằng tháng. Cần người hỗ trợ trực tiếp thì em chuyển tư vấn viên ạ.",
    ),
)


#: Cụm BẤT BIẾN mọi biến thể từ chối phải chứa. Đây là phần NGHIỆP VỤ của lời từ
#: chối — nói rõ giới hạn nằm ở dữ liệu đã xác minh — nên nó không được biến mất
#: khi ai đó viết thêm biến thể cho hay hơn. Test khoá, và các test luồng đối
#: chiếu cụm này thay vì đối chiếu nguyên văn một biến thể cụ thể.
FOREIGN_DOMAIN_ANCHOR: Final[str] = "dữ liệu sản phẩm và chính sách VinFast đã được xác minh"


def social_reply(seed: str = "") -> str:
    """Lời chào cho một phiên."""

    return pick_variant(SOCIAL_VARIANTS, seed)


def foreign_domain_parts(seed: str = "") -> tuple[str, str]:
    """Cặp `(giới hạn, lối đi tiếp)` của lời từ chối, cho một phiên."""

    index = _variant_index(len(FOREIGN_DOMAIN_VARIANTS), seed)
    return FOREIGN_DOMAIN_VARIANTS[index]


def foreign_domain_reply(seed: str = "") -> str:
    """Lời từ chối đã ghép — phải ra ĐÚNG chuỗi `ScopeDecision.user_response` dựng.

    Nối bằng KHOẢNG TRẮNG, không phải xuống dòng: `scope.ScopeDecision.
    user_response` dùng `f"{limitation} {escape_route}"`, và
    `test_classify_scope_size_gate` khoá hai bản bằng nhau. Lệch một ký tự ở đây
    là khách gặp hai lời từ chối khác nhau tuỳ lượt bị đóng ở cửa tất định hay ở
    nhãn của bộ phân loại — sai lặng lẽ, không test nào ngoài cái đó bắt được.
    """

    limitation, escape = foreign_domain_parts(seed)
    return f"{limitation} {escape}"


#: Thân câu hỏi tính năng lượt 2. Đổi theo phiên, nhưng CẤU TRÚC giữ nguyên: một
#: dòng dẫn kết bằng dấu hỏi, rồi danh sách gạch đầu dòng do code dựng.
#:
#: Sếp 2026-08-26: "chỗ thì có đánh highlight in đậm chỗ thì viết liền nhưng gạch
#: đầu dòng ở cùng dòng". Gốc là tầng LLM viết lại — nó ép danh sách vào một dòng
#: và tự viết hoa tên tính năng. Tầng đó đã gỡ; đa dạng giờ nằm ở đây, nơi cấu
#: trúc không thể bị phá.
#:
#: Mỗi biến thể phải kết bằng "?" — dòng dẫn không có dấu hỏi thì danh sách ngay
#: dưới đọc như một lời liệt kê, không như một câu hỏi đang chờ trả lời.
FEATURE_QUESTION_BODIES: Final[tuple[str, ...]] = (
    "quan tâm đến những tính năng nào dưới đây ạ?",
    "cần những tính năng nào trong số dưới đây ạ?",
    "để ý tới tính năng nào dưới đây nhất ạ?",
    "thấy tính năng nào dưới đây là cần thiết với mình ạ?",
    "muốn xe có những tính năng nào trong số này ạ?",
    "ưu tiên tính năng nào dưới đây ạ?",
    "quan tâm tới mục nào trong những tính năng dưới đây ạ?",
    "cho em biết tính năng nào dưới đây là quan trọng với mình nhé ạ?",
)


def feature_question_body(seed: str = "") -> str:
    """Thân câu hỏi tính năng cho một phiên."""

    return pick_variant(FEATURE_QUESTION_BODIES, seed)


# ── Câu hỏi tiếp SAU khi đã đề xuất xe ───────────────────────────────────────
#
# Sếp 2026-08-26: *"sau khi đề xuất mẫu xe xong thì có thể hỏi tiếp… anh chị có
# thấy hài lòng không, nếu quan tâm thì cho em tên mẫu và thông tin để tính TCO,
# hay mình còn cân nhắc điều gì"*.
#
# Trước đây pitch xong là hết — không câu nào mời khách đi tiếp, hội thoại cụt
# ngay lúc khách vừa có đủ thứ để cân nhắc.
#
# **Chỉ hỏi thứ hệ thống DÙNG ĐƯỢC.** `tco_estimation.estimate()` nhận đúng
# `vehicle_id`, `daily_distance_km` và `region_code`; trong đó `region_code` chưa
# nối vào hội thoại (node TCO không truyền, luôn rơi về mặc định). Nên thứ duy
# nhất đáng hỏi là QUÃNG ĐƯỜNG MỖI NGÀY. Hỏi thêm "thông tin a, b, c" chung chung
# là bắt khách gõ những thứ rồi không ai đọc tới.

#: Dùng khi TCO đã tính được — không còn gì phải xin, chỉ mời khách phản hồi.
POST_PITCH_VARIANTS: Final[tuple[str, ...]] = (
    "Anh/chị thấy những mẫu trên có hợp ý mình không ạ? Nếu anh/chị ưng mẫu nào, "
    "cho em biết tên mẫu để em gửi thêm thông tin chi tiết, còn nếu chưa ưng thì "
    "anh/chị cứ nói em điều mình đang băn khoăn nhé ạ.",
    "Dạ không biết mấy mẫu em vừa giới thiệu có gần với mong muốn của anh/chị chưa ạ? "
    "Anh/chị chọn được mẫu nào thì cho em tên mẫu, hoặc nói em nghe điểm nào chưa vừa ý "
    "để em tìm phương án khác ạ.",
    "Anh/chị xem qua thấy sao ạ? Mẫu nào anh/chị muốn tìm hiểu kỹ hơn thì cho em biết tên, "
    "còn nếu cần em lọc theo tiêu chí khác thì anh/chị cứ nói ạ.",
    "Dạ em gửi anh/chị tham khảo. Anh/chị ưng mẫu nào thì nhắn em tên mẫu để em nói kỹ hơn, "
    "hay còn điều gì anh/chị đang cân nhắc thì em nghe với ạ?",
    "Mấy mẫu này có mẫu nào anh/chị thấy ổn không ạ? Cho em xin tên mẫu anh/chị quan tâm nhất, "
    "hoặc nói em biết mình cần đổi tiêu chí nào ạ.",
    "Dạ anh/chị thấy các phương án trên thế nào ạ? Em có thể đi sâu vào một mẫu cụ thể nếu "
    "anh/chị cho em biết tên, hoặc tìm hướng khác nếu chưa mẫu nào hợp ạ.",
    "Anh/chị cân nhắc giúp em xem có mẫu nào đáng để tìm hiểu thêm không ạ? Có thì anh/chị "
    "nhắn em tên mẫu, chưa có thì anh/chị chia sẻ điều còn vướng để em gợi ý lại ạ.",
    "Dạ trên đây là những mẫu em thấy hợp nhất với nhu cầu anh/chị vừa nêu. Anh/chị muốn xem "
    "kỹ mẫu nào ạ? Cho em tên mẫu, còn nếu cần điều chỉnh gì thì anh/chị cứ nói với em ạ.",
)


#: Nói ra số mẫu ĐÃ CẮT khỏi màn hình.
#:
#: `chain` giữ đúng ba thẻ (Sếp 2026-08-26) vì câu mời nói "ba mẫu" và khách chỉ
#: chọn được giữa những mẫu có lý do đi kèm. Nhưng bộ lọc thường còn mẫu hợp
#: khác, và im lặng bỏ chúng là để khách không ưng cả ba phải tự nêu lại tiêu
#: chí — trong khi hệ ĐANG có sẵn thứ họ cần.
#:
#: Một câu, đặt sau câu mời chính: nó là đường thoát, không phải lời chào mời.
_MORE_MATCHES_TEMPLATE: Final[str] = (
    "Ngoài ra em còn {count} mẫu khác cũng hợp tiêu chí, anh/chị muốn xem thì em gửi thêm ạ."
)


def more_matches_note(count: int) -> str:
    """Câu nói ra số mẫu hợp còn lại ngoài ba thẻ đang hiện."""

    if count <= 0:
        raise ValueError("more_matches_note can chi so mau con lai duong")
    return _MORE_MATCHES_TEMPLATE.format(count=count)


# ── Chặng SAU khi khách đã chốt một mẫu ──────────────────────────────────────
#
# Sếp 2026-08-26. Mỗi chặng một bộ câu riêng vì chúng chờ những câu trả lời KHÁC
# hẳn nhau — xem `domain/post_pitch`. Dùng chung một bộ thì lượt sau không biết
# khách đang đáp câu nào.

#: Câu hỏi HAI LỐI sau khi đã gửi thông tin xe và chi phí (Sếp 2026-08-26).
#:
#: Thay cho cặp `CONCERN_QUESTION_BODIES` → `TEST_DRIVE_INVITE_BODIES` cũ, vốn
#: tốn hai lượt cho một quyết định.
#:
#: Mỗi biến thể phải NÊU TÊN cả hai lối — "đặt lịch lái thử" và "còn điều gì cần
#: làm rõ" — theo đúng thứ tự đó. `domain/concern_reply.classify_post_pitch_decision`
#: đọc câu đáp theo hai lối này; một câu hỏi mở trống thì khách đáp kiểu gì cũng
#: được và bộ đọc trả `UNCLEAR`, rồi agent hỏi lại, thành vòng.
#:
#: Lối lái thử đứng TRƯỚC: nó là bước tiến, và đặt nó sau một lời mời nêu vấn đề
#: là gợi ý cho khách rằng đáng ra họ nên còn vướng điều gì đó.
POST_PITCH_DECISION_BODIES: Final[tuple[str, ...]] = (
    "Anh/chị muốn em đặt lịch lái thử mẫu này, hay còn điều gì cần em làm rõ thêm ạ?",
    "Em xếp cho anh/chị một buổi lái thử nhé, hay anh/chị còn thắc mắc gì về xe muốn hỏi thêm ạ?",
    "Anh/chị thấy sao ạ — mình đặt lịch lái thử luôn, hay còn chỗ nào anh/chị chưa yên tâm ạ?",
    "Anh/chị có muốn cầm lái thử mẫu này không ạ? Còn nếu vẫn còn điều gì lăn tăn thì anh/chị cứ nói em nghe ạ.",
    "Em mời anh/chị trải nghiệm thực tế mẫu này nhé? Hoặc anh/chị còn băn khoăn gì thì em làm rõ giúp anh/chị trước ạ.",
    "Mình đặt lịch lái thử cho chắc anh/chị nhé? Còn thắc mắc gì về xe thì anh/chị cứ hỏi, em sẵn sàng ạ.",
    "Anh/chị muốn lái thử xe một vòng chứ ạ? Hay còn điểm nào anh/chị thấy chưa rõ, cần em giải thích kỹ hơn ạ?",
    "Em đặt lịch lái thử giúp anh/chị nhé, hay anh/chị còn gì chưa rõ về xe muốn trao đổi thêm ạ?",
)

#: Khách đã nói HẾT vướng nhưng chưa nói gì về lái thử → mời lại cho RÕ.
#:
#: Khác `CONCERN_CLARIFY_BODIES`: ở đây khách đã trả lời xong một nửa câu hỏi, và
#: hỏi lại cả câu là bắt họ nói lại điều vừa nói. Chỉ hỏi nốt nửa còn thiếu.
POST_PITCH_CONFIRM_TEST_DRIVE_BODIES: Final[tuple[str, ...]] = (
    "Dạ vâng ạ. Vậy em đặt lịch lái thử cho anh/chị nhé?",
    "Dạ em ghi nhận ạ. Anh/chị cho em xếp một buổi lái thử nhé?",
    "Vâng ạ. Vậy mình lái thử một vòng cho chắc anh/chị nhé?",
    "Dạ tốt quá ạ. Em đặt lịch để anh/chị trải nghiệm thực tế nhé?",
    "Dạ vâng. Anh/chị muốn em sắp xếp buổi lái thử luôn không ạ?",
    "Em rất vui ạ. Vậy em giữ cho anh/chị một buổi lái thử nhé?",
    "Dạ được ạ. Anh/chị cầm lái thử mẫu này một vòng nhé?",
    "Vâng ạ, vậy em xếp lịch lái thử cho anh/chị luôn nhé?",
)


def post_pitch_decision_question(seed: str = "") -> str:
    """Câu hỏi hai lối: đặt lịch lái thử, hay còn điều gì cần làm rõ."""

    return pick_variant(POST_PITCH_DECISION_BODIES, seed)
