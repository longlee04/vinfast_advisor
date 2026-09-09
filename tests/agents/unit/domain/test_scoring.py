"""Contract tests for deterministic A5-3 candidate scoring."""

from dataclasses import replace
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.agents.domain.claim_policy import plan_claims
from src.agents.domain.scoring import (
    NeedTagLink,
    ScoringAssertion,
    ScoringCandidate,
    ScoringProfile,
    _budget_reasons,
    _purpose_reasons,
    rank_candidates,
)
from src.agents.domain.values import SlotName, VehicleType

VEHICLE_1 = UUID("00000000-0000-0000-0000-000000000101")
VEHICLE_2 = UUID("00000000-0000-0000-0000-000000000102")
VEHICLE_3 = UUID("00000000-0000-0000-0000-000000000103")
VEHICLE_4 = UUID("00000000-0000-0000-0000-000000000104")


def _profile(
    *,
    need_tags: tuple[str, ...] = (),
    feature_mentions: tuple[str, ...] = (),
    feature_mention_labels: dict[str, str] | None = None,
    feature_labels: dict[str, str] | None = None,
) -> ScoringProfile:
    return ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=5,
        required_range_km=300,
        home_charging=True,
        purpose="gia_dinh",
        max_load_kg=None,
        habit_need_tags=need_tags,
        feature_mentions=feature_mentions,
        feature_mention_labels=feature_mention_labels or {},
        feature_labels=feature_labels or {},
    )


def _candidate(
    vehicle_id: UUID,
    *,
    price_vnd: Decimal = Decimal("650000000"),
    range_km: Decimal = Decimal("400"),
    seat_count: int = 5,
    home_charge_time_minutes: Decimal | None = Decimal("480"),
    over_budget_percent: Decimal | None = None,
    assertions: tuple[ScoringAssertion, ...] = (),
    need_tag_links: tuple[NeedTagLink, ...] = (),
) -> ScoringCandidate:
    return ScoringCandidate(
        vehicle_id=vehicle_id,
        vehicle_type=VehicleType.CAR,
        price_vnd=price_vnd,
        range_km=range_km,
        seat_count=seat_count,
        max_load_kg=None,
        cargo_volume_l=Decimal("500"),
        energy_consumption_per_100km=Decimal("18"),
        home_charge_time_minutes=home_charge_time_minutes,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=over_budget_percent,
        assertions=assertions,
        need_tag_links=need_tag_links,
    )


def test_personal_car_with_consumption_gets_evidence_backed_purpose_claim() -> None:
    profile = replace(_profile(), purpose="đi trong nội thành")

    reasons = _purpose_reasons(profile, _candidate(VEHICLE_1))

    assert len(reasons) == 1
    assert reasons[0].message == "Mức tiêu thụ điện phù hợp nhu cầu đi lại trong đô thị"
    assert plan_claims(tuple(reason.render() for reason in reasons))[0].text == "tiết kiệm điện khi đi lại trong đô thị"


def test_personal_car_without_consumption_gets_no_purpose_reason() -> None:
    profile = ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=5,
        required_range_km=300,
        home_charging=True,
        purpose="đi trong nội thành",
        max_load_kg=None,
        habit_need_tags=(),
    )

    candidate = replace(_candidate(VEHICLE_1), energy_consumption_per_100km=None)

    assert _purpose_reasons(profile, candidate) == []


def test_personal_motorbike_gets_no_purpose_reason_even_with_consumption() -> None:
    profile = ScoringProfile(
        vehicle_type=VehicleType.ELECTRIC_MOTORBIKE,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=None,
        required_range_km=None,
        home_charging=None,
        purpose="đi trong nội thành",
        max_load_kg=None,
        habit_need_tags=(),
    )
    candidate = replace(_candidate(VEHICLE_1), vehicle_type=VehicleType.ELECTRIC_MOTORBIKE)

    assert _purpose_reasons(profile, candidate) == []


