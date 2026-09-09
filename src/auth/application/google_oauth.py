"""Đăng nhập bằng Google: đổi authorization code lấy danh tính đã xác minh.

Luồng server-side Authorization Code. `id_token` được xác minh bằng endpoint
`tokeninfo` của chính Google thay vì tự giải mã chữ ký: với luồng server-side
(code đổi trực tiếp với Google qua TLS) thì kiểm `aud`, `iss`, `email_verified`
trên câu trả lời của Google là đủ, và khỏi kéo thêm một thư viện JOSE vào repo.

Tài khoản Google mới được tạo ACTIVE ngay — Google đã xác minh hộp thư, đúng
điều bước verify-email của luồng đăng ký thường tồn tại để chứng minh.
`password_hash` là hash của một bí mật ngẫu nhiên 32 byte: cột NOT NULL cần một
giá trị, nhưng không ai — kể cả chủ tài khoản — biết mật khẩu đó, nên đường
đăng nhập bằng mật khẩu không mở thêm cho tài khoản Google.
"""

import logging
from datetime import datetime
from secrets import token_urlsafe
from typing import Any, Final, Protocol
from uuid import uuid4

from src.auth.application.ports import AccessTokenIssuer, AuthTransaction, TokenFactory
from src.auth.application.session_lifecycle import AuthSession, SessionLifecycle
from src.auth.domain.accounts import AccountState, User
from src.auth.domain.authorization import Role
from src.auth.domain.clock import Clock
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.hashing import PasswordHasher
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, UserId

logger = logging.getLogger(__name__)

#: Google phát `id_token` dưới một trong hai issuer này, tuỳ phiên bản endpoint.
GOOGLE_ISSUERS: Final[frozenset[str]] = frozenset({"accounts.google.com", "https://accounts.google.com"})


class GoogleIdentityGateway(Protocol):
    """Cổng HTTP sang Google; mọi thất bại mạng/HTTP quy về `None`."""

    async def exchange_code(self, code: str) -> dict[str, Any] | None:
        """Đổi authorization code lấy token response (chứa `id_token`)."""

    async def fetch_tokeninfo(self, id_token: str) -> dict[str, Any] | None:
        """Đọc claims đã được Google xác nhận cho một `id_token`."""


class GoogleOAuthService(SessionLifecycle):
    """Tìm-hoặc-tạo tài khoản khách từ danh tính Google rồi phát phiên."""

    def __init__(
        self,
        transaction: AuthTransaction,
        clock: Clock,
        password_hasher: PasswordHasher,
        token_factory: TokenFactory,
        access_tokens: AccessTokenIssuer,
        gateway: GoogleIdentityGateway,
        *,
        client_id: str,
    ) -> None:
        self._transaction = transaction
        self._clock = clock
        self._password_hasher = password_hasher
        self._token_factory = token_factory
        self._access_tokens = access_tokens
        self._gateway = gateway
        self._client_id = client_id

    async def login_with_google(self, code: str) -> AuthSession | None:
        """Trả phiên khi Google xác nhận danh tính; mọi ngả hỏng đều là `None`.

        `None` đồng nhất cho mọi lý do (đổi code trượt, `aud` lạ, email chưa
        xác minh, tài khoản bị khoá): người gọi chỉ đưa khách về màn đăng nhập,
        còn lý do cụ thể nằm trong log server — không phát cho trình duyệt.
        """
        email = await self._verified_email(code)
        if email is None:
            return None
        now = self._clock.now()
        async with self._transaction.transaction() as stores:
            user = await stores.users.get_by_email(email)
            if user is None:
                user = self._new_google_customer(email, now)
                await stores.users.add(user, now=now)
                await stores.security_events.append(
                    event_type="customer_registered_google", occurred_at=now, actor_user_id=user.id
                )
            elif user.state is AccountState.PENDING_VERIFICATION:
                # Google vừa chứng minh hộp thư thuộc về người này — đúng điều
                # token verify-email tồn tại để chứng minh, nên kích hoạt luôn.
                user = user.verify_email()
                await stores.users.save(user, now=now)
                await stores.security_events.append(
                    event_type="customer_verified", occurred_at=now, actor_user_id=user.id
                )
            try:
                user.assert_can_start_session()
            except AuthDomainError:
                logger.warning("dang nhap google bi tu choi: tai khoan khong o trang thai mo phien")
                return None
            session = self._new_session(user, now)
            await stores.refresh_tokens.add(self._refresh_from_session(session, now))
            await stores.security_events.append(
                event_type="customer_logged_in_google", occurred_at=now, actor_user_id=user.id
            )
            return session

    async def _verified_email(self, code: str) -> NormalizedEmail | None:
        token_response = await self._gateway.exchange_code(code)
        id_token = (token_response or {}).get("id_token")
        if not id_token:
            logger.warning("doi authorization code voi google that bai")
            return None
        claims = await self._gateway.fetch_tokeninfo(id_token)
        if not claims:
            logger.warning("khong doc duoc tokeninfo tu google")
            return None
        if claims.get("aud") != self._client_id:
            logger.warning("id_token mang aud cua client khac; tu choi")
            return None
        if claims.get("iss") not in GOOGLE_ISSUERS:
            logger.warning("id_token mang issuer la; tu choi")
            return None
        # `tokeninfo` trả chuỗi "true"; chấp nhận thêm boolean để không gãy nếu
        # Google đổi cách serialize.
        if claims.get("email_verified") not in ("true", True):
            logger.warning("email google chua duoc xac minh; tu choi")
            return None
        raw_email = claims.get("email")
        if not raw_email:
            return None
        try:
            # `parse` chứ không `parse_customer`: allowlist domain tồn tại để
            # chặn hộp thư dùng-một-lần, còn địa chỉ tới đây đã được Google xác
            # minh — kể cả domain Google Workspace riêng của công ty khách.
            return NormalizedEmail.parse(raw_email)
        except AuthDomainError:
            logger.warning("dia chi email tu google khong hop le")
            return None

    def _new_google_customer(self, email: NormalizedEmail, now: datetime) -> User:
        # 32 byte ngẫu nhiên rồi hash: thoả ràng buộc NOT NULL của cột mật khẩu
        # mà không tạo ra một mật khẩu ai đó đoán được.
        placeholder = PlaintextPassword(token_urlsafe(32))
        return User(
            id=UserId(str(uuid4())),
            email=email,
            role=Role.CUSTOMER,
            state=AccountState.ACTIVE,
            password_hash=self._password_hasher.hash(placeholder),
            created_at=now,
        )
