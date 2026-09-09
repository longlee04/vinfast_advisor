"""Safely restore one ACTIVE policy scope as the current default; never delete evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from src.config import get_settings  # noqa: E402
from src.document.application.policy_notifications import SetCurrentPolicyDefault  # noqa: E402
from src.document.composition import DocumentComposition  # noqa: E402
from src.document.domain.policy_scopes import PolicyScopeId  # noqa: E402
from src.document.infrastructure.settings import DocumentSettings  # noqa: E402


async def _run(args: argparse.Namespace) -> int:
    scope_id = PolicyScopeId(args.scope_id).value
    if not args.apply:
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_NOT_CHANGED",
                    "scope_id": scope_id,
                    "instruction": "Repeat with --apply and --confirm-scope-id after review.",
                },
                indent=2,
            )
        )
        return 0
    if args.confirm_scope_id != scope_id:
        raise SystemExit("--confirm-scope-id must exactly match --scope-id")
    if get_settings().app_env != args.target_env:
        raise SystemExit("--target-env must match APP_ENV")
    settings = DocumentSettings()
    if not settings.enabled:
        raise SystemExit("DOCUMENT_ENABLED=true and reviewed database settings are required")
    composition = DocumentComposition(settings)
    await composition.start()
    try:
        resources = composition.resources
        if resources is None:
            raise SystemExit("Document resources are unavailable")
        selected = await SetCurrentPolicyDefault(resources.unit_of_work).execute(
            scope_id,
            args.actor_id,
        )
        print(
            json.dumps(
                {
                    "status": "CURRENT_DEFAULT_CHANGED",
                    "scope_id": selected.id.value,
                    "source_document_id": selected.source_document_id,
                    "updated_by": args.actor_id,
                },
                indent=2,
            )
        )
        return 0
    finally:
        await composition.shutdown()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-id", required=True)
    parser.add_argument("--actor-id", required=True)
    parser.add_argument(
        "--target-env",
        required=True,
        choices=("development", "test", "production"),
    )
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-scope-id")
    return parser


def main() -> int:
    """Execute an explicit, exact-scope default switch."""
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