def test_rank_candidates_returns_every_eligible_sample_in_descending_score_order() -> None:
    """Mọi ứng viên đủ điều kiện, không cắt theo thứ hạng.

    Cả bốn xe đều đủ điều kiện; chúng chỉ khác nhau ở tầm chạy nên khác nhau ở
    ĐIỂM. Trước đây `VEHICLE_1` biến mất khỏi kết quả chỉ vì điểm thấp nhất đẩy
    nó xuống vị trí thứ tư — không một tiêu chí nào loại nó. Đó chính là bug:
    thứ hạng bị dùng như một bộ lọc.
    """

    ranked = rank_candidates(
        _profile(),
        [
            _candidate(VEHICLE_1, range_km=Decimal("310")),
            _candidate(VEHICLE_2, range_km=Decimal("500")),
            _candidate(VEHICLE_3, range_km=Decimal("420")),
            _candidate(VEHICLE_4, range_km=Decimal("350")),
        ],
    )

    assert [item.vehicle_id for item in ranked] == [
        VEHICLE_2,
        VEHICLE_3,
        VEHICLE_4,
        VEHICLE_1,
    ]
    assert [item.score for item in ranked] == sorted((item.score for item in ranked), reverse=True)


def test_each_ranked_sample_has_at_least_two_reasons_pointing_to_specific_slots() -> None:
    ranked = rank_candidates(_profile(), [_candidate(VEHICLE_1)])

    assert len(ranked) == 1
    assert len(ranked[0].reasons) >= 2
    assert all(reason.slot in SlotName for reason in ranked[0].reasons)


def test_over_budget_candidate_without_label_is_excluded() -> None:
    ranked = rank_candidates(
        _profile(),
        [
            _candidate(VEHICLE_1, price_vnd=Decimal("800000000")),
            _candidate(VEHICLE_2),
        ],
    )

    assert [item.vehicle_id for item in ranked] == [VEHICLE_2]


def test_price_closer_to_budget_scores_higher_than_a_much_cheaper_one() -> None:
    """Bug thật 2026-08-21 (Sếp báo): khách nói "khoảng 500 triệu" mà xe hẳn
    dưới 200 triệu lại xếp đầu — công thức cũ thưởng điểm theo "còn dư bao
    nhiêu" (headroom), xe càng rẻ càng dư nhiều càng điểm cao. Giờ đổi sang
    "gần ngân sách" (closeness) — không loại xe rẻ, chỉ đổi thứ tự ưu tiên."""

    ranked = rank_candidates(
        _profile(),
        [
            _candidate(VEHICLE_1, price_vnd=Decimal("188000000")),  # rất rẻ
            _candidate(VEHICLE_2, price_vnd=Decimal("496000000")),  # gần sát ngân sách 500tr
        ],
    )

    assert [item.vehicle_id for item in ranked] == [VEHICLE_2, VEHICLE_1]


def test_over_budget_candidate_with_label_has_explicit_budget_reason() -> None:
    ranked = rank_candidates(
        _profile(),
        [
            _candidate(
                VEHICLE_1,
                price_vnd=Decimal("770000000"),
                over_budget_percent=Decimal("10"),
            )
        ],
    )

    assert len(ranked) == 1
    assert ranked[0].over_budget_percent == Decimal("10")
    assert any(
        reason.slot is SlotName.BUDGET_MAX_VND and "Vượt ngân sách 10%" in reason.message
        for reason in ranked[0].reasons
    )


def test_need_tag_reason_traces_from_habit_slot_to_flag_evidence() -> None:
    assertion = ScoringAssertion(
        feature_code="PANORAMIC_ROOF",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-1",
    )
    ranked = rank_candidates(
        _profile(need_tags=("URBAN_TRAFFIC",)),
        [
            _candidate(
                VEHICLE_1,
                assertions=(assertion,),
                need_tag_links=(
                    NeedTagLink(
                        need_tag="URBAN_TRAFFIC",
                        feature_code="PANORAMIC_ROOF",
                        relevance=Decimal("0.80"),
                    ),
                ),
            )
        ],
    )

    reason = next(reason for reason in ranked[0].reasons if reason.need_tag is not None)
    assert reason.slot is SlotName.HABIT_NEED_TAGS
    assert reason.need_tag == "URBAN_TRAFFIC"
    assert reason.feature_code == "PANORAMIC_ROOF"
    assert reason.assertion_source == "FLAG"
    assert reason.evidence_ref == "vehicle_feature_flags:flag-1"
    assert reason.weight == Decimal("16.00")


