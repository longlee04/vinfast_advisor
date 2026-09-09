"""FastAPI routes for the enabled Document feature."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.auth.domain.authorization import Action
from src.document.application.contracts import (
    ArchiveDocument,
    CreateUploadedDocument,
    DetailDocument,
    DownloadDocument,
    ListDocuments,
    ListDocumentsQuery,
    UploadDocumentCommand,
)
from src.document.application.errors import (
    DocumentPersistenceError,
    DocumentStorageUnavailableError,
    DocumentUploadRejectedError,
)
from src.document.domain.errors import InvalidPageSizeError
from src.document.domain.values import DocumentId, SourceAuthority
from src.document.presentation.dependencies import (
    PrincipalDependency,
    get_document_route_services,
    require_document_action,
)
from src.document.presentation.schemas import DocumentPageResponse, DocumentResponse, DownloadResponse


class _DocumentMultipartRoute(APIRoute):
    """Normalize malformed Document multipart bodies without affecting other routers."""

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
                        content={"detail": "invalid document request"},
                    )
                raise

        return handle


@dataclass(frozen=True, slots=True)
class DocumentRouteServices:
    """Document use cases bound by infrastructure composition."""

    create: CreateUploadedDocument
    list_documents: ListDocuments
    detail: DetailDocument
    archive: ArchiveDocument
    download: DownloadDocument


def _register_document_routes(router: APIRouter, services_dependency: Callable[..., DocumentRouteServices]) -> None:
    """Register Document endpoints against a supplied service dependency."""
    services_parameter = Annotated[DocumentRouteServices, Depends(services_dependency)]

    @router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
    async def create_document(
        services: services_parameter,
        principal: PrincipalDependency,
        file: Annotated[UploadFile, File()],
        title: Annotated[str, Form(min_length=1)],
        description: Annotated[str | None, Form()] = None,
        document_type: Annotated[str | None, Form()] = None,
        source_url: Annotated[str | None, Form()] = None,
        source_authority: Annotated[SourceAuthority, Form()] = SourceAuthority.UNKNOWN,
        source_revision: Annotated[str | None, Form()] = None,
    ) -> DocumentResponse:
        authorized = require_document_action(principal, Action.CREATE_DOCUMENT)
        try:
            document = await services.create.execute(
                UploadDocumentCommand(
                    title=title,
                    actor_id=authorized.actor_id,
                    data=file.file,
                    filename=file.filename or "upload",
                    content_type=file.content_type or "application/octet-stream",
                    description=description,
                    document_type=document_type,
                    source_url=source_url,
                    source_authority=source_authority,
                    source_revision=source_revision,
                )
            )
        except DocumentUploadRejectedError as error:
            raise HTTPException(status_code=error.status_code, detail="document upload rejected") from error
        except DocumentStorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="document storage unavailable"
            ) from error
        except DocumentPersistenceError as error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="document could not be saved"
            ) from error
        return DocumentResponse.from_document(document)

    @router.get("", response_model=DocumentPageResponse)
    async def list_documents(
        services: services_parameter,
        principal: PrincipalDependency,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> DocumentPageResponse:
        require_document_action(principal, Action.READ_DOCUMENT)
        try:
            documents = await services.list_documents.execute(ListDocumentsQuery(page=page, page_size=page_size))
        except InvalidPageSizeError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="invalid pagination"
            ) from error
        return DocumentPageResponse(
            items=tuple(DocumentResponse.from_document(document) for document in documents),
            page=page,
            page_size=page_size,
        )

    @router.get("/{document_id}", response_model=DocumentResponse)
    async def detail_document(
        services: services_parameter, principal: PrincipalDependency, document_id: str
    ) -> DocumentResponse:
        require_document_action(principal, Action.READ_DOCUMENT)
        document = await services.detail.execute(DocumentId(document_id))
        if document is None or document.archived_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found")
        return DocumentResponse.from_document(document)

    @router.get("/{document_id}/download", response_model=DownloadResponse)
    async def download_document(
        services: services_parameter, principal: PrincipalDependency, document_id: str
    ) -> DownloadResponse:
        authorized = require_document_action(principal, Action.READ_DOCUMENT)
        try:
            url = await services.download.execute(DocumentId(document_id), authorized.actor_id, authorized.role)
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found") from error
        except DocumentStorageUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="document storage unavailable"
            ) from error
        return DownloadResponse(url=url)

    @router.post("/{document_id}/archive", response_model=DocumentResponse)
    async def archive_document(
        services: services_parameter, principal: PrincipalDependency, document_id: str
    ) -> DocumentResponse:
        authorized = require_document_action(principal, Action.ARCHIVE_DOCUMENT)
        try:
            document = await services.archive.execute(DocumentId(document_id), authorized.actor_id)
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found") from error
        return DocumentResponse.from_document(document)


router = APIRouter(
    prefix="/documents",
    tags=["documents"],
    route_class=_DocumentMultipartRoute,
    dependencies=[Depends(get_document_route_services)],
)
_register_document_routes(router, get_document_route_services)


def build_document_router(services: DocumentRouteServices) -> APIRouter:
    """Build a compatibility router with concrete services for existing tests."""
    compatibility_router = APIRouter(prefix="/documents", tags=["documents"], route_class=_DocumentMultipartRoute)
    _register_document_routes(compatibility_router, lambda: services)
    return compatibility_router
