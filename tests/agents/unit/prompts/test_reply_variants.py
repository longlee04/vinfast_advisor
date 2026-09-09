"""Lời chào / lời từ chối phải đổi cách nói giữa các phiên, mà không đổi nghĩa.

Đo trên prod 2026-08-26 (Sếp: "lặp lại liên tục như vậy cũng hơi tệ"): lời chào
lặp y nguyên 27 lần, lời từ chối 28 lần. `question_variants` đã có biến thể
nhưng chọn theo `retry_count`, mà mỗi phiên mới đều bắt đầu từ 0 — nên nó chỉ
chống lặp TRONG một hội thoại.
"""

from __future__ import annotations

import pytest

from src.agents.domain.values import ScopeLabel, SlotName
from src.agents.prompts.reply_variants import (
    FEATURE_QUESTION_BODIES,
    FOREIGN_DOMAIN_ANCHOR,
    FOREIGN_DOMAIN_VARIANTS,
    POST_PITCH_CONFIRM_TEST_DRIVE_BODIES,
    POST_PITCH_DECISION_BODIES,
    POST_PITCH_VARIANTS,
    SOCIAL_VARIANTS,
    feature_question_body,
    foreign_domain_parts,
    foreign_domain_reply,
    pick_variant,
    social_reply,
)

_SESSIONS = [
    "77777777-7777-7777-7777-777777777777",
    "11111111-1111-1111-1111-111111111111",
    "abc-def-ghi",
    "",
]


# ── Chọn biến thể phải TẤT ĐỊNH ──────────────────────────────────────────────


@pytest.mark.parametrize("seed", _SESSIONS)
def test_cung_mot_phien_luon_ra_cung_mot_cau(seed: str) -> None:
    """Khách nhắn lại trong cùng phiên phải gặp cùng lời chào — đổi câu giữa
    chừng đọc như hai người khác nhau đang trả lời."""

    assert social_reply(seed) == social_reply(seed)
    assert foreign_domain_reply(seed) == foreign_domain_reply(seed)


def test_khong_dung_hash_dung_san_cua_python() -> None:
    """`hash()` của chuỗi phụ thuộc `PYTHONHASHSEED` ngẫu nhiên mỗi tiến trình:
    cùng một phiên sẽ nhận câu khác nhau sau mỗi lần restart backend, và test thì
    đỏ ngẫu nhiên. Giá trị dưới đây được chốt cứng — nó chỉ đúng nếu hàm chọn
    dùng một hàm băm ổn định."""

    assert pick_variant(("a", "b", "c"), "77777777-7777-7777-7777-777777777777") == "c"
    assert pick_variant(("a", "b", "c"), "11111111-1111-1111-1111-111111111111") == "b"


def test_seed_rong_ve_bien_the_dau() -> None:
    """Chỗ gọi chưa có danh tính phiên vẫn chạy đúng như trước, không vỡ."""

    assert social_reply("") == SOCIAL_VARIANTS[0]
    assert foreign_domain_parts("") == FOREIGN_DOMAIN_VARIANTS[0]


def test_cac_phien_khac_nhau_khong_don_het_ve_mot_cau() -> None:
    """Có biến thể mà mọi phiên vẫn ra một câu thì công sức thành vô nghĩa."""

    seen = {social_reply(f"phien-{index}") for index in range(60)}

    assert len(seen) == len(SOCIAL_VARIANTS)


# ── Đổi cách nói, KHÔNG đổi nghĩa ────────────────────────────────────────────


@pytest.mark.parametrize("variant", FOREIGN_DOMAIN_VARIANTS)
def test_moi_bien_the_tu_choi_giu_cum_bat_bien(variant: tuple[str, str]) -> None:
    """Phần nghiệp vụ của lời từ chối — giới hạn nằm ở dữ liệu đã xác minh —
    không được biến mất khi ai đó viết thêm biến thể cho hay hơn."""

    limitation, _escape = variant

    assert FOREIGN_DOMAIN_ANCHOR in limitation


@pytest.mark.parametrize("variant", FOREIGN_DOMAIN_VARIANTS)
def test_moi_bien_the_tu_choi_deu_mo_loi_di_tiep(variant: tuple[str, str]) -> None:
    """Từ chối mà không chỉ đường là đẩy khách vào ngõ cụt. Mỗi biến thể phải nêu
    được việc làm được VÀ lối gặp tư vấn viên."""

    _limitation, escape = variant

    assert "tư vấn viên" in escape
    assert "chọn xe" in escape or "giá" in escape


@pytest.mark.parametrize("variant", SOCIAL_VARIANTS)
def test_moi_loi_chao_deu_moi_khach_noi_tiep(variant: str) -> None:
    """Sếp 2026-08-26: "dài hơn 1 chút thì tốt". Bản cũ một câu cụt đọc như dòng
    trạng thái. Lời chào không có lối đi tiếp thì khách phải tự nghĩ ra câu hỏi —
    đó là lúc hội thoại chết."""

    assert variant.rstrip().endswith("?")
    assert len(variant) >= 120