def test_feature_customer_asked_at_turn_2_adds_a_reason_when_vehicle_has_it() -> None:
    """Sếp 2026-08-21: xe có đúng tính năng khách vừa chọn ở lượt 2 → thêm
    lý do, để synthesis có claim hợp lệ mà nhắc lại đúng tính năng đó."""

    assertion = ScoringAssertion(
        feature_code="ANTI_THEFT",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-42",
    )
    ranked = rank_candidates(
        _profile(feature_mentions=("ANTI_THEFT",)),
        [_candidate(VEHICLE_1, assertions=(assertion,))],
    )

    reason = next(reason for reason in ranked[0].reasons if reason.feature_code == "ANTI_THEFT")
    assert reason.slot is SlotName.HABIT_NEED_TAGS
    assert reason.assertion_source == "FLAG"
    assert reason.evidence_ref == "vehicle_feature_flags:flag-42"
    assert reason.weight == Decimal("25")


def test_feature_mention_message_uses_the_vietnamese_label_not_the_raw_code() -> None:
    """Bug thật 2026-08-21 (Sếp báo): message trước đây nhúng thẳng mã thô
    (vd "ANTI_THEFT") — claim dựng từ message đó không gọi được tên tiếng
    Việt. `feature_mention_labels` phải thắng, message không còn mã thô."""

    assertion = ScoringAssertion(
        feature_code="ANTI_THEFT",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-42",
    )
    ranked = rank_candidates(
        _profile(
            feature_mentions=("ANTI_THEFT",),
            feature_mention_labels={"ANTI_THEFT": "khoá chống trộm"},
        ),
        [_candidate(VEHICLE_1, assertions=(assertion,))],
    )

    reason = next(reason for reason in ranked[0].reasons if reason.feature_code == "ANTI_THEFT")
    assert "khoá chống trộm" in reason.message
    assert "ANTI_THEFT" not in reason.message


def test_feature_customer_asked_but_vehicle_lacks_it_adds_no_reason() -> None:
    ranked = rank_candidates(_profile(feature_mentions=("ANTI_THEFT",)), [_candidate(VEHICLE_1)])

    assert not any(reason.feature_code == "ANTI_THEFT" for reason in ranked[0].reasons)


def test_feature_customer_asked_ignores_unapproved_document_assertion() -> None:
    """Chỉ FLAG đã duyệt YES mới đủ căn cứ — tài liệu (DOCUMENT) không tính,
    cùng chuẩn `_need_tag_reasons` (FLAG mới có thẩm quyền, T7)."""

    assertion = ScoringAssertion(
        feature_code="ANTI_THEFT",
        status="YES",
        source="DOCUMENT",
        evidence_ref="brochure:doc-1",
    )
    ranked = rank_candidates(
        _profile(feature_mentions=("ANTI_THEFT",)),
        [_candidate(VEHICLE_1, assertions=(assertion,))],
    )

    assert not any(reason.feature_code == "ANTI_THEFT" for reason in ranked[0].reasons)


def test_no_feature_mentions_adds_no_extra_reason() -> None:
    assertion = ScoringAssertion(
        feature_code="ANTI_THEFT",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-42",
    )
    ranked = rank_candidates(_profile(), [_candidate(VEHICLE_1, assertions=(assertion,))])

    assert not any(reason.feature_code == "ANTI_THEFT" for reason in ranked[0].reasons)


def test_feature_customer_asked_reaches_synthesis_as_a_named_claim() -> None:
    """Đầu-cuối: tính năng khách chọn ở lượt 2 phải tới được `plan_claims`,
    gọi ĐÚNG TÊN tiếng Việt — trước khi có `_feature_mention_reasons` + fix
    regex trace + `feature_mention_labels`, chỗ này luôn rỗng hoặc chỉ nói
    chung chung/nhúng mã thô (bug thật Sếp báo 2026-08-21)."""

    assertion = ScoringAssertion(
        feature_code="ANTI_THEFT",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-42",
    )
    ranked = rank_candidates(
        _profile(
            feature_mentions=("ANTI_THEFT",),
            feature_mention_labels={"ANTI_THEFT": "khoá chống trộm"},
        ),
        [_candidate(VEHICLE_1, assertions=(assertion,))],
    )
    rendered = [reason.render() for reason in ranked[0].reasons]

    claims = plan_claims(rendered)

    assert any(claim.placeholder == "CLAIM_ANTI_THEFT" for claim in claims)
    feature_claim = next(c for c in claims if c.placeholder == "CLAIM_ANTI_THEFT")
    assert "khoá chống trộm" in feature_claim.text
    assert "vừa xác nhận quan tâm" in feature_claim.text


