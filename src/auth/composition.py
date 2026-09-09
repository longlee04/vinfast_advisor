"""Auth composition root.

This module is the only place that constructs Auth infrastructure. Domain and
application code receive already-built collaborators, so neither imports
SQLAlchemy or reads the environment (`AGENTS.md:27-28`).

Startup is fail-fast on purpose. An Auth deployment that cannot reach its
database, or whose schema is behind the migration history, is not degraded but
broken: serving requests would either error per-request or, worse, appear to
work while writing nothing. So `AuthComposition.start()` verifies connectivity
and migration state before the application accepts traffic.
"""

import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.auth.application.customer_auth import CustomerAuthService
from src.auth.application.google_oauth import GoogleOAuthService
from src.auth.application.password_recovery import PasswordRecoveryService
from src.auth.application.ports import EmailSender
from src.auth.application.staff_auth import StaffAuthService
from src.auth.infrastructure.argon2_hasher import Argon2idHasher
from src.auth.infrastructure.clock import SystemClock
from src.auth.infrastructure.email import LoggingEmailSender, SendGridEmailSender
from src.auth.infrastructure.google_oauth import HttpxGoogleIdentityGateway
from src.auth.infrastructure.migrations import expected_auth_head
from src.auth.infrastructure.rate_limit import HmacRateLimitKeyBuilder, PostgresRateLimiter, RateLimitPolicy
from src.auth.infrastructure.repositories import AuthUnitOfWork
from src.auth.infrastructure.security import JwtAccessTokenIssuer, SecureTokenFactory
from src.auth.settings import AuthSettings

logger = logging.getLogger(__name__)

# Statement and connection ceilings keep a stuck database from holding an Auth
# request (and its connection) open indefinitely.
CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MS = 5_000
POOL_SIZE = 5
POOL_MAX_OVERFLOW = 5
POOL_RECYCLE_SECONDS = 1_800

ALEMBIC_VERSION_TABLE = "alembic_version"

# Printed in startup failures so the operator's next step is unambiguous.
_UPGRADE_COMMAND = "uv run alembic -c alembic-auth.ini upgrade head"


class AuthStartupError(RuntimeError):
    """Auth cannot serve traffic with the current configuration or schema."""


class AuthDatabaseUnavailableError(AuthStartupError):
    """The Auth database could not be reached."""


class AuthMigrationStateError(AuthStartupError):
    """The Auth database is reachable but its schema is not migrated."""


def describe_database_target(database_url: str) -> str:
    """Return `host:port/dbname` — never the user or password.

    Startup errors are read by operators and land in logs, so they must identify
    *which* database failed without disclosing how to connect to it
    (`AGENTS.md:43`).
    """
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return "<unparseable database url>"
    host = parts.hostname or "<unknown host>"
    port = f":{parts.port}" if parts.port else ""
    name = parts.path.lstrip("/") or "<unknown database>"
    return f"{host}{port}/{name}"


class AuthSchemaVerifier(Protocol):
    """Checks that a reachable Auth database is migrated to the expected head.

    Injectable so tests can exercise the migration-behind path without a live
    server.
    """

    async def __call__(self, engine: AsyncEngine, target: str) -> None: ...


async def verify_auth_schema(engine: AsyncEngine, target: str) -> None:
    """Reject an Auth database that is not on the revision the code expects.

    Three distinct failures, three distinct messages, because the operator's next
    action differs in each case:

    * No `alembic_version` table — never migrated. Run migrations.
    * Table present but empty — history was stamped away. Run migrations.
    * A revision that is not the expected head — stale (or ahead of) this build.
      Checking only that *some* revision exists would let a database whose schema
      predates the current models pass startup, and the mismatch would then
      surface as an undefined-column error on a live request instead of at boot.

    A multi-row `alembic_version` table means a branched history; reading only
    the first row would make the verdict depend on scan order, so every row is
    compared.
    """
    expected = expected_auth_head()
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}"))
            applied = sorted(str(row[0]) for row in result.fetchall() if row[0])
    except ProgrammingError:
        raise AuthMigrationStateError(_migration_required_message(target)) from None
    if not applied:
        raise AuthMigrationStateError(_migration_required_message(target))
    if applied != [expected]:
        raise AuthMigrationStateError(_revision_mismatch_message(target, applied, expected))
    logger.info("Auth schema revision %s verified on %s", expected, target)


