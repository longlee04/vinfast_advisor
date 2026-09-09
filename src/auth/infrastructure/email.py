"""Email adapters behind the Auth application port."""

import logging
from dataclasses import dataclass, field

import anyio
import sendgrid
from sendgrid.helpers.mail import Mail

from src.auth.application.ports import EmailDeliveryError, EmailSender
from src.auth.domain.values import NormalizedEmail, PlaintextPassword, PlaintextToken

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SendGridEmailSender(EmailSender):
    """Send Auth messages through the configured SendGrid account."""

    api_key: str
    from_email: str

    async def _send(self, recipient: NormalizedEmail, subject: str, body: str) -> None:
        message = Mail(
            from_email=self.from_email,
            to_emails=str(recipient),
            subject=subject,
            plain_text_content=body,
        )
        try:
            client = sendgrid.SendGridAPIClient(self.api_key)
            await anyio.to_thread.run_sync(
                client.send,
                message,
            )
        except Exception as error:
            raise EmailDeliveryError("email delivery failed") from error

    async def send_verification(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        await self._send(recipient, "Verify your P-150 account", f"Verification token: {token.reveal()}")

    async def send_temporary_password(self, *, recipient: NormalizedEmail, password: PlaintextPassword) -> None:
        await self._send(recipient, "Your temporary P-150 password", f"Temporary password: {password.reveal()}")

    async def send_password_reset(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        await self._send(recipient, "Reset your P-150 password", f"Password reset token: {token.reveal()}")


class LoggingEmailSender(EmailSender):
    """Development-only sender that writes credentials to application logs."""

    async def send_temporary_password(self, *, recipient: NormalizedEmail, password: PlaintextPassword) -> None:
        logger.warning(
            "development email sender: temporary password for %s is %s",
            recipient,
            password.reveal(),
        )

    async def send_verification(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        logger.warning(
            "development email sender: verification token for %s is %s",
            recipient,
            token.reveal(),
        )

    async def send_password_reset(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        logger.warning(
            "development email sender: reset token for %s is %s",
            recipient,
            token.reveal(),
        )


@dataclass(slots=True)
class DeterministicEmailSender(EmailSender):
    """In-memory test adapter; plaintext exists only for the test assertion."""

    fail_delivery: bool = False
    deliveries: list[tuple[NormalizedEmail, PlaintextToken | PlaintextPassword]] = field(default_factory=list)
    temporary_password_deliveries: list[tuple[NormalizedEmail, PlaintextPassword]] = field(default_factory=list)
    reset_deliveries: list[tuple[NormalizedEmail, PlaintextToken]] = field(default_factory=list)

    async def send_verification(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        """Record a deterministic verification delivery for integration assertions."""
        if self.fail_delivery:
            raise EmailDeliveryError("email delivery failed")
        self.deliveries.append((recipient, token))

    async def send_temporary_password(self, *, recipient: NormalizedEmail, password: PlaintextPassword) -> None:
        """Record an in-memory test delivery or simulate a provider rejection."""
        if self.fail_delivery:
            raise EmailDeliveryError("email delivery failed")
        self.temporary_password_deliveries.append((recipient, password))
        self.deliveries.append((recipient, password))

    async def send_password_reset(self, *, recipient: NormalizedEmail, token: PlaintextToken) -> None:
        """Record a reset delivery or simulate a provider rejection."""
        if self.fail_delivery:
            raise EmailDeliveryError("email delivery failed")
        self.reset_deliveries.append((recipient, token))