def test_document_assertion_adds_a_reason_weaker_than_a_flag() -> None:
    """Tài liệu được góp điểm, nhưng flag vẫn nặng hơn — `FLAG` giữ quyền quyết định."""

    link = NeedTagLink(
        need_tag="URBAN_TRAFFIC",
        feature_code="PREMIUM_AUDIO",
        relevance=Decimal("1"),
    )
    profile = _profile(need_tags=("URBAN_TRAFFIC",))
    baseline = rank_candidates(profile, [_candidate(VEHICLE_1, need_tag_links=(link,))])
    document = ScoringAssertion(
        feature_code="PREMIUM_AUDIO",
        status="YES",
        source="DOCUMENT",
        evidence_ref="vehicle_documents:chunk-1",
    )
    flag = ScoringAssertion(
        feature_code="PREMIUM_AUDIO",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:flag-1",
    )
    with_document = rank_candidates(profile, [_candidate(VEHICLE_1, assertions=(document,), need_tag_links=(link,))])
    with_flag = rank_candidates(profile, [_candidate(VEHICLE_1, assertions=(flag,), need_tag_links=(link,))])

    assert with_document[0].score > baseline[0].score
    assert with_flag[0].score > with_document[0].score

    reason = next(reason for reason in with_document[0].reasons if reason.assertion_source == "DOCUMENT")
    assert reason.need_tag == "URBAN_TRAFFIC"
    assert reason.feature_code == "PREMIUM_AUDIO"
    assert reason.evidence_ref == "vehicle_documents:chunk-1"
    assert reason.weight == Decimal("8")


def test_quote_only_document_assertion_does_not_change_score() -> None:
    """Đoạn chỉ để trích dẫn (UNKNOWN) không khẳng định gì nên không được cộng điểm."""

    link = NeedTagLink(
        need_tag="URBAN_TRAFFIC",
        feature_code="PREMIUM_AUDIO",
        relevance=Decimal("1"),
    )
    profile = _profile(need_tags=("URBAN_TRAFFIC",))
    quote_only = ScoringAssertion(
        feature_code="PREMIUM_AUDIO",
        status="UNKNOWN",
        source="DOCUMENT",
        evidence_ref="vehicle_documents:chunk-1",
    )
    baseline = rank_candidates(profile, [_candidate(VEHICLE_1, need_tag_links=(link,))])
    with_quote = rank_candidates(profile, [_candidate(VEHICLE_1, assertions=(quote_only,), need_tag_links=(link,))])

    assert with_quote[0].score == baseline[0].score


def test_home_charging_slot_scores_shorter_structured_charge_time_higher() -> None:
    ranked = rank_candidates(
        _profile(),
        [
            _candidate(VEHICLE_1, home_charge_time_minutes=Decimal("600")),
            _candidate(VEHICLE_2, home_charge_time_minutes=Decimal("300")),
        ],
    )

    assert [item.vehicle_id for item in ranked] == [VEHICLE_2, VEHICLE_1]
    assert any(reason.slot is SlotName.HOME_CHARGING for reason in ranked[0].reasons)


def test_candidate_with_fewer_than_two_supported_reasons_is_excluded() -> None:
    profile = ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=None,
        passenger_count=None,
        required_range_km=None,
        home_charging=None,
        purpose=None,
        max_load_kg=None,
        habit_need_tags=(),
    )

    assert rank_candidates(profile, [_candidate(VEHICLE_1)]) == []


def test_empty_candidate_input_returns_empty_result() -> None:
    assert rank_candidates(_profile(), []) == []


def test_free_text_countryside_need_matches_canonical_long_range_tag() -> None:
    long_range = NeedTagLink(
        need_tag="LONG_RANGE",
        feature_code="HIGH_RANGE_BATTERY",
        relevance=Decimal("1"),
    )
    approved = ScoringAssertion(
        feature_code="HIGH_RANGE_BATTERY",
        status="YES",
        source="FLAG",
        evidence_ref="vehicle_feature_flags:long-range",
    )

    ranked = rank_candidates(
        _profile(need_tags=("thường xuyên về quê",)),
        [_candidate(VEHICLE_1, assertions=(approved,), need_tag_links=(long_range,))],
    )

    assert any(reason.need_tag == "LONG_RANGE" for reason in ranked[0].reasons)


