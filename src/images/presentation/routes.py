"""FastAPI routes for the enabled Image feature."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.auth.domain.authorization import Action
from src.images.application.contracts import (
    DeleteImage,
    DetailImage,
    DownloadImage,
    ListImages,
    UploadImage,
    UploadImageCommand,
)
from src.images.application.errors import (
    ImageNotFoundError,
    ImagePersistenceError,
    ImageStorageUnavailableError,
    ImageUploadRejectedError,
)
from src.images.domain.values import ImageId
from src.images.presentation.dependencies import (
    PrincipalDependency,
    get_image_route_services,
    require_image_action,
)
from src.images.presentation.schemas import (
    ImageDownloadResponse,
    ImageListResponse,
    ImageResponse,
)


class _ImageMultipartRoute(APIRoute):
    """Normalize malformed Image multipart bodies without affecting other routers."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        """Wrap only this router's multipart parsing error into its stable contract."""
        route_handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await route_handler(request)
            except StarletteHTTPException as error:
                is_multipart = request.headers.get("content-type", "").startswith("multipart/form-data")
                if error.status_code == status.HTTP_400_BAD_REQUEST and is_multipart:
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        content={"detail": "invalid image request"},
                    )
                raise

        return handle


@dataclass(frozen=True, slots=True)
class ImageRouteServices:
    """Image use cases bound by infrastructure composition."""

    upload: UploadImage
    list_images: ListImages
    detail: DetailImage
    download: DownloadImage
    delete: DeleteImage


def _register_image_routes(router: APIRouter, services_dependency: Callable[..., ImageRouteServices]) -> None:
    """Register Image endpoints against a supplied service dependency."""
    services_parameter = Annotated[ImageRouteServices, Depends(services_dependency)]

    @router.post("", response_model=ImageResponse, status_code=status.HTTP_201_CREATED)
    async def upload_image(
        principal: PrincipalDependency,
        services: services_parameter,
        file: Annotated[UploadFile, File()],
    ) -> ImageResponse:
        authorized = require_image_action(principal, Action.UPLOAD_IMAGE)
        try:
            image = await services.upload.execute(
                UploadImageCommand(
                    filename=file.filename or "upload",
                    content_type=file.content_type or "application/octet-stream",
                    data=file.file,
                    actor_id=authorized.actor_id,
                )
            )
        except ImageUploadRejectedError as error:
            raise HTTPException(status_code=error.status_code, detail="image upload rejected") from error
        except ImageStorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="image storage unavailable"
            ) from error
        except ImagePersistenceError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="image could not be saved"
            ) from error
        return ImageResponse.from_image(image)

    @router.get("", response_model=ImageListResponse)
    async def list_images(
        principal: PrincipalDependency,
        services: services_parameter,
    ) -> ImageListResponse:
        require_image_action(principal, Action.READ_IMAGE)
        images = await services.list_images.execute()
        return ImageListResponse(items=tuple(ImageResponse.from_image(image) for image in images))

    @router.get("/{image_id}", response_model=ImageResponse)
    async def detail_image(
        principal: PrincipalDependency,
        services: services_parameter,
        image_id: str,
    ) -> ImageResponse:
        require_image_action(principal, Action.READ_IMAGE)
        try:
            image = await services.detail.execute(ImageId(image_id))
        except ImageNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found") from error
        return ImageResponse.from_image(image)

    @router.get("/{image_id}/download", response_model=ImageDownloadResponse)
    async def download_image(
        principal: PrincipalDependency,
        services: services_parameter,
        image_id: str,
    ) -> ImageDownloadResponse:
        require_image_action(principal, Action.READ_IMAGE)
        try:
            url = await services.download.execute(ImageId(image_id))
        except ImageNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found") from error
        except ImageStorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="image storage unavailable"
            ) from error
        return ImageDownloadResponse(url=url)

    @router.delete("/{image_id}", response_model=ImageResponse)
    async def delete_image(
        principal: PrincipalDependency,
        services: services_parameter,
        image_id: str,
    ) -> ImageResponse:
        authorized = require_image_action(principal, Action.DELETE_IMAGE)
        try:
            image = await services.delete.execute(ImageId(image_id), authorized.actor_id)
        except ImageNotFoundError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="image not found") from error
        return ImageResponse.from_image(image)


router = APIRouter(
    prefix="/images",
    tags=["images"],
    route_class=_ImageMultipartRoute,
    dependencies=[Depends(get_image_route_services)],
)
_register_image_routes(router, get_image_route_services)


def build_image_router(services: ImageRouteServices) -> APIRouter:
    """Build a compatibility router with concrete services for tests."""
    compatibility_router = APIRouter(prefix="/images", tags=["images"], route_class=_ImageMultipartRoute)
    _register_image_routes(compatibility_router, lambda: services)
    return compatibility_router
