"""OpenAI moderation adapter used before any stateful task or tool handling."""

from __future__ import annotations

from openai import AsyncOpenAI, OpenAIError

from src.agents.domain.canonical_text import CanonicalText
from src.agents.domain.moderation_blocklist import blocklist_verdict
from src.agents.logging import get_agent_logger
from src.config import get_settings

logger = get_agent_logger("agent.adapters.moderation")


class OpenAIModerationAdapter:
    """Classify potentially harmful input without exposing category details."""

    def __init__(self, *, api_key: str | None = None, model_name: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key if api_key is not None else settings.openai_api_key
        self._model_name = model_name or settings.moderation_model_name

    async def is_blocked(self, *, user_message: str, canonical: CanonicalText | None = None) -> bool:
        """Cờ tổng hợp của provider; provider không trả lời được thì rơi về blocklist.

        Bản cũ trả `False` cho cả hai đường hỏng — thiếu API key và lỗi hạ tầng.
        Nghĩa là ai làm được OpenAI timeout thì tắt được lớp kiểm duyệt, và một
        môi trường quên đặt key thì chạy không có lớp đó mà không ai biết. Nay
        hai đường ấy đi qua `blocklist_verdict`: hẹp hơn provider rất nhiều,
        nhưng là một cái cổng chứ không phải cửa mở.

        `canonical` do chain sinh một lần mỗi lượt; thiếu thì blocklist tự dựng
        để đường gọi cũ vẫn được chấm.
        """

        if not user_message.strip():
            return False
        if blocklist_verdict(user_message, canonical):
            # Đáy sàn chạy TRƯỚC provider, không phải THAY provider khi nó hỏng.
            #
            # Bản cũ chỉ hỏi blocklist ở hai nhánh lỗi, nên khi có API key thì nó
            # không bao giờ được chấm — mà OpenAI moderation KHÔNG gắn cờ chửi
            # tiếng Việt: đo trên máy 2026-09-23, "con mẹ chúng mày" đi thẳng qua
            # cổng và bot đáp lại bằng một bài chào hàng hai mẫu xe.
            #
            # Gộp bằng OR: danh sách tất định hẹp hơn provider rất nhiều nên nó
            # không làm provider yếu đi, chỉ bịt đúng vùng provider không phủ.
            return True
        if not self._api_key:
            return False
        try:
            response = await AsyncOpenAI(api_key=self._api_key).moderations.create(
                model=self._model_name,
                input=user_message,
            )
        except OpenAIError as error:
            logger.warning("Moderation unavailable (%s) — dung blocklist tat dinh", type(error).__name__)
            return blocklist_verdict(user_message, canonical)
        return any(result.flagged for result in response.results)
