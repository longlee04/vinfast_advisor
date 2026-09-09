"""[A2-3] OpenAIChatAdapter — lỗi phía LLM không được làm chết lượt, không ghi DB."""

from __future__ import annotations

import logging

import pytest

from src.agents.adapters.llm import OpenAIChatAdapter
from src.agents.contracts import LLMExtractionPayload
from src.agents.domain.conversation_memory import MemoryMessage, WorkingMemoryProjection
from src.agents.domain.values import VehicleType


class _Response:
    def __init__(self, tool_calls: list[dict], content: str = "") -> None:
        self.tool_calls = tool_calls
        self.content = content


def _adapter_with(monkeypatch: pytest.MonkeyPatch, response: object) -> OpenAIChatAdapter:
    adapter = OpenAIChatAdapter(model_name="gpt-4o-mini", api_key="test-key")
    calls: list[int] = []
    captured_messages: list[object] = []
    captured_tools: list[dict] = []

    class _Bound:
        async def ainvoke(self, messages: list) -> object:
            calls.append(1)
            captured_messages.extend(messages)
            if isinstance(response, Exception):
                raise response
            return response

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def bind_tools(self, tools: list, tool_choice: object) -> _Bound:
            captured_tools.extend(tools)
            return _Bound()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", _Client)
    adapter.calls = calls  # type: ignore[attr-defined]
    adapter.captured_messages = captured_messages  # type: ignore[attr-defined]
    adapter.captured_tools = captured_tools  # type: ignore[attr-defined]
    return adapter


async def _extract(adapter: OpenAIChatAdapter, message: str = "tôi cần xe 700 triệu") -> LLMExtractionPayload:
    return await adapter.extract_slots(
        vehicle_type=VehicleType.CAR,
        feature_vocabulary=["PANORAMIC_ROOF"],
        conversation_history="",
        user_message=message,
    )


@pytest.mark.asyncio
async def test_missing_api_key_returns_an_empty_payload_instead_of_raising() -> None:
    adapter = OpenAIChatAdapter(model_name="gpt-4o-mini", api_key="")

    payload = await _extract(adapter)

    assert payload == LLMExtractionPayload()


@pytest.mark.asyncio
async def test_valid_tool_call_becomes_a_typed_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _Response([{"args": {"vehicle_type": "CAR", "budget_max_vnd": "700 triệu"}}])
    adapter = _adapter_with(monkeypatch, response)

    payload = await _extract(adapter)

    assert payload.vehicle_type is VehicleType.CAR
    assert payload.budget_max_vnd == "700 triệu"


@pytest.mark.asyncio
async def test_wrongly_typed_payload_is_rejected_without_killing_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response([{"args": {"passenger_count": "bảy người"}}])
    adapter = _adapter_with(monkeypatch, response)

    payload = await _extract(adapter)

    assert payload == LLMExtractionPayload()


@pytest.mark.asyncio
async def test_transport_failure_is_swallowed_into_an_empty_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_with(monkeypatch, RuntimeError("connection reset"))

    payload = await _extract(adapter)

    assert payload == LLMExtractionPayload()


@pytest.mark.asyncio
async def test_transport_failure_log_does_not_include_provider_payload(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret_payload = "Bearer customer-secret-token"
    adapter = _adapter_with(monkeypatch, RuntimeError(secret_payload))
    caplog.set_level(logging.WARNING)

    await _extract(adapter)

    assert secret_payload not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.asyncio
async def test_a_turn_without_any_tool_call_extracts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_with(monkeypatch, _Response([]))

    payload = await _extract(adapter)

    assert payload == LLMExtractionPayload()


@pytest.mark.asyncio
async def test_extraction_issues_exactly_one_llm_call_per_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _Response([{"args": {"vehicle_type": "CAR"}}])
    adapter = _adapter_with(monkeypatch, response)

    await _extract(adapter)

    assert adapter.calls == [1]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_working_memory_is_sent_as_role_preserving_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter_with(monkeypatch, _Response([{"args": {"vehicle_type": "CAR"}}]))
    projection = WorkingMemoryProjection(
        slots={"vehicle_type": "CAR"},
        summary="Khách đang xem VF 7.",
        recent_messages=(
            MemoryMessage("USER", "VF 7 đi được bao xa?"),
            MemoryMessage("ASSISTANT", "Thông tin quãng đường VF 7."),
        ),
        pending_features=("camera 360",),
        current_user_message="Con đó giá bao nhiêu?",
    )

    await adapter.extract_slots(
        vehicle_type=VehicleType.CAR,
        feature_vocabulary=[],
        conversation_history=projection,
        user_message="Con đó giá bao nhiêu?",
    )

    messages = adapter.captured_messages  # type: ignore[attr-defined]
    assert [type(message).__name__ for message in messages] == [
        "SystemMessage",
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert messages[-1].content == "Con đó giá bao nhiêu?"
    assert "camera 360" in messages[1].content


# ── Nhãn tính năng gửi cho LLM phải là TIẾNG VIỆT, không phải mã ──────────────


def _feature_mentions_field(adapter: OpenAIChatAdapter) -> dict:
    tool = adapter.captured_tools[0]  # type: ignore[attr-defined]
    return tool["function"]["parameters"]["properties"]["feature_mentions"]


@pytest.mark.asyncio
async def test_tool_schema_mo_ta_tinh_nang_bang_nhan_tieng_viet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lượt thật 2026-08-26: "anh chỉ cần 1 chiếc nhỏ gọn thôi tại đi trong nội
    thành" trả về `feature_mentions = []`. Vì prompt khai `COMPACT_SIZE =
    COMPACT_SIZE` — mô hình không có cách nào biết mã đó nghĩa là gì bằng tiếng
    Việt, nên "nhỏ gọn" không quy về được mã nào."""

    adapter = _adapter_with(monkeypatch, _Response([]))

    await adapter.extract_slots(
        vehicle_type=VehicleType.CAR,
        feature_vocabulary=["COMPACT_SIZE", "ANTI_THEFT"],
        conversation_history="",
        user_message="anh chỉ cần 1 chiếc nhỏ gọn thôi tại đi trong nội thành",
    )

    description = _feature_mentions_field(adapter)["description"]
    assert "thân xe nhỏ gọn" in description
    assert "khoá chống trộm" in description


@pytest.mark.asyncio
async def test_ma_khong_co_nhan_van_o_lai_trong_enum_chu_khong_bi_loai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nhãn thiếu chỉ làm mô tả rơi về mã; làm HẸP tập giá trị hợp lệ thì mã mới
    thêm vào `feature_definitions` sẽ không bao giờ trích được nữa."""

    adapter = _adapter_with(monkeypatch, _Response([]))

    await adapter.extract_slots(
        vehicle_type=VehicleType.CAR,
        feature_vocabulary=["COMPACT_SIZE", "MA_MOI_CHUA_CO_NHAN"],
        conversation_history="",
        user_message="x",
    )

    field = _feature_mentions_field(adapter)
    assert field["items"]["enum"] == ["COMPACT_SIZE", "MA_MOI_CHUA_CO_NHAN"]
    assert "MA_MOI_CHUA_CO_NHAN = MA_MOI_CHUA_CO_NHAN" in field["description"]
