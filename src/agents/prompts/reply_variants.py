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


def post_pitch_question(seed: str = "") -> str:
    """Câu mời khách chọn một mẫu sau khi đã đề xuất.

    Không còn biến thể "xin quãng đường" (Sếp 2026-08-26): bảng chi phí giờ chạy
    được với mốc mặc định 30 km/ngày và tự nói ra mốc đó, nên không lượt nào phải
    dừng lại để xin một con số chiếm chưa tới 9% tổng tiền.
    """

    return pick_variant(POST_PITCH_VARIANTS, seed)


# ── Chặng SAU khi khách đã chốt một mẫu ──────────────────────────────────────
#
# Sếp 2026-08-26. Mỗi chặng một bộ câu riêng vì chúng chờ những câu trả lời KHÁC
# hẳn nhau — xem `domain/post_pitch`. Dùng chung một bộ thì lượt sau không biết
# khách đang đáp câu nào.

#: Hỏi khách còn băn khoăn gì về mẫu đã chọn.
#:
#: Mỗi biến thể phải nêu RÕ HAI LỐI ("còn thắc mắc" / "đã ổn"), vì
#: `domain/concern_reply` đọc câu đáp theo đúng hai lối đó. Câu hỏi mở trống
#: không thì khách đáp kiểu gì cũng được, và bộ đọc trả `UNCLEAR` — rồi agent
#: hỏi lại, thành vòng.
CONCERN_QUESTION_BODIES: Final[tuple[str, ...]] = (
    "Anh/chị còn băn khoăn gì về mẫu này không ạ? Còn điều gì chưa rõ thì anh/chị cứ nói, "
    "còn nếu đã ưng rồi thì em hướng dẫn bước tiếp theo ạ.",
    "Với mẫu này anh/chị thấy đã ổn chưa ạ? Có chỗ nào anh/chị muốn hỏi thêm thì em giải đáp, "
    "không thì mình đi tiếp bước sau nhé ạ.",
    "Anh/chị có điều gì còn lăn tăn về mẫu này không ạ? Anh/chị cứ nêu ra để em làm rõ, "
    "hoặc bảo em một tiếng là đã ổn thì em sang bước tiếp ạ.",
    "Mẫu này có chỗ nào anh/chị chưa hài lòng không ạ? Còn vướng gì thì anh/chị nói em nghe, "
    "còn nếu ổn rồi thì em mời anh/chị bước tiếp theo ạ.",
    "Anh/chị xem còn thắc mắc gì về xe này nữa không ạ? Có thì em giải đáp ngay, chưa có thì mình đi tiếp cũng được ạ.",
    "Về mẫu này anh/chị đã nắm đủ thông tin chưa ạ? Còn thiếu gì anh/chị cứ hỏi em, "
    "đủ rồi thì em hướng dẫn bước tiếp theo nhé.",
    "Anh/chị còn điều gì cần em làm rõ về mẫu này không ạ? Nói em nghe cũng được, "
    "mà thấy ổn rồi thì mình sang bước sau ạ.",
    "Anh/chị thấy mẫu này thế nào ạ? Còn chỗ nào chưa yên tâm thì em giải thích thêm, "
    "còn nếu đã ưng thì em mời anh/chị bước tiếp ạ.",
)