def _migration_required_message(target: str) -> str:
    return f"Auth database {target} has no applied migration revision; run '{_UPGRADE_COMMAND}' before starting Auth"


def _revision_mismatch_message(target: str, applied: list[str], expected: str) -> str:
    return (
        f"Auth database {target} is at revision {', '.join(applied)} "
        f"but this build expects {expected}; run '{_UPGRADE_COMMAND}' before starting Auth"
    )


def create_auth_engine(settings: AuthSettings) -> AsyncEngine:
    """Build the Auth async engine with explicit timeouts and pool bounds."""
    return create_async_engine(
        settings.database_url,
        pool_size=POOL_SIZE,
        max_overflow=POOL_MAX_OVERFLOW,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        connect_args={
            "timeout": CONNECT_TIMEOUT_SECONDS,
            "server_settings": {"statement_timeout": str(STATEMENT_TIMEOUT_MS)},
        },
    )


@dataclass(frozen=True)
class AuthServices:
    """Concrete Auth application services owned by one application lifespan."""

    customer: CustomerAuthService
    recovery: PasswordRecoveryService
    staff: StaffAuthService
    #: `None` khi thiếu cấu hình `GOOGLE_OAUTH_*`; endpoint Google khi đó trả 404.
    google: GoogleOAuthService | None = None


@dataclass(frozen=True)
class AuthResources:
    """Infrastructure owned by one application lifespan."""

    engine: AsyncEngine
    email_sender: EmailSender
    session_factory: async_sessionmaker[AsyncSession]
    services: AuthServices