def test_duplicate_candidate_ids_are_rejected() -> None:
    try:
        rank_candidates(_profile(), [_candidate(VEHICLE_1), _candidate(VEHICLE_1)])
    except ValueError as error:
        assert str(error) == "candidate vehicle_id values must be unique"
    else:
        raise AssertionError("duplicate vehicle ids must be rejected")


# ── Kể tính năng khách CHƯA hỏi tới (`_feature_showcase_reasons`) ─────────────


def _flag(code: str, *, status: str = "YES", source: str = "FLAG") -> ScoringAssertion:
    return ScoringAssertion(
        feature_code=code,
        status=status,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        evidence_ref=f"vehicle_feature_flags:{code.lower()}",
    )


def test_approved_feature_is_told_even_when_the_customer_never_asked_about_it() -> None:
    """Sếp 2026-08-25: "tính năng đề xuất quá ít". Trước đây `reasons` chỉ chứa
    thứ đã dùng để CHẤM ĐIỂM, nên xe có ADAS mà khách không hỏi ADAS thì pitch im."""

    ranked = rank_candidates(
        _profile(feature_labels={"ADAS_SUITE": "gói ADAS giữ làn và phanh khẩn cấp"}),
        [_candidate(VEHICLE_1, assertions=(_flag("ADAS_SUITE"),))],
    )
    claims = plan_claims([reason.render() for reason in ranked[0].reasons])

    claim = next(c for c in claims if c.placeholder == "CLAIM_ADAS_SUITE")
    assert claim.text == "được trang bị gói ADAS giữ làn và phanh khẩn cấp"


def test_showcase_never_changes_the_ranking() -> None:
    """Trọng số phải bằng KHÔNG: showcase là lý do để kể, không phải để chọn.
    Hai xe giống hệt nhau, một xe có thêm cờ tính năng — điểm phải y nhau."""

    labels = {"GPS": "định vị GPS", "BLUETOOTH": "kết nối Bluetooth"}
    without = rank_candidates(_profile(feature_labels=labels), [_candidate(VEHICLE_1)])
    with_flags = rank_candidates(
        _profile(feature_labels=labels),
        [_candidate(VEHICLE_1, assertions=(_flag("GPS"), _flag("BLUETOOTH")))],
    )

    assert with_flags[0].score == without[0].score


def test_showcase_does_not_rescue_a_candidate_that_fails_the_two_reason_gate() -> None:
    """Cổng `len(reasons) < 2` phải chạy TRƯỚC showcase. Đặt sau thì một mẫu chỉ
    khớp đúng loại xe lọt vào đề xuất chỉ vì nó có vài cái cờ — nới điều kiện lọc
    mà không ai yêu cầu."""

    bare = _profile(feature_labels={"GPS": "định vị GPS"})
    lonely = ScoringCandidate(
        vehicle_id=VEHICLE_1,
        vehicle_type=VehicleType.CAR,
        price_vnd=None,
        range_km=None,
        seat_count=None,
        max_load_kg=None,
        cargo_volume_l=None,
        energy_consumption_per_100km=None,
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=None,
        assertions=(_flag("GPS"), _flag("BLUETOOTH")),
        need_tag_links=(),
    )

    assert rank_candidates(bare, [lonely]) == []


def test_showcase_skips_codes_without_a_vietnamese_label() -> None:
    """Rơi về chính mã thì câu claim mang dấu gạch dưới, `synthesis.
    RAW_STRUCTURED_PATTERN` chặn, guardrail retry hai lần rồi đẩy tư vấn viên.
    Thà không kể còn hơn làm vỡ cả pitch."""

    ranked = rank_candidates(
        _profile(feature_labels={"GPS": "định vị GPS"}),
        [_candidate(VEHICLE_1, assertions=(_flag("GPS"), _flag("MOT_CAI_MA_LA")))],
    )
    rendered = " ".join(reason.render() for reason in ranked[0].reasons)

    assert "định vị GPS" in rendered
    assert "MOT_CAI_MA_LA" not in rendered.split("] ")[-1]
    assert all(
        claim.placeholder != "CLAIM_MOT_CAI_MA_LA" for claim in plan_claims([r.render() for r in ranked[0].reasons])
    )