@pytest.mark.parametrize("variant", SOCIAL_VARIANTS)
def test_moi_loi_chao_deu_ke_duoc_viec_lam_duoc(variant: str) -> None:
    assert "chọn xe" in variant or "tư vấn" in variant


def test_cac_bien_the_khong_trung_nhau() -> None:
    assert len(set(SOCIAL_VARIANTS)) == len(SOCIAL_VARIANTS)
    assert len(set(FOREIGN_DOMAIN_VARIANTS)) == len(FOREIGN_DOMAIN_VARIANTS)


# ── Hai đường ra cùng một câu ────────────────────────────────────────────────


@pytest.mark.parametrize("seed", _SESSIONS)
def test_hai_cua_dong_luot_phai_cho_cung_mot_loi_tu_choi(seed: str) -> None:
    """Lượt có thể bị đóng ở cửa tất định (`names_foreign_domain`) hoặc ở nhãn
    của bộ phân loại. Hai đường phải ra ĐÚNG một câu, nếu không khách gặp hai lời
    từ chối khác nhau cho cùng một tình huống — sai lặng lẽ.

    Ghép bằng KHOẢNG TRẮNG vì `ScopeDecision.user_response` dùng
    `f"{limitation} {escape_route}"`. Lệch một ký tự là lệch cả câu.
    """

    from src.agents.domain.scope import decision_for

    decision = decision_for(label=ScopeLabel.OUT_OF_SCOPE, utterance="tư vấn cho tôi mua cổ phiếu", seed=seed)

    assert decision.user_response == foreign_domain_reply(seed)


# ── Thân câu hỏi tính năng: đa dạng câu chữ, CỐ ĐỊNH cấu trúc ────────────────


@pytest.mark.parametrize("body", FEATURE_QUESTION_BODIES)
def test_than_cau_hoi_tinh_nang_luon_ket_bang_dau_hoi(body: str) -> None:
    """Dòng dẫn không có dấu hỏi thì danh sách ngay dưới đọc như một lời liệt kê,
    không như một câu hỏi đang chờ trả lời."""

    assert body.rstrip().endswith("?")


@pytest.mark.parametrize("body", FEATURE_QUESTION_BODIES)
def test_than_cau_hoi_tinh_nang_khong_tu_dung_danh_sach(body: str) -> None:
    """Sếp 2026-08-26: "chỗ thì có đánh highlight in đậm chỗ thì viết liền nhưng
    gạch đầu dòng ở cùng dòng". Danh sách do CODE dựng (`candidate_tuning.ask`),
    một mục một dòng. Thân câu lén mang gạch đầu dòng hay dấu in đậm là dựng hai
    danh sách chồng nhau — đúng thứ format lộn xộn việc này đi chữa.
    """

    assert "\n" not in body
    assert "- " not in body
    assert "**" not in body


def test_than_cau_hoi_tinh_nang_doi_theo_phien() -> None:
    seen = {feature_question_body(f"phien-{index}") for index in range(60)}

    assert len(seen) == len(FEATURE_QUESTION_BODIES)


# ── Seed phải đi HẾT đường, không chỉ tới hàm ngoài cùng ─────────────────────


def test_seed_di_toi_duoc_duong_hoi_chinh() -> None:
    """`question_for_turn` là đường CHÍNH của luồng hỏi slot, không phải
    `question_for`.

    Bản nối đầu tiên chỉ truyền seed vào `question_for`, nên mọi lượt thật vẫn ra
    biến thể `[0]` — đo bằng cách chạy lại câu khách thật từ log prod: ba phiên
    khác nhau cùng ra một câu. Test đơn vị của `get_question_variant` vẫn xanh vì
    nó gọi thẳng hàm, không đi qua đường thật.

    Bài học: test khoá HÀM không thay được test khoá ĐƯỜNG ĐI.
    """

    from src.agents.services.slot_planning import SlotPlanningServiceImpl

    planner = SlotPlanningServiceImpl()
    asked = {
        planner.question_for_turn(
            slot=SlotName.VEHICLE_TYPE,
            retry_count=0,
            user_message="anh muốn tư vấn",
            vehicle_mentions=[],
            seed=f"phien-{index}",
        )
        for index in range(60)
    }

    assert len(asked) > 1, "seed không đi tới được `question_for_turn` — mọi phiên ra cùng một câu"


# ── Số biến thể: đủ để không lặp sớm ─────────────────────────────────────────

MIN_VARIANTS = 8


