from __future__ import annotations

import pytest

from src.agents.adapters.summary_llm import OpenAIConversationSummarizer


class Response:
    def __init__(self, tool_calls: list[dict[str, object]]) -> None:
        self.tool_calls = tool_calls


@pytest.mark.asyncio
async def test_summarizer_sends_previous_summary_and_exact_completed_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[object]] = []

    class Bound:
        async def ainvoke(self, messages: list[object]) -> Response:
            captured.append(messages)
            return Response([{"args": {"summary": "Đã loại VF 5; tiếp tục VF 7."}}])

    class Client:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        def bind_tools(self, tools: list[object], tool_choice: object) -> Bound:
            return Bound()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", Client)
    adapter = OpenAIConversationSummarizer(model_name="gpt-4o-mini", api_key="test-key")

    result = await adapter.summarize(
        previous_summary="Khách cân nhắc VF 5 và VF 7.",
        user_message="Loại VF 5 vì chật.",
        assistant_response="Mình sẽ tiếp tục với VF 7.",
    )

    assert result == "Đã loại VF 5; tiếp tục VF 7."
    rendered = str(captured[0][-1])
    assert "Khách cân nhắc VF 5 và VF 7." in rendered
    assert "Loại VF 5 vì chật." in rendered
    assert "Mình sẽ tiếp tục với VF 7." in rendered


@pytest.mark.asyncio
async def test_summarizer_rejects_missing_or_invalid_tool_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Bound:
        async def ainvoke(self, messages: list[object]) -> Response:
            del messages
            return Response([{"args": {"summary": ""}}])

    class Client:
        def __init__(self, **kwargs: object) -> None:
            pass

        def bind_tools(self, tools: list[object], tool_choice: object) -> Bound:
            return Bound()

    monkeypatch.setattr("langchain_openai.ChatOpenAI", Client)
    adapter = OpenAIConversationSummarizer(model_name="gpt-4o-mini", api_key="test-key")

    with pytest.raises(ValueError):
        await adapter.summarize(
            previous_summary="",
            user_message="ô tô",
            assistant_response="Bạn muốn ngân sách bao nhiêu?",
        )