def test_showcase_only_trusts_approved_flags() -> None:
    """Cùng chuẩn bằng chứng với `_need_tag_reasons`: chỉ `FLAG` đã duyệt `YES`.
    Tài liệu mô tả là căn cứ yếu hơn, `NO`/`UNKNOWN` thì không phải căn cứ nào cả."""

    labels = {"GPS": "định vị GPS", "TOWING": "móc kéo moóc", "ESIM": "eSIM kết nối dữ liệu trên xe"}
    ranked = rank_candidates(
        _profile(feature_labels=labels),
        [
            _candidate(
                VEHICLE_1,
                assertions=(
                    _flag("GPS"),
                    _flag("TOWING", status="NO"),
                    _flag("ESIM", source="DOCUMENT"),
                ),
            )
        ],
    )
    placeholders = {claim.placeholder for claim in plan_claims([r.render() for r in ranked[0].reasons])}

    assert "CLAIM_GPS" in placeholders
    assert "CLAIM_TOWING" not in placeholders
    assert "CLAIM_ESIM" not in placeholders


def test_customer_confirmed_feature_wins_over_the_plain_showcase_line() -> None:
    """Cùng một feature_code có thể vừa được khách xác nhận vừa nằm trong
    showcase. Lời "đúng thứ Quý khách vừa hỏi" mạnh hơn hẳn lời kể suông."""

    ranked = rank_candidates(
        _profile(
            feature_mentions=("ANTI_THEFT",),
            feature_mention_labels={"ANTI_THEFT": "khoá chống trộm"},
            feature_labels={"ANTI_THEFT": "khoá chống trộm"},
        ),
        [_candidate(VEHICLE_1, assertions=(_flag("ANTI_THEFT"),))],
    )
    claims = plan_claims([reason.render() for reason in ranked[0].reasons])

    matching = [c for c in claims if c.placeholder == "CLAIM_ANTI_THEFT"]
    assert len(matching) == 1
    assert "vừa xác nhận quan tâm" in matching[0].text


def test_empty_label_map_keeps_the_old_behaviour() -> None:
    """Không có nhãn thì showcase im hẳn — không mã trần nào lọt ra câu chữ."""

    ranked = rank_candidates(_profile(), [_candidate(VEHICLE_1, assertions=(_flag("GPS"),))])

    assert all("trang bị" not in reason.message for reason in ranked[0].reasons)


def test_free_text_purpose_still_counts_toward_the_score() -> None:
    """Bug thật Sếp báo 2026-08-25: mục đích viết tự do KHÔNG góp điểm nào.

    `_purpose_reasons` từng so `profile.purpose` với đúng bốn token
    `gia_dinh`/`di_lam`/`kinh_doanh`/`giao_hang`, trong khi prompt trích xuất chỉ
    dặn LLM ghi "mục đích khách nêu" — tức chữ tự do. Nên "chở gia đình đi xa"
    không khớp token nào và bị bỏ qua trong IM LẶNG: không log, không lỗi, chỉ là
    gợi ý kém đi.

    Nay dùng `purpose_bucket` — đúng hàm mà allowlist tính năng lượt 2 vẫn dùng —
    nên hai nơi hiểu mục đích theo cùng một cách.
    """

    ranked = rank_candidates(_profile_purpose("chở gia đình đi xa"), [_candidate(VEHICLE_1)])
    messages = [reason.message for reason in ranked[0].reasons if reason.slot is SlotName.PURPOSE]

    assert messages == ["Khoang hành lý hỗ trợ nhu cầu gia đình"]


def test_the_underscore_tokens_of_older_sessions_still_work() -> None:
    """Phiên cũ lưu `gia_dinh` dạng gạch dưới. Nắn sang nhóm mà làm hỏng chúng thì
    mọi cuộc tư vấn đang dở mất luôn mục đích."""

    ranked = rank_candidates(_profile_purpose("gia_dinh"), [_candidate(VEHICLE_1)])
    messages = [reason.message for reason in ranked[0].reasons if reason.slot is SlotName.PURPOSE]

    assert messages == ["Khoang hành lý hỗ trợ nhu cầu gia đình"]


def _profile_purpose(purpose: str) -> ScoringProfile:
    return ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal("700000000"),
        passenger_count=5,
        required_range_km=300,
        home_charging=True,
        purpose=purpose,
        max_load_kg=None,
        habit_need_tags=(),
    )


