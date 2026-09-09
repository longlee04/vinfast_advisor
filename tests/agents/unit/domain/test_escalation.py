"""Chốt leo thang phải bắt đúng ca cần người, và KHÔNG bắt câu hỏi thường."""

from __future__ import annotations

import pytest

from src.agents.domain.escalation import (
    escalation_signals,
    explicitly_requests_human,
    is_critical_safety_incident,
    keyword_severity,
)
from src.agents.domain.values import Severity


@pytest.mark.parametrize(
    "message",
    [
        "cho tôi gặp tư vấn viên",
        "cho toi gap tu van vien",
        "Em muốn nói chuyện với nhân viên ạ",
        "chuyển cho tư vấn viên giúp em",
        "CHO GẶP NGƯỜI THẬT",
    ],
)
def test_explicit_human_request_is_caught_with_or_without_diacritics(message: str) -> None:
    assert explicitly_requests_human(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "tư vấn giúp em xe nào phù hợp",
        "gặp lại mẫu VF 8 hôm trước",
        "cửa hàng có nhân viên kỹ thuật không ạ",
    ],
)
def test_ordinary_turns_are_not_treated_as_human_requests(message: str) -> None:
    """"Có nhân viên không" là câu HỎI về cửa hàng, không phải yêu cầu gặp người."""

    assert explicitly_requests_human(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "xe của tôi đang bốc khói",
        "xe toi bi mat phanh",
        "xe em vừa tai nạn",
        "xe của mình có mùi khét",
    ],
)
def test_live_hazard_on_the_customers_own_vehicle_is_critical(message: str) -> None:
    assert is_critical_safety_incident(message) is True
    assert keyword_severity(message) is Severity.CRITICAL


@pytest.mark.parametrize(
    "message",
    [
        "xe điện có bốc cháy không ạ",
        "pin xe điện có nguy hiểm không",
        "nghe nói xe điện hay cháy có đúng không",
        "xe của tôi hết pin giữa đường",
    ],
)
def test_safety_questions_and_harmless_reports_are_not_incidents(message: str) -> None:
    """Hỏi kiến thức an toàn KHÁC báo sự cố.

    Thiếu một trong hai vế (xe của khách / nguy hiểm đang xảy ra) thì không
    đánh thức tư vấn viên — nếu không, mỗi câu hỏi vu vơ lại thành một báo động.
    """

    assert is_critical_safety_incident(message) is False


def test_non_urgent_complaint_raises_severity_without_forcing_handoff() -> None:
    assert keyword_severity("pin chai nhanh quá, bảo hành thế nào ạ") is Severity.ELEVATED


def test_a_light_price_remark_stays_normal() -> None:
    assert keyword_severity("xe này giá hơi cao nhỉ") is Severity.NORMAL


def test_signals_take_the_union_of_keyword_and_model() -> None:
    """Keyword trượt thì nhãn LLM đỡ, và ngược lại."""

    only_model = escalation_signals(
        "cho em xin một bạn phụ trách trực tiếp nhé",
        llm_human_requested=True,
    )
    assert only_model["human_requested"] is True

    only_keyword = escalation_signals("cho tôi gặp tư vấn viên", llm_human_requested=False)
    assert only_keyword["human_requested"] is True


def test_signals_keep_the_higher_severity_of_the_two_sources() -> None:
    signals = escalation_signals("xe chạy hơi ồn", llm_severity=Severity.CRITICAL)
    assert signals["severity"] is Severity.CRITICAL
    assert signals["critical_safety"] is True


def test_an_unknown_model_severity_string_never_lowers_the_keyword_verdict() -> None:
    """LLM trả rác thì rơi về NORMAL, nhưng không được kéo tụt kết luận keyword."""

    signals = escalation_signals("xe của tôi đang bốc khói", llm_severity="KHONG_HOP_LE")
    assert signals["severity"] is Severity.CRITICAL


# ── Báo động giả: chỗ khớp chuỗi con làm hỏng ────────────────────────────────
#
# `normalize` bỏ dấu, nên nhiều cặp từ khác nghĩa trở thành CÙNG một chuỗi:
# "chạy" → "chay" trùng "cháy"; "nóng"/"nong" nằm gọn trong "nong". Khớp chuỗi
# con biến mỗi câu khen xe thành một báo động cứu hộ.


@pytest.mark.parametrize(
    "message",
    [
        "xe của tôi chạy tốt lắm",
        "xe tôi chạy êm",
        "xe của tôi chạy được 400 km",
        "xe của tôi chạy hàng ngày",
    ],
)
def test_chay_the_verb_is_not_chay_the_fire(message: str) -> None:
    """"chạy" và "cháy" cùng bỏ dấu thành "chay" — phải phân biệt bằng ranh giới từ."""

    assert is_critical_safety_incident(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "xe của tôi hơi nóng",
        "xe tôi nóng máy khi đi xa",
    ],
)
def test_a_warm_vehicle_is_not_an_abnormally_hot_battery(message: str) -> None:
    """Chỉ "pin nóng" / "nóng bất thường" mới là nguy cấp, "hơi nóng" thì không."""

    assert is_critical_safety_incident(message) is False


@pytest.mark.parametrize(
    "message",
    [
        "xe của tôi mới mua",
        "xe của tôi tiết kiệm điện",
        "xe của tôi đi nhanh không",
        "xe của tôi có nổi bật gì không",
    ],
)
def test_ordinary_talk_about_ones_own_vehicle_never_escalates(message: str) -> None:
    assert is_critical_safety_incident(message) is False
    assert keyword_severity(message) is not Severity.CRITICAL


def test_a_real_fire_report_is_still_caught_after_tightening() -> None:
    """Siết chống báo động giả KHÔNG được làm mất ca thật."""

    assert is_critical_safety_incident("xe của tôi bốc cháy") is True
    assert is_critical_safety_incident("xe toi dang chay") is True


# ── Ma trận đối kháng: siết chống báo động giả không được làm mất ca thật ────


@pytest.mark.parametrize(
    "message",
    [
        "xe của tôi đang bốc khói",
        "xe toi bi mat phanh",
        "xe của tôi vừa tai nạn",
        "xe em có mùi khét",
        "xe của tôi bị cháy",
        "xe tôi pin nóng bất thường",
        "xe của mình đâm vào cột",
    ],
)
def test_every_real_incident_phrasing_still_escalates(message: str) -> None:
    assert is_critical_safety_incident(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "xe điện có bốc cháy không ạ",
        "pin xe điện có nóng không",
        "xe của tôi chạy 300km",
        "anh cho em hỏi xe nào chạy xa nhất",
        "tôi muốn xem xe khác",
        "xe của tôi hết pin",
    ],
)
def test_no_ordinary_sentence_triggers_a_rescue(message: str) -> None:
    assert is_critical_safety_incident(message) is False
