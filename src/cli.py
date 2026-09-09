"""Secure command-line entry point for Auth operations."""

import argparse
import getpass
import hashlib
import secrets
import sys
from typing import NoReturn

import anyio

from src.auth.application.ports import EmailDeliveryError
from src.auth.application.staff_auth import StaffAuthService
from src.auth.composition import AuthComposition
from src.auth.domain.authorization import Role
from src.auth.domain.errors import AuthDomainError
from src.auth.domain.values import TokenHash, UserId
from src.auth.infrastructure.argon2_hasher import Argon2idHasher
from src.auth.infrastructure.clock import SystemClock
from src.auth.infrastructure.repositories import AuthUnitOfWork
from src.auth.settings import get_auth_settings


class _SecureTokenFactory:
    """CSPRNG token factory supplied to application use cases."""

    def new_secret(self) -> str:
        return secrets.token_urlsafe(32)

    def hash(self, secret: str) -> TokenHash:
        return TokenHash(hashlib.sha256(secret.encode("utf-8")).hexdigest())


class _NoEmailSender:
    """Bootstrap cannot send email, so accidental delivery is refused."""

    async def send_temporary_password(self, **_: str) -> None:
        raise RuntimeError("create-admin does not send email")


class _SecureArgumentParser(argparse.ArgumentParser):
    """Avoid reflecting unsupported password option values into terminal output."""

    def error(self, message: str) -> NoReturn:
        if message.startswith("unrecognized arguments: --password"):
            message = "unrecognized arguments: --password"
        super().error(message)


def _parser() -> argparse.ArgumentParser:
    parser = _SecureArgumentParser(prog="python -m src.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create_admin = commands.add_parser("create-admin", help="bootstrap the first Admin account")
    create_admin.add_argument("--email", required=True, help="Admin email address")
    create_staff = commands.add_parser(
        "create-staff", help="create a staff account with a delivered temporary password"
    )
    create_staff.add_argument("--email", required=True, help="Staff email address")
    create_staff.add_argument("--actor-id", required=True, help="Existing Admin account ID")
    create_staff.add_argument("--role", choices=(Role.ADVISOR.value, Role.ADMIN.value), required=True)
    return parser


def _read_password() -> str:
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm admin password: ")
    if password != confirmation:
        raise ValueError("password confirmation did not match")
    return password


async def _create_staff(actor_id: str, email: str, role: str) -> bool:
    settings = get_auth_settings()
    composition = AuthComposition(settings)
    await composition.start()
    try:
        await composition.resources.services.staff.create_staff(UserId(actor_id), email, Role(role))
        return True
    finally:
        await composition.shutdown()


async def _create_admin(email: str, password: str) -> bool:
    settings = get_auth_settings()
    composition = AuthComposition(settings)
    await composition.start()
    try:
        service = StaffAuthService(
            AuthUnitOfWork(composition.resources.session_factory),
            SystemClock(),
            Argon2idHasher(),
            _SecureTokenFactory(),
            _NoEmailSender(),
        )
        return await service.bootstrap_first_admin(email, password)
    finally:
        await composition.shutdown()


def _main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "create-staff":
            anyio.run(_create_staff, arguments.actor_id, arguments.email, arguments.role)
            print("Staff account created; temporary password sent through configured email sender.")
            return 0
        password = _read_password()
        created = anyio.run(_create_admin, arguments.email, password)
    except (AuthDomainError, EmailDeliveryError, EOFError, KeyboardInterrupt, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    if created:
        print("First Admin account created.")
        return 0
    print("An active Admin account already exists.", file=sys.stderr)
    return 1


def main() -> NoReturn:
    """Run the Auth CLI and return its process status."""
    raise SystemExit(_main())


if __name__ == "__main__":
    main()