def test_moi_bang_bien_the_du_so_luong() -> None:
    """Sếp 2026-08-26: nâng từ ba lên tám mỗi loại.

    Ba biến thể nghĩa là phiên thứ tư lặp lại câu của phiên thứ nhất. Tám thì
    khoảng lặp đủ xa để một khách quay lại vài lần vẫn thấy câu mới. Vẫn là bảng
    TĨNH — rẻ, tất định, và không mô hình nào phá được cấu trúc.

    Số này là SÀN, không phải trần: thêm biến thể chỉ cần thêm chuỗi vào tuple.
    """

    from src.agents.prompts.question_variants import QUESTION_VARIANTS, ROUTING_VARIANTS

    thieu = {
        "SOCIAL": len(SOCIAL_VARIANTS),
        "FOREIGN_DOMAIN": len(FOREIGN_DOMAIN_VARIANTS),
        "FEATURE_QUESTION": len(FEATURE_QUESTION_BODIES),
        "POST_PITCH": len(POST_PITCH_VARIANTS),
        "POST_PITCH_DECISION": len(POST_PITCH_DECISION_BODIES),
        "POST_PITCH_CONFIRM_TEST_DRIVE": len(POST_PITCH_CONFIRM_TEST_DRIVE_BODIES),
        "ROUTING": len(ROUTING_VARIANTS),
        **{slot.value: len(variants) for slot, variants in QUESTION_VARIANTS.items()},
    }

    assert {ten: so for ten, so in thieu.items() if so < MIN_VARIANTS} == {}


def test_bien_the_trong_cung_mot_bang_khong_trung_nhau() -> None:
    """Hai biến thể giống hệt nhau làm khoảng lặp ngắn lại mà không ai thấy."""

    from src.agents.prompts.question_variants import QUESTION_VARIANTS, ROUTING_VARIANTS

    trung = {
        ten: bang
        for ten, bang in {
            "SOCIAL": SOCIAL_VARIANTS,
            "FEATURE_QUESTION": FEATURE_QUESTION_BODIES,
            "POST_PITCH": POST_PITCH_VARIANTS,
            "POST_PITCH_DECISION": POST_PITCH_DECISION_BODIES,
            "POST_PITCH_CONFIRM_TEST_DRIVE": POST_PITCH_CONFIRM_TEST_DRIVE_BODIES,
            "ROUTING": ROUTING_VARIANTS,
            **{slot.value: variants for slot, variants in QUESTION_VARIANTS.items()},
        }.items()
        if len(set(bang)) != len(bang)
    }

    assert trung == {}


# ── Câu mời khách đi tiếp sau pitch ──────────────────────────────────────────


@pytest.mark.parametrize("variant", POST_PITCH_VARIANTS)
def test_cau_moi_sau_pitch_phai_la_cau_hoi(variant: str) -> None:
    """Không có dấu hỏi thì nó thành lời chốt hạ, và khách không biết mình được
    mời nói tiếp."""

    assert "?" in variant


@pytest.mark.parametrize("variant", POST_PITCH_VARIANTS)
def test_cau_moi_sau_pitch_luon_xin_ten_mau(variant: str) -> None:
    """Sếp 2026-08-26: "cho em tên mẫu mình chọn". Không xin tên mẫu thì câu trả
    lời của khách không dẫn tới việc gì tiếp được."""

    assert "mẫu" in variant.casefold()


@pytest.mark.parametrize("variant", POST_PITCH_DECISION_BODIES)
def test_cau_hai_loi_phai_neu_ten_ca_hai_loi(variant: str) -> None:
    """Sếp 2026-08-26: gộp "còn băn khoăn gì" và "mời lái thử" thành MỘT câu.

    Gộp chỉ ăn tiền khi câu hỏi NÊU TÊN cả hai lối — `classify_post_pitch_decision`
    đọc câu đáp theo đúng hai lối đó. Một câu mở trống ("anh/chị thấy sao ạ?") thì
    khách đáp kiểu gì cũng được và bộ đọc trả `UNCLEAR`, rồi agent hỏi lại: đúng
    cái vòng mà việc gộp sinh ra để phá.
    """

    thap = variant.casefold()
    assert "lái thử" in thap or "cầm lái" in thap or "trải nghiệm" in thap
    assert any(cum in thap for cum in ("làm rõ", "thắc mắc", "lăn tăn", "băn khoăn", "chưa rõ", "chưa yên tâm"))


@pytest.mark.parametrize("variant", POST_PITCH_CONFIRM_TEST_DRIVE_BODIES)
def test_moi_lai_thu_lan_hai_khong_hoi_lai_dieu_khach_vua_tra_loi(variant: str) -> None:
    """Khách đã nói HẾT vướng thì chỉ hỏi nốt nửa còn thiếu.

    Nhắc lại "còn băn khoăn gì không" ở đây là bắt họ trả lời lại điều vừa nói.
    """

    thap = variant.casefold()
    assert "?" in variant
    assert not any(cum in thap for cum in ("băn khoăn", "thắc mắc", "lăn tăn"))