#: Mời đăng ký lái thử. Sếp: "hỏi ít thông tin khách ở đây thôi".
#:
#: Nên mỗi biến thể chỉ xin ĐÚNG một thứ — thời gian thuận tiện. Tên mẫu đã biết
#: (khách vừa chốt), showroom hệ tự đề nghị theo vị trí. Xin thêm là làm dài đúng
#: cái bước lẽ ra phải nhẹ nhất.
TEST_DRIVE_INVITE_BODIES: Final[tuple[str, ...]] = (
    "Anh/chị có muốn đăng ký lái thử mẫu này không ạ? Em chỉ cần biết anh/chị rảnh khoảng "
    "thời gian nào là sắp lịch được ngay.",
    "Em mời anh/chị trải nghiệm thực tế mẫu này nhé? Anh/chị cho em biết buổi nào thuận tiện, em lo phần còn lại ạ.",
    "Anh/chị muốn lái thử xe trước khi quyết định không ạ? Chỉ cần anh/chị nói giúp em khung thời gian rảnh là xong ạ.",
    "Ngồi thử xe một vòng rồi quyết cho chắc anh/chị nhé? Anh/chị rảnh hôm nào thì báo em, em giữ chỗ giúp ạ.",
    "Anh/chị có muốn em xếp một buổi lái thử không ạ? Em chỉ xin anh/chị thời gian thuận tiện thôi ạ.",
    "Em đặt lịch lái thử cho anh/chị nhé? Anh/chị cho em biết ngày giờ tiện nhất là được ạ.",
    "Anh/chị muốn cầm lái thử mẫu này chứ ạ? Nói em nghe anh/chị rảnh lúc nào, em sắp xếp ngay.",
    "Trước khi chốt, anh/chị lái thử một vòng cho chắc nhé? Anh/chị chỉ cần cho em khung giờ rảnh ạ.",
)

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
#: Câu hỏi ngay sau khi khách CHỌN một mẫu.
#:
#: Sếp 2026-08-27 dựng lại thứ tự: xem xe → hỏi han về xe → khi nào khách muốn
#: thì mới tính tiền → rồi mới mời lái thử. Nên câu này KHÔNG mời lái thử và
#: KHÔNG kèm bảng chi phí; nó chỉ mở đúng hai lối mà khách đang cần ở đó: nói ra
#: điều còn cân nhắc, hoặc hỏi thêm về chính chiếc xe vừa xem.
#:
#: Mở bằng một câu chúc mong sản phẩm hợp ý — Sếp đọc mẫu "viết 1 câu hy vọng
#: sản phẩm này đáp ứng được nhu cầu của Quý khách".
#:
#: NÊU ĐÍCH DANH cả hai lối, kể cả lối tính chi phí (Sếp làm rõ 2026-08-27). Câu
#: mở trống ("còn cân nhắc gì không") bắt khách tự nghĩ ra rằng họ được xin bảng
#: chi phí — mà bảng đó là thứ giúp họ quyết. Nói ra tên nó thì khách chỉ cần
#: gật, và `offer_reply.asks_for_cost_estimate` bắt được ngay.
POST_PITCH_AFTER_CHOICE_BODIES: Final[tuple[str, ...]] = (
    "Hy vọng mẫu này đáp ứng được nhu cầu của Quý khách ạ. "
    "Anh/chị còn thắc mắc gì về mẫu này không, hay để em tính chi phí lăn bánh "
    "cho anh/chị tiện ước chừng ạ?",
    "Em hy vọng chiếc này hợp với nhu cầu của anh/chị ạ. "
    "Anh/chị có gì muốn hỏi thêm về xe không, hay em tính luôn chi phí lăn bánh ạ?",
    "Mong là mẫu này đúng thứ anh/chị đang tìm ạ. "
    "Anh/chị còn điều gì cần em làm rõ về xe không, hay mình xem qua chi phí lăn bánh luôn ạ?",
    "Hy vọng chiếc xe này phục vụ tốt nhu cầu của anh/chị ạ. "
    "Anh/chị còn băn khoăn gì về mẫu này không, hay để em ước tính chi phí lăn bánh giúp anh/chị ạ?",
    "Em mong mẫu này hợp ý anh/chị ạ. "
    "Anh/chị cứ hỏi thêm nếu còn gì chưa rõ về xe, hoặc em tính chi phí lăn bánh cho anh/chị xem nhé?",
    "Hy vọng đây là mẫu anh/chị ưng ạ. "
    "Anh/chị muốn hỏi thêm gì về xe, hay em tính chi phí lăn bánh để anh/chị dễ hình dung ạ?",
)

#: Mời LÁI THỬ, đặt ngay dưới bảng chi phí (Sếp 2026-08-27).
#:
#: Bảng số vừa đưa ra là lúc khách đã xem xe, đã hỏi xong, đã biết tốn bao
#: nhiêu — chỗ tự nhiên nhất để mời cầm lái. Trước đây lời mời này đứng ngay sau
#: khi chọn xe, tức mời trải nghiệm khi khách còn chưa kịp hỏi gì.
POST_PITCH_AFTER_COST_BODIES: Final[tuple[str, ...]] = (
    "Anh/chị có muốn em đặt lịch lái thử mẫu này không ạ?",
    "Em xếp cho anh/chị một buổi lái thử nhé?",
    "Anh/chị muốn cầm lái thử một vòng chứ ạ?",
    "Em mời anh/chị trải nghiệm thực tế mẫu này nhé?",
    "Anh/chị có muốn đặt lịch lái thử không ạ?",
    "Em giữ cho anh/chị một buổi lái thử nhé?",
)

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


#: Báo đã chuyển tư vấn viên khi khách còn băn khoăn.
#:
#: Mỗi biến thể phải nói RÕ chuyện gì đang xảy ra và khách cần làm gì (không cần
#: làm gì). "Đã chuyển" mà không nói tiếp thì khách ngồi nhìn màn hình im.
HITL_HANDOVER_BODIES: Final[tuple[str, ...]] = (
    "Dạ em ghi nhận băn khoăn của anh/chị và đã chuyển sang tư vấn viên để được hỗ trợ kỹ hơn. "
    "Anh/chị chờ em chút nhé, có ưu đãi phù hợp em báo lại ngay ạ.",
    "Phần này em xin phép nhờ tư vấn viên hỗ trợ anh/chị cho chắc ạ. Anh/chị đợi em một lát, "
    "có thông tin em quay lại ngay.",
    "Em đã chuyển thắc mắc của anh/chị tới tư vấn viên rồi ạ. Anh/chị nghỉ tay chút, "
    "bên em xem có chính sách nào phù hợp rồi báo lại nhé.",
    "Dạ để tư vấn viên trao đổi trực tiếp với anh/chị cho rõ ạ. Em đã gửi thông tin sang, "
    "anh/chị chờ em một chút thôi.",
    "Em nhờ tư vấn viên xem giúp trường hợp của anh/chị ạ. Có phương án em báo lại anh/chị ngay.",
    "Dạ em chuyển anh/chị sang tư vấn viên để được giải đáp cặn kẽ hơn. Anh/chị đợi em chút xíu nhé.",
    "Em đã báo tư vấn viên về băn khoăn của anh/chị rồi ạ. Anh/chị chờ em một lát, có gì em nhắn lại ngay.",
    "Chỗ này để tư vấn viên hỗ trợ anh/chị sẽ nhanh hơn ạ. Em đã chuyển thông tin, anh/chị chờ em chút nhé.",
)

