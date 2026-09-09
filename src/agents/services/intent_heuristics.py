"""Cửa TẤT ĐỊNH cho lời xin gặp tư vấn viên.

File này từng chở cả một lớp phủ cho bộ định tuyến cũ (`normalize_router_output`:
chửi bậy → HITL, HUMAN_REQUEST, TRANSACTION_REQUEST). Lớp đó đi cùng
`LLMPort.classify_intent`, mà đường ấy KHÔNG còn ai gọi trong luồng sống — chỉ
còn một forwarder và một protocol không ai cài. Đọc code thấy một lớp an toàn
đầy đủ nằm đây là hiểu sai hệ đang được bảo vệ tới đâu, nên nó bị gỡ.

Còn lại đúng phần đang chạy thật: `is_direct_human_request`, gọi từ
`services/scope_classifier` và `services/quote_gate`.
"""

from __future__ import annotations

import re
import unicodedata

from src.agents.domain.canonical_text import CanonicalText


def is_direct_human_request(message: str, canonical: CanonicalText) -> bool:
    """Return whether the customer explicitly asks for a human advisor.

    So trên `canonical.folded` — gate không tự normalize (ENG REVIEW AMENDMENT 2).
    """

    return _detect_intent(canonical.folded) == "HUMAN_REQUEST"


def _detect_intent(text: str) -> str:
    if any(
        marker in text for marker in ("chat voi bot", "chat tiep voi bot", "quay lai voi bot", "noi chuyen voi bot")
    ):
        return "OTHER"
    if any(
        marker in text
        for marker in (
            "advisor",
            "tu van vien",
            "tu van truc tiep",
            "nhan vien",
            "nguoi that",
            "goi lai",
            "ket noi toi voi sale",
            "ket noi voi sale",
            "ket noi sale",
            "ket noi advisor",
            "gap sale",
            "gap advisor",
            "cho toi gap",
            "chuyen tu van",
            "chuyen advisor",
            "ho tro vien",
            "tong dai vien",
            "quan tri vien",
            "quan tri",
            "admin",
            "chuyen sang tu van",
            "chuyen sang tu van vien",
            "chuyen qua tu van vien",
            "chuyen cho tu van vien",
            "chuyen den tu van vien",
            "chuyen sang nguoi that",
            "gap tu van",
            "gap tu van vien",
            "gap quan tri",
            "gap quan tri vien",
            "gap admin",
            "gap nhan vien",
            "gap chuyen vien",
            "chuyen vien",
            "ho tro truc tiep",
            "noi chuyen voi nguoi that",
            "noi chuyen voi tu van vien",
            "noi chuyen voi nhan vien",
            "noi chuyen voi sale",
            "can gap nguoi",
            "can gap tu van",
            "can gap sale",
            "can gap nhan vien",
            "chuyen may",
            "gap tong dai vien",
            "lien he tu van vien",
            "lien he nhan vien",
            "lien he sale",
            "lien he quan tri vien",
        )
    ):
        return "HUMAN_REQUEST"
    if any(
        marker in text
        for marker in (
            "dat coc",
            "ky hop dong",
            "thanh toan",
            "thu tuc mua",
            "chot chiec",
            "chot xe",
            "dat xe ngay",
            "dat vf",
            "mua ngay",
            "mua xe nay",
            "muon dat coc",
        )
    ):
        return "TRANSACTION_REQUEST"
    if any(
        marker in text
        for marker in (
            "voucher nay",
            "ap dung cho xe",
            "truong hop cua toi",
            "cua toi co duoc",
            "hoan coc",
            "duoc bao hanh cho",
            "duoc cong 2 voucher",
            "dung duoc cho vf",
            "dung duoc cho xe",
        )
    ):
        return "POLICY_APPLICATION"
    if any(
        marker in text
        for marker in (
            "chinh sach",
            "bao hanh",
            "thu cu doi moi",
            "voucher song xanh",
            "voucher la gi",
            "uu dai",
            "ho tro",
            "sac pin",
            "mien phi sac",
        )
    ):
        return "POLICY_QUERY"
    if any(marker in text for marker in ("so sanh", "khac nhau")):
        return "COMPARISON"

    has_model = bool(
        re.search(r"\b(vf\s*\d+|evo\s*\d+|feliz|klara|vento|theon|vero|viper)\b", text, flags=re.IGNORECASE)
    )
    has_pronoun = bool(
        re.search(
            r"\b(xe nay|con nay|mau nay|chiec nay|xe do|con do|mau do|chiec do|em nay|em do|chiec xe nay|con xe nay|\d+\s*con\s*xe|\d+\s*xe|\d+\s*mau\s*xe|cac\s*con\s*xe|nhung\s*con\s*xe|cac\s*xe|nhung\s*xe|cac\s*mau\s*xe|nhung\s*mau\s*xe|cac\s*mau\s*nay|cac\s*xe\s*nay|\d+\s*con\s*xe\s*nay|\d+\s*xe\s*nay|nhung\s*xe\s*tren|cac\s*xe\s*tren|\d+\s*con\s*xe\s*toi\s*muon\s*mua|cac\s*xe\s*toi\s*muon\s*mua|\d+\s*xe\s*toi\s*muon\s*mua)\b",
            text,
            flags=re.IGNORECASE,
        )
    )
    if (has_model or has_pronoun) and any(
        marker in text
        for marker in (
            "tu van",
            "chi tiet",
            "thong tin",
            "sau hon",
            "hoi ve",
            "ve xe",
            "nhu the nao",
            "the nao",
            "ra sao",
            "co nhung gi",
            "gia",
            "thong so",
            "tam chay",
            "pin",
            "sac",
            "muon mua",
            "can mua",
            "mua xe",
            "muon xem",
            "xem xe",
        )
    ):
        return "VEHICLE_INFO"

    if any(marker in text for marker in ("tra cuu", "thong so", "gia bao nhieu", "tam chay", "pin bao")):
        return "VEHICLE_INFO"
    if any(
        marker in text
        for marker in (
            "muon mua o to",
            "muon mua xe",
            "can mua",
            "muon mua",
            "tu van chon",
            "xe phu hop",
            "can xe",
            "tim o to",
            "tim xe",
            "ngan sach",
            "di lam",
            "gia dinh",
            "trieu",
            "ty",
            "ti",
            "cho",
        )
    ):
        return "VEHICLE_DISCOVERY"
    if any(
        marker in text
        for marker in ("khong hieu", "tra loi sai", "rat buc", "tu van kieu gi", "may goi sale", "hoi mai", "chan qua")
    ):
        return "COMPLAINT"
    return "OTHER"


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_marks.replace("đ", "d")
