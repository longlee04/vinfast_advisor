"""Authentication and authorization dependencies for Document routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status

from src.auth.domain.authorization import Action, Role, authorize
from src.auth.domain.errors import AuthorizationError

if TYPE_CHECKING:
    from src.document.presentation.policy_routes import PolicyNotificationRouteServices
    from src.document.presentation.routes import DocumentRouteServices


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Authenticated actor supplied by the Auth presentation boundary."""

    actor_id: str
    role: Role


async def get_current_principal() -> CurrentPrincipal:
    """Require an Auth-provided principal; applications override this narrow seam."""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


PrincipalDependency = Annotated[CurrentPrincipal, Depends(get_current_principal)]


async def get_document_route_services(request: Request) -> DocumentRouteServices:
    """Resolve enabled Document services from application state per request."""
    composition = getattr(request.app.state, "document", None)
    if composition is None or not composition.enabled or composition.resources is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document service unavailable")
    return composition.resources.route_services()


DocumentServicesDependency = Annotated["DocumentRouteServices", Depends(get_document_route_services)]


async def get_policy_notification_route_services(request: Request) -> PolicyNotificationRouteServices:
    """Resolve policy notification services from the existing Document composition."""
    composition = getattr(request.app.state, "document", None)
    if composition is None or not composition.enabled or composition.resources is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Document service unavailable")
    try:
        return composition.resources.policy_route_services()
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Policy notification service unavailable",
        ) from error


def require_document_action(principal: CurrentPrincipal, action: Action) -> CurrentPrincipal:
    """Apply the authoritative default-deny Auth policy to a principal."""
    try:
        authorize(principal.role, action, actor_id=principal.actor_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from error
    return principal