def test_a_long_trip_purpose_scores_on_range_not_nothing() -> None:
    """Sếp 2026-08-25: "về quê" phải thuộc nhóm ĐI XA.

    Trước đây nó rơi về `PERSONAL`, mà nhóm đó không có nhánh chấm điểm nào —
    khách nói một mục đích rất rõ mà không đổi được thứ hạng xe nào.
    """

    ranked = rank_candidates(_profile_purpose("mua xe để về quê"), [_candidate(VEHICLE_1)])
    messages = [reason.message for reason in ranked[0].reasons if reason.slot is SlotName.PURPOSE]

    assert messages == ["Tầm hoạt động phù hợp nhu cầu đi xa"]


def test_a_family_trip_home_is_still_a_family_purpose() -> None:
    """ "Chở gia đình về quê" là một chuyến GIA ĐÌNH: khoang hành lý mới là thứ
    quyết định ở đó, không phải tầm chạy. Thứ tự kiểm nhóm phải giữ đúng chiều này."""

    ranked = rank_candidates(_profile_purpose("chở gia đình về quê"), [_candidate(VEHICLE_1)])
    messages = [reason.message for reason in ranked[0].reasons if reason.slot is SlotName.PURPOSE]

    assert messages == ["Khoang hành lý hỗ trợ nhu cầu gia đình"]


def test_a_long_trip_gate_xe_tam_ngan_khong_nhan_ly_do_di_xa() -> None:
    """Bug prod 2026-08-31: "200 triệu + đi du lịch đường dài" → VF 2 (210 km)
    vẫn nhận "Tầm hoạt động phù hợp nhu cầu đi xa", rồi `claim_policy.plan_claims`
    đổi nó thành câu "hợp với mục đích sử dụng" trong pitch. Xe không đủ tầm
    (`LONG_TRIP_MIN_RANGE_KM`) thì KHÔNG có lý do đi-xa nào — chặn ở nguồn để
    mọi tầng nói phía sau hết đường khẳng định sai. Đi làm trong phố sạc mỗi tối
    nên vẫn chấm tầm chạy như cũ; bản trước từng so trọng số đi-xa với đi-làm
    trên xe 120 km, nay xe dưới ngưỡng không còn trọng số đi-xa để so."""

    short_range = _candidate(VEHICLE_1, range_km=Decimal("210"))

    di_xa = rank_candidates(_profile_purpose("đi du lịch đường dài"), [short_range])[0]
    di_lam = rank_candidates(_profile_purpose("đi làm"), [short_range])[0]

    assert [r.message for r in di_xa.reasons if r.slot is SlotName.PURPOSE] == []
    assert [r.message for r in di_lam.reasons if r.slot is SlotName.PURPOSE] == [
        "Tầm hoạt động phù hợp nhu cầu đi làm"
    ]


# ── Khách không đặt trần giá thì giá THÔI làm tiêu chí (Sếp 2026-08-26) ──────


def _candidate_at(price: Decimal) -> ScoringCandidate:
    return ScoringCandidate(
        vehicle_id=uuid4(),
        vehicle_type=VehicleType.CAR,
        price_vnd=price,
        seat_count=5,
        range_km=Decimal(400),
        max_load_kg=None,
        cargo_volume_l=Decimal(376),
        energy_consumption_per_100km=Decimal("19.19"),
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=None,
        assertions=(),
        need_tag_links=(),
    )


def _profile_no_budget(**kwargs):
    from src.agents.domain.budget_parsing import NO_BUDGET_LIMIT_VND

    base = {
        "vehicle_type": VehicleType.CAR,
        "budget_max_vnd": float(NO_BUDGET_LIMIT_VND),
        "passenger_count": None,
        "required_range_km": None,
        "home_charging": None,
        "purpose": None,
        "max_load_kg": None,
        "habit_need_tags": (),
    }
    base.update(kwargs)
    return ScoringProfile(**base)