#: Hỏi lại khi câu trả lời cho câu hỏi HAI LỐI không đọc được.
#:
#: Bốn kết quả chứ không phải hai (`domain/concern_reply.PostPitchDecision`):
#: "cũng được" không nói lên khách muốn lái thử hay đang ngần ngại. Đoán hộ là
#: đẩy họ đi sai nhánh.
#:
#: Câu hỏi lại phải NÊU LẠI CẢ HAI LỐI, y như câu gốc. Bản trước chỉ hỏi "còn chỗ
#: nào chưa yên tâm, hay mình sang bước sau ạ?" — vế thứ hai không có tên, nên
#: khách vẫn không biết "bước sau" là gì và lại đáp một câu không đọc được.
CONCERN_CLARIFY_BODIES: Final[tuple[str, ...]] = (
    "Dạ em chưa rõ ý anh/chị. Anh/chị muốn em đặt lịch lái thử, hay còn điều gì cần em làm rõ ạ?",
    "Em xin phép hỏi lại cho rõ ạ: mình đặt lịch lái thử nhé, hay anh/chị còn thắc mắc gì ạ?",
    "Dạ anh/chị nói rõ giúp em chút ạ — anh/chị muốn lái thử xe, hay còn chỗ nào chưa yên tâm ạ?",
    "Em chưa nắm được ý anh/chị ạ. Anh/chị cho em xếp buổi lái thử nhé, hay còn gì vướng em gỡ giúp ạ?",
    "Dạ cho em hỏi lại ạ: em đặt lịch lái thử cho anh/chị, hay anh/chị cần em làm rõ thêm điều gì ạ?",
    "Em muốn chắc ý anh/chị ạ — mình lái thử một vòng nhé, hay còn băn khoăn gì anh/chị nói em nghe ạ?",
    "Dạ em hỏi lại cho chắc: anh/chị muốn trải nghiệm thử xe, hay còn câu hỏi nào về mẫu này ạ?",
    "Anh/chị cho em biết rõ hơn nhé — mình đặt lịch lái thử, hay còn điều gì anh/chị chưa ưng ạ?",
)


def concern_question(seed: str = "") -> str:
    """Hỏi khách còn băn khoăn gì về mẫu đã chốt.

    Giữ lại cho các đường gọi cũ; luồng chính dùng `post_pitch_decision_question`.
    """

    return pick_variant(CONCERN_QUESTION_BODIES, seed)


def post_pitch_decision_question(seed: str = "") -> str:
    """Câu hỏi hai lối: đặt lịch lái thử, hay còn điều gì cần làm rõ."""

    return pick_variant(POST_PITCH_DECISION_BODIES, seed)


def post_pitch_after_choice(seed: str = "") -> str:
    """Câu ngay sau khi khách chọn mẫu — chúc hợp ý, rồi mở hai lối hỏi/cân nhắc."""

    return pick_variant(POST_PITCH_AFTER_CHOICE_BODIES, seed)


def post_pitch_after_cost(seed: str = "") -> str:
    """Mời lái thử, đặt ngay dưới bảng chi phí."""

    return pick_variant(POST_PITCH_AFTER_COST_BODIES, seed)


def confirm_test_drive(seed: str = "") -> str:
    """Khách đã hết vướng nhưng chưa nhận lời lái thử → mời nốt nửa còn lại."""

    return pick_variant(POST_PITCH_CONFIRM_TEST_DRIVE_BODIES, seed)


def test_drive_invite(seed: str = "") -> str:
    """Mời đăng ký lái thử."""

    return pick_variant(TEST_DRIVE_INVITE_BODIES, seed)


def hitl_handover_notice(seed: str = "") -> str:
    """Báo đã chuyển tư vấn viên."""

    return pick_variant(HITL_HANDOVER_BODIES, seed)


def concern_clarify(seed: str = "") -> str:
    """Hỏi lại khi câu trả lời về băn khoăn không rõ."""

    return pick_variant(CONCERN_CLARIFY_BODIES, seed)
