"""Bốn trục hiểu lượt phải ĐỘC LẬP với nhau.

Gộp chúng vào một bảng nhãn là lý do câu "vừa chê vừa hỏi" không xử được — mà đó
là dạng câu khách nói nhiều nhất. Một lượt vừa phàn nàn vừa hỏi thông tin thì
HÀNH VI vẫn là phàn nàn, còn NHIỆM VỤ đi theo câu hỏi chính.
"""

from __future__ import annotations

import pytest

from src.agents.domain.turn_axes import (
    MAX_SECONDARY_TOPICS,
    TurnAxes,
    coerce_topic,
    project_legacy_intents,
)
from src.agents.domain.values import (
    DialogueAct,
    Intent,
    IntentType,
    Severity,
    Topic,
)

# ── Trục độc lập ─────────────────────────────────────────────────────────────


def test_a_complaint_that_also_asks_keeps_both_axes() -> None:
    """Ca thúc đẩy cả thay đổi này: "Đắt quá, VF 8 giá bao nhiêu?"."""

    axes = TurnAxes(
        dialogue_act=DialogueAct.COMPLAIN,
        task=IntentType.PRICE_TCO_QUERY,
        primary_topic=Topic.PRICE_TCO,
    )
    assert axes.dialogue_act is DialogueAct.COMPLAIN
    assert axes.task is IntentType.PRICE_TCO_QUERY


def test_a_calm_customer_reporting_smoke_is_normal_act_but_critical_severity() -> None:
    """Cảm xúc và mức khẩn là HAI trục: bình tĩnh vẫn có thể nguy cấp."""

    axes = TurnAxes(
        dialogue_act=DialogueAct.REQUEST,
        task=IntentType.OTHER,
        primary_topic=Topic.OTHER,
        severity=Severity.CRITICAL,
    )
    assert axes.dialogue_act is DialogueAct.REQUEST
    assert axes.severity is Severity.CRITICAL


# ── Chủ đề phụ ───────────────────────────────────────────────────────────────


def test_the_primary_topic_is_removed_from_the_secondary_list() -> None:
    axes = TurnAxes(
        dialogue_act=DialogueAct.REQUEST,
        task=IntentType.VEHICLE_DISCOVERY,
        primary_topic=Topic.VEHICLE,
        secondary_topics=(Topic.VEHICLE, Topic.PRICE_TCO),
    )
    assert axes.secondary_topics == (Topic.PRICE_TCO,)


def test_secondary_topics_are_deduplicated_and_keep_their_order() -> None:
    axes = TurnAxes(
        dialogue_act=DialogueAct.REQUEST,
        task=IntentType.VEHICLE_DISCOVERY,
        primary_topic=Topic.VEHICLE,
        secondary_topics=(Topic.POLICY, Topic.PRICE_TCO, Topic.POLICY),
    )
    assert axes.secondary_topics == (Topic.POLICY, Topic.PRICE_TCO)


def test_secondary_topics_are_capped() -> None:
    axes = TurnAxes(
        dialogue_act=DialogueAct.REQUEST,
        task=IntentType.VEHICLE_DISCOVERY,
        primary_topic=Topic.VEHICLE,
        secondary_topics=(
            Topic.PRICE_TCO,
            Topic.POLICY,
            Topic.LOCATION,
            Topic.CHARGING,
            Topic.TRANSACTION,
        ),
    )
    assert len(axes.secondary_topics) == MAX_SECONDARY_TOPICS


# ── Rơi về an toàn ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", ["KHONG_CO_THAT", "", None, 7, "vehicle"])
def test_an_unknown_topic_becomes_other_instead_of_raising(value: object) -> None:
    """Mô hình trả rác thì lượt vẫn phải chạy, chỉ là không biết chủ đề."""

    assert coerce_topic(value) in {Topic.OTHER, Topic.VEHICLE}


def test_a_valid_topic_string_is_accepted_case_insensitively() -> None:
    assert coerce_topic("price_tco") is Topic.PRICE_TCO
    assert coerce_topic("PRICE_TCO") is Topic.PRICE_TCO


# ── Chiếu về nhãn cũ ─────────────────────────────────────────────────────────


def test_vehicle_discovery_projects_to_advisory() -> None:
    assert project_legacy_intents(IntentType.VEHICLE_DISCOVERY) == [Intent.ADVISORY]


def test_vehicle_info_projects_to_lookup_when_a_model_is_named() -> None:
    assert project_legacy_intents(
        IntentType.VEHICLE_INFO, vehicle_mentions=["VF 8"]
    ) == [Intent.CATALOG_LOOKUP]


def test_vehicle_info_projects_to_browse_when_only_a_type_is_named() -> None:
    assert project_legacy_intents(IntentType.VEHICLE_INFO) == [Intent.CATALOG_BROWSE]


def test_comparison_projects_to_compare_vehicles() -> None:
    assert project_legacy_intents(IntentType.COMPARISON) == [Intent.COMPARE_VEHICLES]


def test_a_price_question_about_a_named_model_is_a_lookup() -> None:
    assert project_legacy_intents(
        IntentType.PRICE_TCO_QUERY, vehicle_mentions=["VF 5"]
    ) == [Intent.CATALOG_LOOKUP]


def test_a_price_question_without_a_model_stays_advisory() -> None:
    assert project_legacy_intents(IntentType.PRICE_TCO_QUERY) == [Intent.ADVISORY]


@pytest.mark.parametrize(
    "task",
    [IntentType.POLICY_QUERY, IntentType.TRANSACTION_REQUEST, IntentType.HUMAN_REQUEST],
)
def test_tasks_without_legacy_routing_authority_project_to_nothing(task: IntentType) -> None:
    """Ba nhiệm vụ này KHÔNG được lái routing cũ — chúng có đường đi riêng."""

    assert project_legacy_intents(task) == []


def test_a_complaint_alone_projects_to_no_task() -> None:
    """Chê suông không phải một yêu cầu tra cứu."""

    assert project_legacy_intents(IntentType.COMPLAINT) == []


def test_an_unknown_task_projects_to_nothing_rather_than_guessing() -> None:
    assert project_legacy_intents(IntentType.OTHER) == []


def test_the_projection_is_never_a_second_source_of_truth() -> None:
    """Chiếu chỉ ĐỌC bốn trục, không bao giờ tự sinh nhãn mới ngoài bảng."""

    allowed = {
        Intent.ADVISORY,
        Intent.CATALOG_LOOKUP,
        Intent.CATALOG_BROWSE,
        Intent.COMPARE_VEHICLES,
    }
    for task in IntentType:
        for mentions in ([], ["VF 8"]):
            assert set(project_legacy_intents(task, vehicle_mentions=mentions)) <= allowed