class AuthComposition:
    """Creates and disposes Auth resources exactly once per lifespan.

    `start()` is a no-op when Auth is disabled, which is what keeps legacy-only
    deployments byte-for-byte unchanged.
    """

    def __init__(
        self,
        settings: AuthSettings,
        *,
        verify_schema: AuthSchemaVerifier | None = None,
        email_sender: EmailSender | None = None,
    ) -> None:
        self._settings = settings
        self._verify_schema: AuthSchemaVerifier = verify_schema or verify_auth_schema
        self._email_sender_override = email_sender
        self._resources: AuthResources | None = None
        self._started = False

    @property
    def enabled(self) -> bool:
        return self._settings.enabled

    @property
    def frontend_origin(self) -> str:
        return self._settings.frontend_origin

    @property
    def google_oauth_enabled(self) -> bool:
        return self._settings.google_oauth_enabled

    @property
    def google_oauth_client_id(self) -> str:
        return self._settings.google_oauth_client_id

    @property
    def google_oauth_redirect_url(self) -> str:
        return self._settings.google_oauth_redirect_url

    @property
    def resources(self) -> AuthResources:
        if self._resources is None:
            raise AuthStartupError("Auth resources are unavailable; Auth is disabled or not started")
        return self._resources

    async def start(self) -> None:
        if not self._settings.enabled:
            logger.info("Auth is disabled; skipping Auth resource creation")
            return
        if self._started:
            raise AuthStartupError("Auth composition has already been started")

        target = describe_database_target(self._settings.database_url)
        engine = create_auth_engine(self._settings)
        try:
            await self._verify_connectivity(engine, target)
            await self._verify_schema(engine, target)
        except AuthStartupError:
            await engine.dispose()
            raise
        except SQLAlchemyError as error:
            await engine.dispose()
            # Re-raise as a redacted error: the SQLAlchemy message can embed the
            # full connection URL, password included.
            raise AuthDatabaseUnavailableError(
                f"Auth database {target} rejected the startup check ({type(error).__name__})"
            ) from None

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        transaction = AuthUnitOfWork(session_factory)
        clock = SystemClock()
        hasher = Argon2idHasher()
        token_factory = SecureTokenFactory()
        access_tokens = JwtAccessTokenIssuer(
            signing_key=self._settings.jwt_signing_key.get_secret_value(),
            algorithm=self._settings.jwt_algorithm,
            issuer=self._settings.jwt_issuer,
            audience=self._settings.jwt_audience,
        )
        login_limiter = PostgresRateLimiter(
            session_factory,
            RateLimitPolicy(
                self._settings.login_rate_limit_attempts,
                self._settings.login_rate_limit_window_seconds,
            ),
        )
        resend_limiter = PostgresRateLimiter(
            session_factory,
            RateLimitPolicy(
                self._settings.recovery_rate_limit_attempts,
                self._settings.recovery_rate_limit_window_seconds,
            ),
        )
        recovery_limiter = PostgresRateLimiter(
            session_factory,
            RateLimitPolicy(
                self._settings.recovery_rate_limit_attempts,
                self._settings.recovery_rate_limit_window_seconds,
            ),
        )
        key_builder = HmacRateLimitKeyBuilder(self._settings.csrf_secret.get_secret_value())
        email_sender = self._email_sender_override or self._build_email_sender()
        customer = CustomerAuthService(
            transaction,
            clock,
            hasher,
            token_factory,
            access_tokens,
            login_limiter,
            resend_limiter,
            key_builder,
            email_sender,
            require_email_verification=self._settings.require_email_verification,
            customer_email_domains=self._settings.customer_email_domain_set or None,
        )
        recovery = PasswordRecoveryService(
            transaction, clock, hasher, token_factory, email_sender, recovery_limiter, key_builder
        )
        staff = StaffAuthService(
            transaction,
            clock,
            hasher,
            token_factory,
            email_sender,
            access_tokens=access_tokens,
            login_limiter=login_limiter,
            rate_limit_keys=key_builder,
        )
        google: GoogleOAuthService | None = None
        if self._settings.google_oauth_enabled:
            google = GoogleOAuthService(
                transaction,
                clock,
                hasher,
                token_factory,
                access_tokens,
                HttpxGoogleIdentityGateway(
                    client_id=self._settings.google_oauth_client_id,
                    client_secret=self._settings.google_oauth_client_secret.get_secret_value(),
                    redirect_url=self._settings.google_oauth_redirect_url,
                ),
                client_id=self._settings.google_oauth_client_id,
            )
        self._resources = AuthResources(
            engine=engine,
            email_sender=email_sender,
            session_factory=session_factory,
            services=AuthServices(customer=customer, recovery=recovery, staff=staff, google=google),
        )
        self._started = True
        logger.info("Auth started against %s", target)

    def _build_email_sender(self) -> EmailSender:
        """Pick delivery adapter without logging credentials outside development."""
        if self._settings.app_env == "development":
            logger.warning("Auth is using development email sender; credentials go to log")
            return LoggingEmailSender()
        if not self._settings.sendgrid_api_key.get_secret_value() or not self._settings.sendgrid_from_email:
            raise AuthStartupError("SendGrid configuration is required outside development")
        return SendGridEmailSender(
            api_key=self._settings.sendgrid_api_key.get_secret_value(),
            from_email=self._settings.sendgrid_from_email,
        )

    async def _verify_connectivity(self, engine: AsyncEngine, target: str) -> None:
        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise AuthDatabaseUnavailableError(
                f"Auth database {target} is unreachable ({type(error).__name__})"
            ) from None
        except OSError as error:
            raise AuthDatabaseUnavailableError(
                f"Auth database {target} is unreachable ({type(error).__name__})"
            ) from None

    async def shutdown(self) -> None:
        """Dispose Auth resources. Safe to call when never started."""
        resources, self._resources = self._resources, None
        self._started = False
        if resources is None:
            return
        await resources.engine.dispose()
        logger.info("Auth resources disposed")
