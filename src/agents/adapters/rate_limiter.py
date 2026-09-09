"""[T7a] Bộ đếm chống lạm dụng cho `/agent/turn`.

Sao khuôn `src/auth/infrastructure/rate_limit.PostgresRateLimiter` — KHÔNG import
từ đó. Hai module có vòng đời schema riêng (`agent_alembic_version` vs
`auth_alembic_version`) và ranh giới ấy là thứ giữ cho việc đổi bảng của Auth
không làm vỡ agent. Trùng ~30 dòng ở đây rẻ hơn một phụ thuộc chéo module.

Cửa sổ CỐ ĐỊNH, không trượt. Tính chất phải biết trước: hai cửa sổ liền kề cho
phép một cụm gấp đôi hạn mức quanh ranh giới. Chấp nhận ở mức 20 lượt/phút, và
đổi lấy phép đếm nguyên tử bằng đúng một câu `INSERT ... ON CONFLICT DO UPDATE`
— đọc-rồi-ghi sẽ đếm thiếu dưới tải đồng thời, đúng cái tình huống mà một bộ
giới hạn sinh ra để xử lý.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.unit_of_work import SqlAlchemyRateLimitUnitOfWork
from src.agents.logging import get_agent_logger

logger = get_agent_logger("agent.adapters.rate_limiter")

#: Hạn mức khởi đầu. Một cuộc tư vấn thật hiếm khi quá vài lượt mỗi phút; 20 là
#: chỗ rộng rãi cho người gõ nhanh mà vẫn chặn script.
TURNS_PER_WINDOW: Final[int] = 20
WINDOW_SECONDS: Final[int] = 60


@dataclass(frozen=True, slots=True)
class TurnRateLimitPolicy:
    """Hạn mức và độ dài cửa sổ, chỉnh được mà không sửa code gọi."""

    attempts: int = TURNS_PER_WINDOW
    window_seconds: int = WINDOW_SECONDS


def window_start(now: datetime, window_seconds: int) -> datetime:
    """Làm tròn một mốc thời gian xuống ranh giới cửa sổ của nó, theo UTC."""

    instant = now.astimezone(UTC)
    epoch = int(instant.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=UTC)


def turn_rate_limit_key(customer_id: str | None, session_id: str) -> str:
    """Khoá đếm: theo KHÁCH khi đã xác thực, không thì theo phiên.

    Theo khách chứ không theo phiên là điều quan trọng: mở phiên mới không tốn
    gì, nên một khoá theo phiên là một khoá tự vô hiệu hoá.
    """

    subject = customer_id.strip() if customer_id and customer_id.strip() else session_id
    scope = "customer" if customer_id and customer_id.strip() else "session"
    return f"agent-turn:{scope}:{subject}"


class PostgresTurnRateLimiter:
    """Chính sách hạn mức; ranh giới transaction nằm ở `adapters/unit_of_work.py`.

    Adapter này KHÔNG tự mở session — `unit_of_work.py` là nơi duy nhất trong
    module được làm việc đó (mục 6.4), và `test_no_agent_repository_opens_its_own_session`
    cưỡng chế điều đó bằng cách quét AST. Ở đây chỉ còn hai việc thuộc về chính
    sách: tính ranh giới cửa sổ, và so tổng với hạn mức.
    """

    def __init__(
        self,
        unit_of_work: SqlAlchemyRateLimitUnitOfWork,
        policy: TurnRateLimitPolicy | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._policy = policy or TurnRateLimitPolicy()

    @classmethod
    def from_session_factory(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
        policy: TurnRateLimitPolicy | None = None,
    ) -> PostgresTurnRateLimiter:
        return cls(SqlAlchemyRateLimitUnitOfWork(session_factory=session_factory), policy)

    @classmethod
    def from_engine(cls, engine: AsyncEngine, policy: TurnRateLimitPolicy | None = None) -> PostgresTurnRateLimiter:
        return cls.from_session_factory(async_sessionmaker(engine, expire_on_commit=False), policy)

    async def allow(self, key: str, *, now: datetime | None = None) -> bool:
        """Đếm một lượt và cho biết nó còn nằm trong hạn mức hay không.

        Hạ tầng đếm hỏng → cho qua và ghi log. FAIL-OPEN có chủ ý: đây là chốt
        chống lạm dụng, không phải chốt an toàn (moderation, guardrail và cổng
        báo giá vẫn nguyên vị). Để một bảng đếm chết làm câm cả sản phẩm là đổi
        một phiền toái lấy một sự cố.
        """

        instant = now or datetime.now(UTC)
        start = window_start(instant, self._policy.window_seconds)
        try:
            attempts = await self._unit_of_work.count_attempt(
                key,
                window_start=start,
                expires_at=start + timedelta(seconds=self._policy.window_seconds),
            )
        except Exception:
            logger.warning("rate limiter khong dem duoc, cho qua", exc_info=True)
            return True
        return attempts <= self._policy.attempts


__all__ = [
    "TURNS_PER_WINDOW",
    "WINDOW_SECONDS",
    "PostgresTurnRateLimiter",
    "TurnRateLimitPolicy",
    "turn_rate_limit_key",
    "window_start",
]
