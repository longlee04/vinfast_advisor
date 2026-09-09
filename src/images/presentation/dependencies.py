"""Authentication and authorization dependencies for Image routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException, Request, status

from src.auth.domain.authorization import Action, Role, authorize
from src.auth.domain.errors import AuthorizationError

if TYPE_CHECKING:
    from src.images.presentation.routes import ImageRouteServices


@dataclass(frozen=True, slots=True)
class CurrentPrincipal:
    """Authenticated actor supplied by the Auth presentation boundary."""

    actor_id: str
    role: Role


async def get_current_principal() -> CurrentPrincipal:
    """Require an Auth-provided principal; applications override this narrow seam."""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")


PrincipalDependency = Annotated[CurrentPrincipal, Depends(get_current_principal)]


async def get_image_route_services(request: Request) -> ImageRouteServices:
    """Resolve enabled Image services from application state per request."""
    composition = getattr(request.app.state, "image", None)
    if composition is None or not composition.enabled or composition.resources is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Image service unavailable")
    return composition.resources.route_services()


ImageServicesDependency = Annotated["ImageRouteServices", Depends(get_image_route_services)]


def require_image_action(principal: CurrentPrincipal, action: Action) -> CurrentPrincipal:
    """Apply the authoritative default-deny Auth policy to a principal."""
    try:
        authorize(principal.role, action, actor_id=principal.actor_id)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden") from error
    return principal
