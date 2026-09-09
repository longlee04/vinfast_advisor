"""`normalize_customer_result` — output-boundary projection (Todo 9).

Mapper thuần, idempotent: project mọi trường văn xuôi khách nhìn thấy
(answer, pending_question, recommendations[].pitch, comparison.summary)
về dạng an toàn + đọc được, giữ nguyên mọi ID có cấu trúc.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest

from src.agents.contracts import (
    Citation,
    NearbyLocationListView,
    NearbyLocationView,
    QuickReplyView,
    RecommendedVehicleView,
    TurnResult,
    VehicleComparisonView,
    VehicleFacts,
)
from src.agents.domain.values import VehicleType
from src.agents.services.output_guard import normalize_customer_result

VEHICLE_ID = UUID("20000000-0000-0000-0000-000000000101")
EVIDENCE_ID = UUID("30000000-0000-0000-0000-000000000101")
REVIEW_ID = UUID("40000000-0000-0000-0000-000000000101")
RAW_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _recommendation(pitch: str = "VF 8 giá 1090000000 đồng.") -> RecommendedVehicleView:
    return RecommendedVehicleView(
        vehicle_id=VEHICLE_ID,
        rank=1,
        display_name="VF 8",
        image_url="https://cdn/vf8.png",
        starting_price_vnd="1090000000",
        pitch=pitch,
        citations=(Citation(index=1, evidence_id=EVIDENCE_ID, source_record="cars:row"),),
    )


def _result(**overrides: object) -> TurnResult:
    base = TurnResult(
        session_id="11111111-1111-1111-1111-111111111111",
        answer="VF 8 giá 1090000000 đồng.",
        pending_question=None,
    )
    return replace(base, **overrides)


def test_scrubs_evidence_and_source_markers() -> None:
    result = _result(answer=(f"Giá 1090000000 đồng [evidence_id:{RAW_UUID}] [source_record:cars:row]."))

    projected = normalize_customer_result(result)

    assert projected.answer == "Giá 1.090.000.000 đồng."
    assert "evidence_id" not in projected.answer
    assert "source_record" not in projected.answer
    assert RAW_UUID not in projected.answer


def test_scrubs_bare_uuid() -> None:
    result = _result(answer=f"Đã ghi nhận {RAW_UUID}.")

    projected = normalize_customer_result(result)

    assert projected.answer == "Đã ghi nhận."
    assert projected.answer is not None
    assert RAW_UUID not in projected.answer


def test_scrubs_provenance_markers() -> None:
    result = _result(answer="Xong [run_id:abc-123] [draft:true].")

    projected = normalize_customer_result(result)

    assert projected.answer == "Xong."
    assert projected.answer is not None
    assert "run_id" not in projected.answer
    assert "draft" not in projected.answer


def test_keeps_citation_footnotes_and_structured_ids() -> None:
    result = _result(
        answer="VF 8 đi 399 km [1].",
        review_id=REVIEW_ID,
        recommendations=[_recommendation()],
    )

    projected = normalize_customer_result(result)

    assert projected.answer == "VF 8 đi 399 km [1]."
    assert projected.review_id == REVIEW_ID
    item = projected.recommendations[0]
    assert item.vehicle_id == VEHICLE_ID
    assert item.citations[0].evidence_id == EVIDENCE_ID
    assert item.citations[0].source_record == "cars:row"
    assert item.display_name == "VF 8"
    assert item.image_url == "https://cdn/vf8.png"
    assert item.starting_price_vnd == "1090000000"


def test_voice_em_address_becomes_quy_khach() -> None:
    result = _result(answer="Em muốn mua xe nào ạ? Em đang phân vân giữa VF 6 và VF 8.")

    projected = normalize_customer_result(result)

    assert projected.answer == "anh/chị muốn mua xe nào ạ? anh/chị đang phân vân giữa VF 6 và VF 8."


def test_voice_keeps_bot_self_reference_em() -> None:
    result = _result(answer="Em xin phép chuyển câu hỏi tới tư vấn viên. Em sẽ gửi thông tin sau.")

    projected = normalize_customer_result(result)

    assert projected.answer == "Em xin phép chuyển câu hỏi tới tư vấn viên. Em sẽ gửi thông tin sau."


def test_voice_keeps_em_inside_compound_words() -> None:
    result = _result(answer="anh/chị xem thêm thông tin nhé.")

    assert normalize_customer_result(result).answer == "anh/chị xem thêm thông tin nhé."


def test_voice_keeps_bot_muon_giới_thiệu() -> None:
    result = _result(answer="Em muốn giới thiệu VF 8 cho anh/chị.")

    assert normalize_customer_result(result).answer == "Em muốn giới thiệu VF 8 cho anh/chị."


def test_quy_khach_case_normalized() -> None:
    result = _result(answer="quý khách vui lòng cho biết nhu cầu.")

    assert normalize_customer_result(result).answer == "anh/chị vui lòng cho biết nhu cầu."


def test_decimal_readable_with_fraction() -> None:
    result = _result(answer="Giá lăn bánh khoảng 278000000.5 đồng, tầm hoạt động 399 km.")

    projected = normalize_customer_result(result)

    assert projected.answer == "Giá lăn bánh khoảng 278.000.000,5 đồng, tầm hoạt động 399 km."


def test_decimal_skips_year_formatted_number_and_model_name() -> None:
    """Bộ định dạng số không đụng năm, số đã format, hay tên bản xe.

    Ca này TỪNG khẳng định `0912345678` đi qua nguyên vẹn. T7c đổi hợp đồng đó
    có chủ ý: số liên hệ ngoài allowlist hotline giờ bị xoá ở cửa ra — xem
    `test_strips_phone_numbers_outside_the_hotline_allowlist`. Phần còn lại của
    ca này giữ nguyên vì nó bảo vệ một điều khác: đừng nhóm lại thứ không phải giá.
    """

    result = _result(answer="Năm 2026, VF 8 giá 1.200.000.000 đồng, hotline 1900545500, bản e34.")

    projected = normalize_customer_result(result)

    assert projected.answer == "Năm 2026, VF 8 giá 1.200.000.000 đồng, hotline 1900545500, bản e34."


def test_normalize_is_idempotent() -> None:
    result = _result(
        answer=(f"Em muốn mua VF 8 giá 1090000000 đồng [evidence_id:{RAW_UUID}]."),
        pending_question="Em đang phân vân giữa VF 6 và VF 8?",
        recommendations=[_recommendation("VF 8 chạy 399 km, giá 1090000000 đồng.")],
        comparison=VehicleComparisonView(summary="VF 8 giá 1090000000 đồng, VF 6 giá 690000000 đồng."),
    )

    once = normalize_customer_result(result)
    twice = normalize_customer_result(once)

    assert once == twice


def test_none_empty_and_unicode_safe() -> None:
    result = _result(answer=None, pending_question="")

    projected = normalize_customer_result(result)

    assert projected.answer is None
    assert projected.pending_question == ""

    unicode_result = _result(answer="Xe điện VF e34 có tầm hoạt động 399 km 🚗.")
    assert normalize_customer_result(unicode_result).answer == "Xe điện VF e34 có tầm hoạt động 399 km 🚗."


def test_nan_and_infinity_tokens_safe() -> None:
    result = _result(answer="Giá nan đồng, inf đồng, -inf.")

    assert normalize_customer_result(result).answer == "Giá nan đồng, inf đồng, -inf."


def test_preserves_structured_fields() -> None:
    result = _result(
        answer="Đề xuất cho anh/chị.",
        lookup_facts=[
            VehicleFacts(
                vehicle_id=VEHICLE_ID,
                display_name="VF 8",
                vehicle_type=VehicleType.CAR,
                starting_price_vnd=Decimal("1090000000"),
                specs={"seats": "5"},
            )
        ],
        quick_replies=[QuickReplyView(label="Xem giá", value="giá VF 8")],
        nearby_locations=NearbyLocationListView(
            locations=[
                NearbyLocationView(
                    id="loc-1",
                    name="Showroom Vinhomes",
                    address="Số 1 Đại lộ Thăng Long",
                    latitude=21.0,
                    longitude=105.8,
                    distance_km=5.5,
                    location_type="SHOWROOM",
                    category_label="Showroom",
                    maps_url="https://maps/x",
                )
            ]
        ),
        options=[{"label": "VF 8", "value": "vf8"}],
        recommendations=[_recommendation("VF 8 phù hợp nhu cầu gia đình.")],
    )

    projected = normalize_customer_result(result)

    assert projected.lookup_facts == result.lookup_facts
    assert projected.quick_replies == result.quick_replies
    assert projected.nearby_locations == result.nearby_locations
    assert projected.options == result.options
    assert projected.recommendations == result.recommendations


def test_projects_pitch_and_comparison_summary() -> None:
    result = _result(
        answer="Đề xuất.",
        recommendations=[_recommendation(f"VF 8 giá 1090000000 đồng [evidence_id:{RAW_UUID}].")],
        comparison=VehicleComparisonView(summary="VF 8 giá 1090000000 đồng, em muốn so sánh thêm."),
    )

    projected = normalize_customer_result(result)

    assert projected.recommendations[0].pitch == "VF 8 giá 1.090.000.000 đồng."
    assert projected.comparison is not None
    assert projected.comparison.summary == "VF 8 giá 1.090.000.000 đồng, anh/chị muốn so sánh thêm."


# --- T7c: bốn lỗ rò còn lại ở cửa ra ------------------------------------------


def test_scrubs_uuid_v7() -> None:
    """UUIDv7 lọt qua vì pattern cũ chỉ nhận nibble phiên bản 1–5.

    v7 là dạng sinh theo thời gian đang phổ biến dần; một pattern khoá cứng
    danh sách phiên bản sẽ rò lại mỗi lần RFC thêm phiên bản mới.
    """

    uuid_v7 = "0192f1a0-7b3c-7def-8abc-1234567890ab"
    result = _result(answer=f"Ma tra cuu {uuid_v7} da duoc ghi.")

    projected = normalize_customer_result(result)

    # So khớp trên MẢNH ĐẦU, không trên nguyên chuỗi: bộ định dạng số nhóm lại
    # cụm chữ số cuối, nên "chuỗi gốc không còn" là một phép thử luôn đúng —
    # nó xanh cả khi UUID vẫn nằm nguyên đó dưới dạng đã nhóm.
    assert "0192f1a0" not in (projected.answer or "")


def test_strips_phone_numbers_outside_the_hotline_allowlist() -> None:
    """Chỉ hotline chính thức được đứng lại; số lạ là rò rỉ hoặc bịa.

    Số điện thoại trong câu trả lời chỉ có hai nguồn: hotline đã công bố, hoặc
    mô hình bịa/nhặt từ dữ liệu nội bộ. Nguồn thứ hai không được tới khách.
    """

    result = _result(answer="anh/chị gọi 0912345678 hoặc 1900232389 nhé.")

    projected = normalize_customer_result(result)

    answer = projected.answer or ""
    assert "0912345678" not in answer, "so la phai bi xoa"
    assert "1900232389" in answer, "hotline chinh thuc phai giu"


def test_strips_a_fabricated_hotline_written_with_separators() -> None:
    """Số dạng hotline có dấu ngăn là số liên hệ, không phải giá tiền.

    Ranh giới cố ý: `1800123456` viết liền không phân biệt được với giá 1,8 tỷ,
    nên nó đi đường số. Có dấu ngăn thì ý định là số gọi — và số gọi không nằm
    trong allowlist là số bịa.
    """

    result = _result(answer="Hotline 1800 123 456 ho tro Quy khach.")

    assert "1800 123 456" not in (normalize_customer_result(result).answer or "")


def test_strips_internal_table_and_column_tokens_from_prose() -> None:
    """Tên bảng/cột nội bộ trong văn xuôi là dấu vết cài đặt, không phải nội dung."""

    result = _result(answer="Thong tin nay lay tu run_evidence va review_queue cua he thong.")

    projected = normalize_customer_result(result)

    answer = projected.answer or ""
    assert "run_evidence" not in answer
    assert "review_queue" not in answer


def test_public_projection_maps_internal_terminal_reason() -> None:
    """Mã nội bộ không được ra client; mã internal vẫn phải giữ trong DB.

    Vì vậy phép ánh xạ nằm ở `project_public_result` (biên công khai), KHÔNG ở
    `normalize_customer_result` — hàm đó chạy trước khi persist.
    """

    from src.agents.services.output_guard import project_public_result

    internal = _result(terminal_reason="GUARDRAIL_CONFIGURATION_ERROR")

    assert normalize_customer_result(internal).terminal_reason == "GUARDRAIL_CONFIGURATION_ERROR"

    public = project_public_result(internal)

    assert public.terminal_reason == "UNAVAILABLE"
    assert project_public_result(public).terminal_reason == "UNAVAILABLE", "phai idempotent"


def test_public_projection_keeps_customer_meaningful_reasons() -> None:
    from src.agents.services.output_guard import project_public_result

    for reason in ("CONTENT_BLOCKED", "ADVISOR_ACTIVE", "OUT_OF_SCOPE"):
        assert project_public_result(_result(terminal_reason=reason)).terminal_reason == reason

    handoff = project_public_result(_result(terminal_reason="NO_CANDIDATE_ADVISOR_HANDOFF"))
    assert handoff.terminal_reason == "ADVISOR_HANDOFF"


# ── "em" xưng hô khách: nhóm động từ phải ĐÓNG ranh giới ─────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "anh/chị cứ nói em điều mình đang băn khoăn nhé ạ",
        "em điều khiển xe qua ứng dụng",
        "em điểm qua vài mẫu cho anh/chị",
    ],
)
def test_dong_tu_ngan_khong_nuot_chu_dai_hon(text: str) -> None:
    """Bug thật 2026-08-26: "cứ nói em điều mình đang băn khoăn" ra "nói anh/chị
    điều mình đang băn khoăn" — "điều" khớp nhánh "đi" vì lookahead thiếu `\\b`.

    Cùng họ với bẫy Sếp tự bắt được: "k" viết tắt của "không" kèm đuôi tự do nuốt
    mất "khoá chống trộm". Sai theo chiều tệ nhất — câu vẫn đọc trôi nên không ai
    thấy, chỉ thấy đại từ đổi giữa chừng.
    """

    from src.agents.services.output_guard import _EM_ADDRESS

    assert not _EM_ADDRESS.search(text)


@pytest.mark.parametrize(
    "text",
    [
        "em muốn mua xe",
        "em đi làm hằng ngày",
        "em cần xe nhỏ gọn",
        "em quan tâm VF 3",
        "em chọn mẫu này",
    ],
)
def test_van_doi_dung_khi_em_that_su_la_khach(text: str) -> None:
    """Vá ranh giới KHÔNG được làm mất chức năng chính — kiểm cả chiều dương."""

    from src.agents.services.output_guard import _EM_ADDRESS

    assert _EM_ADDRESS.search(text)


def test_voice_giu_em_bot_tu_xung_sau_de() -> None:
    # "để em tìm" là bot tự xưng — không phải khách (probe TD-1 2026-08-30).
    result = _result(answer="Anh/chị bấm nút hoặc gõ quận/huyện để em tìm showroom gần nhất nhé.")
    projected = normalize_customer_result(result)
    assert projected.answer == "Anh/chị bấm nút hoặc gõ quận/huyện để em tìm showroom gần nhất nhé."
