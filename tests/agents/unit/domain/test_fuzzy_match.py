from __future__ import annotations

from src.agents.domain.entity_catalog import (
    EntityCategory,
    build_vehicle_aliases,
    default_catalog,
)
from src.agents.domain.fuzzy_match import (
    EntityCatalog,
    MatchThresholds,
    accepted_only,
    best_of,
    match_entities,
)
from src.agents.domain.vehicle_overview import VehicleAttribute

CATALOG = default_catalog()


def _canonicals(matches, category: EntityCategory) -> set[str]:
    return {item.canonical for item in accepted_only(matches) if item.category is category}


def test_vietnamese_number_word_resolves_a_model_without_any_llm() -> None:
    """Ca lỗi gốc: "vf năm" = "VF 5". Bắt được ở Lớp 2, không cần Lớp 1.

    Đây là lý do Lớp 1 không phải điểm chết duy nhất của pipeline: một sự cố LLM
    không được kéo sập luôn khả năng nhận diện tên xe.
    """

    matches = match_entities(original_text="tho ti x vf năm", catalog=CATALOG)

    assert "VF 5" in _canonicals(matches, EntityCategory.VEHICLE)


def test_model_written_without_a_space_still_resolves() -> None:
    matches = match_entities(original_text="vf5 giá bao nhiêu", catalog=CATALOG)

    assert _canonicals(matches, EntityCategory.VEHICLE) == {"VF 5"}
    assert VehicleAttribute.PRICE.value in _canonicals(matches, EntityCategory.ATTRIBUTE)


def test_a_bare_brand_token_never_resolves_to_a_model() -> None:
    """A4-1 cấm suy đoán danh tính xe: "vf" một mình không đủ chọn mẫu nào."""

    matches = match_entities(original_text="cho tôi hỏi về vf", catalog=CATALOG)

    assert _canonicals(matches, EntityCategory.VEHICLE) == set()


def test_a_short_token_only_matches_exactly() -> None:
    """Alias ba ký tự: một thao tác sửa đã là một phần ba chuỗi.

    "mua" không được phép khớp "màu" — nếu khớp thì khách hỏi mua xe sẽ nhận về
    bảng màu sơn.
    """

    matches = match_entities(original_text="tôi muốn mua xe", catalog=CATALOG)

    assert VehicleAttribute.COLOR.value not in _canonicals(matches, EntityCategory.ATTRIBUTE)


def test_a_short_token_inside_a_multi_word_alias_must_match_exactly() -> None:
    """ "các xe" không được khớp "cần xe" dù cả cụm đạt 83 điểm.

    Điểm tính trên cả cụm che mất lỗi nằm trong một từ ngắn; đo trên đúng từ
    chứa nó thì "cac" và "can" là hai từ khác hẳn nhau.
    """

    matches = match_entities(original_text="cho tôi xem các xe máy điện", catalog=CATALOG)
    intents = _canonicals(matches, EntityCategory.INTENT_KEYWORD)

    assert "CATALOG_BROWSE" in intents
    assert "ADVISORY" not in intents


def test_a_real_typo_inside_a_long_token_still_matches() -> None:
    """Token đủ dài thì khớp mờ vẫn làm việc: "klaraa" → "Klara"."""

    matches = match_entities(original_text="klaraa giá bao nhiêu", catalog=CATALOG)
    vehicle = best_of(matches, EntityCategory.VEHICLE)

    assert vehicle is not None
    assert vehicle.canonical == "Klara"
    assert 85.0 <= vehicle.score < 100.0


def test_rewritten_text_can_only_help_never_hurt() -> None:
    """Giữ điểm cao nhất giữa hai đường: câu gốc đúng thì rewrite hỏng vô hại."""

    matches = match_entities(
        original_text="vf5 màu gì",
        rewritten_text="vf9 màu gì",  # rewrite làm hỏng tên xe
        catalog=CATALOG,
    )

    assert "VF 5" in _canonicals(matches, EntityCategory.VEHICLE)


def test_match_records_which_text_it_came_from() -> None:
    matches = match_entities(
        original_text="tho ti x vf nem",
        rewritten_text="thông tin xe VF 5",
        catalog=CATALOG,
    )
    vehicle = best_of(matches, EntityCategory.VEHICLE)

    assert vehicle is not None
    assert vehicle.matched_on == "rewritten"


def test_source_span_only_contains_characters_the_customer_wrote() -> None:
    matches = match_entities(original_text="vf5 giá bao nhiêu", catalog=CATALOG)

    for item in accepted_only(matches):
        assert item.source_span in "vf5 gia bao nhieu"


def test_empty_catalog_returns_no_matches() -> None:
    assert match_entities(original_text="vf5", catalog=EntityCatalog()) == ()


def test_empty_message_returns_no_matches() -> None:
    assert match_entities(original_text="", catalog=CATALOG) == ()


def test_raising_the_threshold_rejects_a_weaker_match() -> None:
    strict = MatchThresholds(single_token=100.0, multi_token=100.0, weak_floor=70.0)

    matches = match_entities(original_text="klaraa giá bao nhiêu", catalog=CATALOG, thresholds=strict)

    assert _canonicals(matches, EntityCategory.VEHICLE) == set()


def test_custom_catalog_keeps_the_canonical_name_verbatim() -> None:
    """`canonical` được truyền xuống tra catalog nên phải giữ đúng cách ghi."""

    catalog = EntityCatalog(aliases=build_vehicle_aliases(["VinFast VF 6 Plus"]))

    matches = match_entities(original_text="vinfast vf 6 plus", catalog=catalog)

    assert _canonicals(matches, EntityCategory.VEHICLE) == {"VinFast VF 6 Plus"}
