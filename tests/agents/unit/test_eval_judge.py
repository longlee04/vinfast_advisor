"""[A9-3] Khung judge offline và ba KPI — thuần Python, không LLM, không DB."""

from __future__ import annotations

import pytest

from eval.judge.ports import CriterionScores
from eval.judge.runner import judge_enabled, run_judge
from eval.judge.scoring import average_score, regressions
from eval.kpi import (
    TurnOutcome,
    factual_accuracy,
    required_slot_completion,
    unwarned_over_budget_rate,
)


class FakeJudge:
    """Fake implementing `JudgePort`, trả điểm cứng và đếm số lần được gọi."""

    def __init__(self, scores: CriterionScores | None = None) -> None:
        self.scores = scores or CriterionScores(on_topic=1.0, advisor_voice=0.8, complete=0.6)
        self.calls = 0

    async def score(self, question: str, answer: str) -> CriterionScores:
        self.calls += 1
        return self.scores


def _outcome(**overrides: object) -> TurnOutcome:
    base = {
        "question_id": "Q001",
        "every_number_has_evidence": True,
        "recommended_over_budget": False,
        "over_budget_warned": False,
        "required_slots_asked": 4,
        "required_slots_filled": 4,
    }
    base.update(overrides)
    return TurnOutcome(**base)  # type: ignore[arg-type]


# --- KPI-1: Factual Accuracy ------------------------------------------------


def test_factual_accuracy_is_the_share_of_answers_with_every_number_sourced() -> None:
    outcomes = [
        _outcome(question_id="Q1"),
        _outcome(question_id="Q2"),
        _outcome(question_id="Q3", every_number_has_evidence=False),
        _outcome(question_id="Q4"),
    ]
    assert factual_accuracy(outcomes) == 0.75


def test_factual_accuracy_of_an_empty_run_is_unavailable_not_perfect() -> None:
    # Test âm: không có dữ liệu thì phải nói không tính được, không báo 100%
    assert factual_accuracy([]) is None


# --- KPI-2: Unwarned Over-Budget Recommendation Rate ------------------------


def test_unwarned_over_budget_rate_counts_only_recommendations_without_a_warning() -> None:
    outcomes = [
        _outcome(question_id="Q1", recommended_over_budget=True, over_budget_warned=True),
        _outcome(question_id="Q2", recommended_over_budget=True, over_budget_warned=False),
        _outcome(question_id="Q3", recommended_over_budget=False),
        _outcome(question_id="Q4", recommended_over_budget=True, over_budget_warned=False),
    ]
    # Mẫu số là 3 đề xuất vượt ngân sách, không phải 4 câu hỏi
    assert unwarned_over_budget_rate(outcomes) == pytest.approx(2 / 3)


def test_a_warned_over_budget_recommendation_does_not_count_against_the_kpi() -> None:
    outcomes = [_outcome(recommended_over_budget=True, over_budget_warned=True)]
    assert unwarned_over_budget_rate(outcomes) == 0.0


def test_unwarned_over_budget_rate_is_unavailable_without_any_recommendation() -> None:
    # Test âm: mẫu số là số đề xuất, không phải số câu hỏi
    assert unwarned_over_budget_rate([_outcome(recommended_over_budget=False)]) is None


# --- KPI-4: Required-Slot Completion ----------------------------------------


def test_required_slot_completion_is_filled_over_asked() -> None:
    outcomes = [
        _outcome(question_id="Q1", required_slots_asked=4, required_slots_filled=4),
        _outcome(question_id="Q2", required_slots_asked=4, required_slots_filled=2),
    ]
    assert required_slot_completion(outcomes) == 0.75


def test_required_slot_completion_is_unavailable_when_nothing_was_asked() -> None:
    # Test âm: chia cho 0 phải trả "không tính được", không phải crash hay 1.0
    assert required_slot_completion([_outcome(required_slots_asked=0, required_slots_filled=0)]) is None


def test_more_filled_than_asked_is_a_data_error() -> None:
    # Test âm: dữ liệu vô lý phải nổ ngay chứ không cho ra KPI > 1
    with pytest.raises(ValueError):
        required_slot_completion([_outcome(required_slots_asked=2, required_slots_filled=3)])


# --- Judge: bật/tắt, chấm điểm, tụt điểm ------------------------------------


def test_the_judge_is_off_unless_the_environment_variable_says_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENT_EVAL_JUDGE", raising=False)
    assert judge_enabled() is False


def test_the_judge_turns_on_with_the_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENT_EVAL_JUDGE", "1")
    assert judge_enabled() is True


def test_an_unrecognised_environment_value_leaves_the_judge_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Test âm: giá trị lạ không được ngầm bật một thứ tốn tiền gọi LLM
    monkeypatch.setenv("AGENT_EVAL_JUDGE", "maybe")
    assert judge_enabled() is False


def test_the_average_score_is_the_mean_of_the_three_criteria() -> None:
    scores = CriterionScores(on_topic=1.0, advisor_voice=0.5, complete=0.0)
    assert average_score(scores) == pytest.approx(0.5)


def test_questions_that_lost_points_since_the_last_run_are_listed() -> None:
    previous = {"Q1": 0.9, "Q2": 0.4}
    current = {"Q1": 0.7, "Q2": 0.4}
    assert regressions(previous, current) == ["Q1"]


def test_a_question_that_kept_its_score_is_not_a_regression() -> None:
    assert regressions({"Q1": 0.8}, {"Q1": 0.8}) == []


def test_a_question_absent_from_the_previous_run_is_not_a_regression() -> None:
    # Test âm: câu mới thêm vào bộ kiểm thử không được báo là tụt điểm
    assert regressions({}, {"Q9": 0.1}) == []


@pytest.mark.asyncio
async def test_running_the_judge_calls_the_injected_port_once_per_question() -> None:
    # Spy đếm số lần gọi: judge không được gọi LLM nhiều hơn số câu
    judge = FakeJudge()
    answers = {"Q1": "cau tra loi 1", "Q2": "cau tra loi 2"}

    report = await run_judge({"Q1": "hoi 1", "Q2": "hoi 2"}, answers, judge)

    assert judge.calls == 2
    assert sorted(report.scores) == ["Q1", "Q2"]


@pytest.mark.asyncio
async def test_a_question_without_an_answer_is_not_sent_to_the_judge() -> None:
    # Test âm: không có câu trả lời thì không tốn một lần gọi nào
    judge = FakeJudge()

    report = await run_judge({"Q1": "hoi 1"}, {}, judge)

    assert judge.calls == 0
    assert report.scores == {}