@pytest.mark.parametrize("price", [299_000_000, 899_000_000, 1_491_000_000])
def test_khong_dat_tran_thi_gia_khong_con_cong_diem(price: int) -> None:
    """`NO_BUDGET_LIMIT_VND` là trần GIẢ 10 tỷ để bộ lọc không loại xe nào.

    Nhưng nó vẫn chảy qua công thức `closeness`, và đo ra: xe 299 triệu được
    5,60 điểm, xe 1,491 tỷ được 7,98 — tức hệ vẫn xếp theo giá, và xếp NGƯỢC:
    càng đắt càng cao điểm. Khách vừa bảo đừng tính tiền thì hệ tự chọn hộ họ
    chiếc đắt nhất.
    """

    assert _budget_reasons(_profile_no_budget(), _candidate_at(Decimal(price))) == []


def test_co_san_thi_gia_van_la_tieu_chi() -> None:
    """Chiều ÂM. "từ 900 triệu" cũng đặt trần giả 10 tỷ (không giới hạn TRÊN),
    nhưng ở đó khách VẪN nêu một mốc giá — giá còn là tiêu chí, chỉ là tiêu chí
    một đầu."""

    candidate = _candidate_at(Decimal(950_000_000))

    assert _budget_reasons(_profile_no_budget(budget_min_vnd=900_000_000.0), candidate) != []


# ── Nhu cầu THẮNG giá, kể cả ca xấu nhất (Sếp 2026-08-26) ───────────────────


def _rival(price: int, *, tags: tuple[tuple[str, str], ...] = ()) -> ScoringCandidate:
    links = tuple(NeedTagLink(need_tag=t, feature_code=f, relevance=Decimal("1")) for t, f in tags)
    asserts = tuple(
        ScoringAssertion(feature_code=f, status="YES", source="FLAG", evidence_ref=f"ev-{f}") for _, f in tags
    )
    return ScoringCandidate(
        vehicle_id=uuid4(),
        vehicle_type=VehicleType.CAR,
        price_vnd=Decimal(price),
        range_km=Decimal(320),
        seat_count=5,
        max_load_kg=None,
        cargo_volume_l=Decimal(300),
        energy_consumption_per_100km=Decimal("19"),
        home_charge_time_minutes=None,
        battery_removable=None,
        battery_swappable=None,
        over_budget_percent=None,
        assertions=asserts,
        need_tag_links=links,
    )


def test_mot_tin_hieu_nhu_cau_thang_toan_bo_khoang_chenh_gia() -> None:
    """Ca XẤU NHẤT: hai xe giống hệt nhau mọi mặt, chỉ khác giá và đúng MỘT tín
    hiệu nhu cầu.

    Chênh lệch do giá bị chặn cứng ở 20 điểm (5 khi rẻ nhất → 25 khi sát trần),
    còn một tín hiệu need-tag đã là 20. Nên xe sát trần không bao giờ mua được
    thứ hạng bằng tiền: đo ra 79,00 so với 68,80.

    Bất biến này là thứ giữ cho bản đề xuất trả lời đúng câu khách hỏi ("xe nào
    hợp tôi") thay vì câu họ không hỏi ("xe nào đắt nhất trong tầm").
    """

    profile = ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal(1_000_000_000),
        budget_min_vnd=None,
        passenger_count=5,
        required_range_km=300,
        home_charging=None,
        purpose="chở gia đình",
        max_load_kg=None,
        habit_need_tags=("chở gia đình",),
    )
    sat_tran = _rival(990_000_000)
    hop_nhu_cau = _rival(500_000_000, tags=(("FAMILY_TRIP", "7_SEATER"),))

    ranked = rank_candidates(profile=profile, candidates=[sat_tran, hop_nhu_cau])

    assert ranked[0].vehicle_id == hop_nhu_cau.vehicle_id
    assert ranked[0].score > ranked[1].score


def test_khach_neu_mot_khoang_thi_moi_xe_trong_khoang_bang_diem_gia() -> None:
    """Thưởng theo độ gần trần ở đây sẽ luôn đẩy xe đắt nhất lên đầu, tức chọn
    hộ khách một mức giá họ không yêu cầu — họ đã nói cả một khoảng."""

    profile = ScoringProfile(
        vehicle_type=VehicleType.CAR,
        budget_max_vnd=Decimal(1_000_000_000),
        budget_min_vnd=Decimal(700_000_000),
        passenger_count=None,
        required_range_km=None,
        home_charging=None,
        purpose=None,
        max_load_kg=None,
        habit_need_tags=(),
    )

    diem = [_budget_reasons(profile, _rival(gia))[0].weight for gia in (720_000_000, 990_000_000)]

    assert diem[0] == diem[1]
