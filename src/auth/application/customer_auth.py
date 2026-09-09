"""Framework-independent customer registration and verification use cases."""

import logging
from datetime import datetime
from uuid import uuid4

from src.auth.application.ports import (
    AbuseLimitExceededError,
    AccessTokenIssuer,
    AuthStores,
    AuthTransaction,
    EmailDeliveryError,
    EmailSender,
    RateLimitKeyBuilder,
    RecoveryRateLimiter,
    TokenFactory,
)
from src.auth.application.session_lifecycle import AuthSession, SessionLifecycle
from src.auth.contracts import EMAIL_VERIFICATION_TTL_SECONDS
from src.auth.domain.accounts import AccountState, User, initial_customer_state
from src.auth.domain.authorization import Role
from src.auth.domain.clock import Clock, expires_after
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.hashing import PasswordHasher
from src.auth.domain.passwords import validate_password
from src.auth.domain.sessions import OneTimeToken, TokenPurpose
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, PlaintextToken, UserId

logger = logging.getLogger(__name__)


class CustomerAuthService(SessionLifecycle):
    """Customer registration, verification, and session lifecycle orchestration."""

    def __init__(
        self,
        transaction: AuthTransaction,
        clock: Clock,
        password_hasher: PasswordHasher,
        token_factory: TokenFactory,
        access_tokens: AccessTokenIssuer,
        login_limiter: RecoveryRateLimiter,
        resend_limiter: RecoveryRateLimiter,
        rate_limit_keys: RateLimitKeyBuilder,
        email_sender: EmailSender | None = None,
        require_email_verification: bool = True,
        customer_email_domains: frozenset[str] | None = None,
    ) -> None:
        self._transaction = transaction
        self._clock = clock
        self._password_hasher = password_hasher
        self._token_factory = token_factory
        self._access_tokens = access_tokens
        self._login_limiter = login_limiter
        self._resend_limiter = resend_limiter
        self._rate_limit_keys = rate_limit_keys
        self._email_sender = email_sender
        #: `False` → đăng ký xong tài khoản dùng được ngay, không phát token,
        #: không gửi thư. Mặc định BẬT: tắt phải là quyết định tường minh trong
        #: biến môi trường, không phải mặc định lặng lẽ.
        self._require_email_verification = require_email_verification
        #: `None` → domain layer dùng danh sách mặc định. Cùng một danh sách được
        #: dùng cho cả `register` và `login`: thu hẹp nó sau này sẽ khoá đăng nhập
        #: của khách cũ có domain vừa bị bỏ ra, nên chỉ nới, đừng cắt.
        self._customer_email_domains = customer_email_domains

    def _parse_customer_email(self, raw_email: str) -> NormalizedEmail:
        return NormalizedEmail.parse_customer(raw_email, allowed_domains=self._customer_email_domains)

    async def register(self, raw_email: str, raw_password: str) -> bool:
        """Register a pending customer and issue a hash-only verification token."""
        email = self._parse_customer_email(raw_email)
        password = PlaintextPassword(raw_password)
        validate_password(password)
        now = self._clock.now()
        verifying = self._require_email_verification
        user = User(
            id=UserId(str(uuid4())),
            email=email,
            role=Role.CUSTOMER,
            state=initial_customer_state() if verifying else AccountState.ACTIVE,
            password_hash=self._password_hasher.hash(password),
            created_at=now,
        )
        secret: str | None = None
        async with self._transaction.transaction() as stores:
            await stores.users.add(user, now=now)
            if verifying:
                secret = await self._issue_verification(stores, user, now)
            await stores.security_events.append(
                event_type="customer_registered", occurred_at=now, actor_user_id=user.id
            )
        # Chuyển phát nằm NGOÀI transaction. Trong transaction thì một lần
        # SendGrid timeout kéo theo rollback cả tài khoản vừa tạo — hai việc
        # chẳng liên quan gì nhau bị buộc chung một số phận, và khách nhận 500
        # cho một thao tác mà phía hệ thống không có gì sai.
        if secret is not None:
            await self._deliver_verification(user.email, secret)
        return True

    async def resend_verification(self, raw_email: str) -> bool:
        """Issue a latest-wins verification credential without disclosing identity."""
        try:
            email = self._parse_customer_email(raw_email)
        except AuthDomainError:
            return True
        now = self._clock.now()
        key = self._rate_limit_keys.build("resend", str(email))
        if not await self._resend_limiter.allow(key, now=now):
            raise AbuseLimitExceededError
        pending: tuple[NormalizedEmail, str] | None = None
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_email(email)
            if user is None or user.role is not Role.CUSTOMER or user.is_disabled:
                return True
            if user.state is initial_customer_state():
                pending = (user.email, await self._issue_verification(stores, user, now))
        if pending is not None:
            await self._deliver_verification(*pending)
        return True

    async def verify_get(self, raw_token: str) -> bool:
        """Deliberately non-mutating support for GET verification handlers."""
        return False

    async def verify_post(self, raw_token: str) -> bool:
        """Consume a verification credential and activate its customer account."""
        now = self._clock.now()
        token_hash = self._token_factory.hash(raw_token)
        try:
            async with self._transaction.transaction() as stores:
                token = await stores.one_time_tokens.get_for_consumption(token_hash)
                if token is None:
                    return False
                user = await stores.users.get_for_update(token.user_id)
                if user is None:
                    return False
                await stores.one_time_tokens.mark_consumed(
                    token.consume(now, purpose=TokenPurpose.EMAIL_VERIFICATION, user_id=user.id)
                )
                await stores.users.save(user.verify_email(), now=now)
                await stores.security_events.append(
                    event_type="customer_verified", occurred_at=now, actor_user_id=user.id
                )
        except AuthDomainError:
            return False
        return True

    async def login(self, raw_email: str, raw_password: str) -> AuthSession | None:
        """Authenticate a customer without creating an account-existence oracle."""
        password = PlaintextPassword(raw_password)
        try:
            email = self._parse_customer_email(raw_email)
        except AuthDomainError:
            self._password_hasher.verify(password, self._password_hasher.dummy_hash())
            return None
        now = self._clock.now()
        key = self._rate_limit_keys.build("login", str(email))
        if not await self._login_limiter.allow(key, now=now):
            raise AbuseLimitExceededError
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_email(email)
            if user is None:
                self._password_hasher.verify(password, self._password_hasher.dummy_hash())
                return None
            if not self._password_hasher.verify(password, user.password_hash):
                return None
            try:
                user.assert_can_start_session()
            except AuthDomainError:
                return None
            session = self._new_session(user, now)
            await stores.refresh_tokens.add(self._refresh_from_session(session, now))
            await stores.security_events.append(event_type="customer_logged_in", occurred_at=now, actor_user_id=user.id)
            return session

    async def _issue_verification(self, stores: AuthStores, user: User, now: datetime) -> str:
        """Ghi bằng chứng xác minh và TRẢ bí mật cho bước chuyển phát sau commit."""

        secret = self._token_factory.new_secret()
        await stores.one_time_tokens.issue(
            OneTimeToken(
                token_hash=self._token_factory.hash(secret),
                purpose=TokenPurpose.EMAIL_VERIFICATION,
                user_id=user.id,
                issued_at=now,
                expires_at=expires_after(now, EMAIL_VERIFICATION_TTL_SECONDS),
            ),
            now=now,
        )
        return secret

    async def _deliver_verification(self, recipient: NormalizedEmail, secret: str) -> None:
        """Gửi thư xác minh; hỏng thì ghi log, KHÔNG ném ngược lên khách.

        Tới đây token đã bền trong database, nên lỗi chuyển phát không phải là
        "đăng ký thất bại" — nó là "thư chưa tới", và khách tự đi tiếp được bằng
        nút gửi lại. Ném lỗi ở đây khiến khách tưởng chưa có tài khoản, thử lại,
        rồi rơi vào nhánh trùng email vốn cố ý im lặng: hỏng nặng hơn lúc đầu.

        Đây là outbox NHẸ: đủ để tách hai số phận, không hứa gửi đúng một lần.
        Bảo đảm đó cần một bảng hàng đợi và một worker retry — xem TODOS.
        """

        if self._email_sender is None:
            return
        try:
            await self._email_sender.send_verification(
                recipient=recipient, token=PlaintextToken(secret)
            )
        except EmailDeliveryError:
            logger.warning("khong gui duoc thu xac minh; tai khoan van con, khach co the gui lai")
