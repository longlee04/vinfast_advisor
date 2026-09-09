"""[Lớp 1] Use case sửa lỗi gõ: quyết định có gọi LLM không → gọi → áp guard.

Ba trách nhiệm, và trách nhiệm ĐẦU TIÊN mới là thứ khó:

1. **Không gọi LLM khi không cần.** `docs/vinfast-agent-mvp.md` §A4-2 chốt ngân
   sách "lượt hỏi slot ≤ 1 lần gọi LLM" và có test spy canh con số đó. Bước này
   nằm TRƯỚC `extract_slots`, nên nếu nó gọi mô hình ở mọi lượt thì mọi lượt đội
   lên gấp đôi — vỡ cả ngân sách lẫn p95 ≤ 6s (PRD 8.5). `rewrite_trigger` là
   cổng rule-based rẻ để phần lớn lượt đi qua với 0 lần gọi thêm.
2. **Nuốt lỗi hạ tầng, không nuốt trong im lặng.** Mô hình lỗi/timeout thì lượt
   vẫn phải chạy bằng câu gốc, nhưng phải có dòng log — cùng triết lý với
   `nodes/classify_scope`: một guardrail tắt âm thầm là guardrail không tồn tại.
3. **Áp guard của `domain/rewrite`.** Xem docstring ở đó.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.agents.adapters.rewrite_source import TextRewriterPort, parse_rewrite_payload
from src.agents.domain.rewrite import (
    MAX_TOKEN_CHANGE_RATIO,
    MIN_REWRITE_CONFIDENCE,
    RewriteResult,
    evaluate_rewrite,
    rewrite_trigger,
)
from src.agents.logging import get_agent_logger
from src.agents.prompts.rewrite_prompts import build_rewrite_prompt

logger = get_agent_logger("agent.nlu.layer1")


@dataclass(slots=True)
class RewriteServiceImpl:
    """Sửa lỗi gõ có kiểm soát; `rewriter=None` nghĩa là tắt hẳn Lớp 1.

    Tắt Lớp 1 KHÔNG làm hỏng ba lớp còn lại: `RewriteResult.text_for_matching`
    trả về câu gốc, và Lớp 2 vẫn bắt được "vf năm" nhờ alias số-đếm tiếng Việt
    trong `domain/entity_catalog`. Đây là chủ ý — nếu Lớp 1 là điểm chết duy nhất
    của cả pipeline thì một sự cố LLM sẽ kéo sập luôn khả năng nhận diện xe.
    """

    rewriter: TextRewriterPort | None = None
    known_tokens: frozenset[str] = field(default_factory=frozenset)
    max_change_ratio: float = MAX_TOKEN_CHANGE_RATIO
    min_confidence: float = MIN_REWRITE_CONFIDENCE
    enabled: bool = True

    async def rewrite(self, user_message: str) -> RewriteResult:
        """Trả `RewriteResult` — luôn có, kể cả khi không gọi mô hình lần nào."""

        original = user_message or ""
        trigger = rewrite_trigger(original, self.known_tokens)
        if not self.enabled or self.rewriter is None:
            # Cổng phát hiện nhiễu vẫn phải chạy khi Lớp 1 tắt: Lớp 4 đọc cờ này
            # để biết có được phép hỏi lại không. Trả thẳng `input_looks_noisy=
            # False` ở đây sẽ báo "mọi câu đều sạch" và tắt âm thầm luôn hai
            # nhánh hỏi lại — một tính năng chết mà không dòng log nào cho biết.
            # Hàm này thuần và rẻ, chạy nó không tốn lần gọi LLM nào.
            return RewriteResult.unchanged(original, "disabled", input_looks_noisy=trigger.should_attempt)

        if not trigger.should_attempt:
            logger.info(
                "layer1 bo qua: reason=%s noise_ratio=%.2f input=%r",
                trigger.reason,
                trigger.noise_ratio,
                original[:120],
            )
            return RewriteResult.unchanged(original, trigger.reason, input_looks_noisy=False)

        logger.info(
            "layer1 goi LLM: reason=%s noise_ratio=%.2f suspicious=%s input=%r",
            trigger.reason,
            trigger.noise_ratio,
            list(trigger.suspicious_tokens),
            original[:120],
        )
        try:
            raw = await self.rewriter.rewrite(prompt=build_rewrite_prompt(original))
        except Exception:
            # Hạ tầng LLM lỗi không được làm vỡ lượt: câu gốc vẫn dùng được, và
            # Lớp 2 vẫn chạy trên nó. Nhưng phải log — nếu không, Lớp 1 hỏng cả
            # tuần mà vận hành chỉ thấy "độ chính xác giảm nhẹ".
            logger.warning("layer1 loi khi goi LLM, dung cau goc", exc_info=True)
            return RewriteResult.unchanged(original, "llm_unavailable", input_looks_noisy=True)

        parsed = parse_rewrite_payload(raw)
        if parsed is None:
            logger.warning("layer1 payload khong doc duoc, dung cau goc")
            return RewriteResult.unchanged(original, "invalid_payload", input_looks_noisy=True)

        rewritten, confidence, _model_tokens = parsed
        result = evaluate_rewrite(
            original=original,
            rewritten=rewritten,
            confidence=confidence,
            max_change_ratio=self.max_change_ratio,
            min_confidence=self.min_confidence,
            input_looks_noisy=True,
        )
        logger.info(
            "layer1 ket qua: applied=%s reason=%s confidence=%.2f changed=%s output=%r",
            result.applied,
            result.reason,
            result.confidence,
            list(result.changed_tokens),
            result.rewritten[:120],
        )
        return result


__all__ = ["RewriteServiceImpl"]
