from __future__ import annotations

import pytest

from src.agents.domain.claim_policy import plan_claims, reject_unstructured_claims
from src.agents.prompts.feature_askable import FEATURE_DISPLAY_LABELS


def test_over_budget_reason_never_becomes_an_in_budget_claim() -> None:
    claims = plan_claims(["[slot=budget_max_vnd] Vượt ngân sách 526.667%"])

    assert len(claims) == 1
    assert claims[0].slot == "budget_max_vnd"
    assert "cao hơn ngân sách" in claims[0].text
    assert "nằm trong ngân sách" not in claims[0].text


def test_within_budget_reason_keeps_the_positive_claim() -> None:
    claims = plan_claims(["[slot=budget_max_vnd] Giá nằm trong ngân sách đã xác nhận"])

    assert len(claims) == 1
    assert "nằm trong ngân sách" in claims[0].text


def test_claim_texts_never_use_the_ban_persona() -> None:
    """Persona (xưng "em", gọi "anh/chị") — claim nói "bạn" là lệch giọng
    với toàn bộ phần còn lại của hội thoại."""

    claims = plan_claims(
        [
            "[slot=vehicle_type] đúng loại xe",
            "[slot=budget_max_vnd] trong ngân sách",
            "[slot=passenger_count] đủ chỗ",
            "[slot=required_range_km] đủ tầm",
            "[slot=home_charging] sạc tại nhà",
            "[slot=purpose] đúng mục đích",
            "[slot=max_load_kg] đủ tải",
            "[slot=habit_need_tags] đúng thói quen",
        ]
    )

    assert len(claims) == 8
    # Toàn hội thoại v2 xưng "em" — gọi khách "anh/chị". "bạn" là giọng bản cũ,
    # còn "Quý khách" là giọng nhánh build-agent ĐÃ LỘ nguyên văn ra prod
    # 2026-08-31 qua đường synthesis (không qua cửa `render.assert_clean`).
    # Không phải claim nào cũng NHẮC tới khách, nên chỉ chặn hai giọng sai.
    for claim in claims:
        assert "bạn" not in claim.text, claim
        assert "Quý khách" not in claim.text, claim


def test_multi_field_trace_from_need_tag_reason_still_produces_a_claim() -> None:
    """Bug có sẵn (Sếp 2026-08-21): `ScoringReason.render()` nối thêm
    `need_tag=`/`feature_code=`/`source=`/`evidence=` trước dấu `]` — pattern
    cũ chỉ khớp `[slot=x]` trơn nên need-tag/tài liệu chưa từng sinh claim."""

    claims = plan_claims(
        [
            "[slot=habit_need_tags; need_tag=URBAN_TRAFFIC; feature_code=PANORAMIC_ROOF; "
            "source=FLAG; evidence=vehicle_feature_flags:flag-1] Tính năng PANORAMIC_ROOF "
            "phù hợp nhu cầu URBAN_TRAFFIC"
        ]
    )

    assert len(claims) == 1
    assert claims[0].slot == "habit_need_tags"
    assert claims[0].placeholder == "CLAIM_PANORAMIC_ROOF"


def test_customer_confirmed_feature_gets_its_own_claim_text() -> None:
    """Sếp 2026-08-21: tính năng khách CHỦ ĐỘNG chọn ở lượt 2 phải có câu
    riêng — không dùng chung câu "phù hợp thói quen sử dụng" của need-tag."""

    claims = plan_claims(
        [
            "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; "
            "evidence=vehicle_feature_flags:flag-9] Có tính năng ANTI_THEFT mà "
            "khách vừa xác nhận quan tâm"
        ]
    )

    assert len(claims) == 1
    assert claims[0].placeholder == "CLAIM_ANTI_THEFT"
    assert "vừa xác nhận quan tâm" in claims[0].text
    assert "thói quen sử dụng" not in claims[0].text


def test_customer_confirmed_feature_claim_names_the_vietnamese_label() -> None:
    """Bug thật 2026-08-21 (Sếp báo): claim cũ chỉ nói chung chung "tính năng
    anh/chị vừa xác nhận quan tâm", không gọi tên — khách hỏi "khoá chống trộm
    thì sao" mà đề xuất không hề nhắc lại "khoá chống trộm". `scoring.py` giờ
    giải nhãn (`ScoringProfile.feature_mention_labels`) trước khi dựng message,
    claim phải LẤY ĐÚNG nhãn đó ra, không phải mã thô."""

    claims = plan_claims(
        [
            "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; "
            "evidence=vehicle_feature_flags:flag-9] Có tính năng khoá chống trộm mà "
            "khách vừa xác nhận quan tâm"
        ]
    )

    assert len(claims) == 1
    assert claims[0].text == "có đúng khoá chống trộm mà anh/chị vừa xác nhận quan tâm ở lượt trước"


def test_different_feature_codes_on_the_same_slot_each_get_a_claim() -> None:
    """Một candidate khớp nhiều feature khác nhau (need-tag) không bị gộp mất
    chỉ vì cùng `slot=habit_need_tags` — mỗi feature một claim riêng."""

    claims = plan_claims(
        [
            "[slot=habit_need_tags; feature_code=PANORAMIC_ROOF; source=FLAG; "
            "evidence=e1] Tính năng PANORAMIC_ROOF phù hợp nhu cầu URBAN_TRAFFIC",
            "[slot=habit_need_tags; feature_code=HIGH_PAYLOAD; source=FLAG; "
            "evidence=e2] Tính năng HIGH_PAYLOAD phù hợp nhu cầu FAMILY_LARGE",
        ]
    )

    assert {claim.placeholder for claim in claims} == {
        "CLAIM_PANORAMIC_ROOF",
        "CLAIM_HIGH_PAYLOAD",
    }


def test_same_feature_code_keeps_only_the_first_reason_seen() -> None:
    """Khách chọn ở lượt 2 VÀ need-tag cũng khớp cùng feature: `_score_candidate`
    đặt `_feature_mention_reasons` trước → lý do khách chủ động chọn thắng."""

    claims = plan_claims(
        [
            "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; "
            "evidence=e1] Có tính năng ANTI_THEFT mà khách vừa xác nhận quan tâm",
            "[slot=habit_need_tags; feature_code=ANTI_THEFT; source=FLAG; "
            "evidence=e2] Tính năng ANTI_THEFT phù hợp nhu cầu HIGHWAY_SAFETY",
        ]
    )

    assert len(claims) == 1
    assert "vừa xác nhận quan tâm" in claims[0].text


# ── Nhóm B (2026-08-26): câu tán dương mơ hồ không căn cứ ─────────────────────


@pytest.mark.parametrize(
    "prose",
    [
        "Xe vận hành mạnh mẽ và êm ái.",
        "Khoang lái rộng rãi thoáng đãng.",
        "Nội thất sang trọng.",
        "Xe tiết kiệm điện vượt trội.",
        "Xe an toàn tuyệt đối.",
    ],
)
def test_vague_praise_without_evidence_is_rejected(prose: str) -> None:
    with pytest.raises(ValueError):
        reject_unstructured_claims(prose)


@pytest.mark.parametrize("label", list(FEATURE_DISPLAY_LABELS.values()))
def test_feature_display_labels_never_trigger_unstructured_claim(label: str) -> None:
    """28 nhãn tính năng in nguyên văn trong prompt — dính mẫu nào là hỏng cả pitch."""

    reject_unstructured_claims(label)
