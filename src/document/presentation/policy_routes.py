"""FastAPI routes for Admin policy analysis and customer publications."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.auth.domain.authorization import Action
from src.document.application.errors import (
    DocumentStorageUnavailableError,
    DocumentTextTooLargeError,
    DocumentTextUnavailableError,
    PolicyAnalyzerUnavailableError,
    PolicyCorpusEmptyError,
    PolicyEmbeddingUnavailableError,
    PolicySourceUnreviewedError,
    PolicyVehicleResolutionError,
    UnsupportedPolicyDocumentError,
)
from src.document.application.policy_corpus import PolicyCorpusSummaryReader
from src.document.application.policy_notifications import (
    AnalyzePolicyDocument,
    ListPublishedPolicyNotifications,
    PublishPolicyNotification,
    UpdatePolicyNotificationDraft,
)
from src.document.domain.policy_notifications import (
    InvalidPolicyNotificationError,
    PolicyNotificationConflictError,
    PolicyNotificationId,
)
from src.document.domain.values import DocumentId
from src.document.presentation.dependencies import (
    PrincipalDependency,
    get_policy_notification_route_services,
    require_document_action,
)
from src.document.presentation.schemas import (
    PolicyNotificationResponse,
    PublishedNotificationPageResponse,
    PublishedNotificationResponse,
    PublishPolicyNotificationRequest,
    UpdatePolicyNotificationRequest,
)


@dataclass(frozen=True, slots=True)
class PolicyNotificationRouteServices:
    """Policy notification use cases bound by the Document composition."""

    analyze: AnalyzePolicyDocument
    update: UpdatePolicyNotificationDraft
    publish: PublishPolicyNotification
    list_published: ListPublishedPolicyNotifications
    corpus_summary: PolicyCorpusSummaryReader | None = None


def _register_policy_routes(
    router: APIRouter,
    services_dependency: Callable[..., PolicyNotificationRouteServices],
) -> None:
    services_parameter = Annotated[PolicyNotificationRouteServices, Depends(services_dependency)]

    @router.post(
        "/documents/{document_id}/analyze-policy",
        response_model=PolicyNotificationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def analyze_policy_document(
        document_id: str,
        services: services_parameter,
        principal: PrincipalDependency,
    ) -> PolicyNotificationResponse:
        authorized = require_document_action(principal, Action.POLICY_NOTIFICATION_MANAGE)
        try:
            notification = await services.analyze.execute(DocumentId(document_id), authorized.actor_id)
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="document not found") from error
        except UnsupportedPolicyDocumentError as error:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="document type is not supported for policy analysis",
            ) from error
        except DocumentTextUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Document does not contain extractable text; OCR is not supported in this MVP.",
            ) from error
        except DocumentTextTooLargeError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="document text exceeds the synchronous policy analysis limit",
            ) from error
        except (PolicyCorpusEmptyError, PolicyVehicleResolutionError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="policy evidence or affected vehicle scope requires Admin correction",
            ) from error
        except PolicyEmbeddingUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="policy embedding service is unavailable",
            ) from error
        except PolicyNotificationConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="document already has a policy analysis",
            ) from error
        except (PolicyAnalyzerUnavailableError, DocumentStorageUnavailableError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="policy analysis is temporarily unavailable",
            ) from error
        corpus = (
            await services.corpus_summary.summary_for_source(notification.source_document_id.value)
            if services.corpus_summary is not None
            else None
        )
        return PolicyNotificationResponse.from_notification(notification, corpus)

    @router.patch("/policy-notifications/{notification_id}", response_model=PolicyNotificationResponse)
    async def update_policy_notification(
        notification_id: str,
        payload: UpdatePolicyNotificationRequest,
        services: services_parameter,
        principal: PrincipalDependency,
    ) -> PolicyNotificationResponse:
        authorized = require_document_action(principal, Action.POLICY_NOTIFICATION_MANAGE)
        try:
            update_arguments = {
                "actor_id": authorized.actor_id,
                "title": payload.title,
                "content": payload.content,
            }
            if payload.scopes is not None:
                update_arguments["scopes"] = payload.scopes
            notification = await services.update.execute(
                PolicyNotificationId(notification_id),
                **update_arguments,
            )
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found") from error
        except PolicyNotificationConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="published notification is immutable",
            ) from error
        except InvalidPolicyNotificationError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="title and content are required",
            ) from error
        corpus = (
            await services.corpus_summary.summary_for_source(notification.source_document_id.value)
            if services.corpus_summary is not None
            else None
        )
        return PolicyNotificationResponse.from_notification(notification, corpus)

    @router.post(
        "/policy-notifications/{notification_id}/publish",
        response_model=PolicyNotificationResponse,
    )
    async def publish_policy_notification(
        notification_id: str,
        services: services_parameter,
        principal: PrincipalDependency,
        payload: PublishPolicyNotificationRequest | None = None,
    ) -> PolicyNotificationResponse:
        authorized = require_document_action(principal, Action.POLICY_NOTIFICATION_MANAGE)
        try:
            if payload is not None and payload.resolution is not None:
                notification = await services.publish.execute(
                    PolicyNotificationId(notification_id),
                    authorized.actor_id,
                    payload.resolution,
                )
            else:
                notification = await services.publish.execute(
                    PolicyNotificationId(notification_id),
                    authorized.actor_id,
                )
        except LookupError as error:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="notification not found") from error
        except (PolicyCorpusEmptyError, PolicySourceUnreviewedError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="policy source, scope, or corpus is not ready for publication",
            ) from error
        except PolicyNotificationConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "POLICY_SCOPE_CONFLICT",
                    "message": "Phạm vi phiên bản đang chồng lấn; hãy sửa cohort trước khi publish.",
                },
            ) from error
        corpus = (
            await services.corpus_summary.summary_for_source(notification.source_document_id.value)
            if services.corpus_summary is not None
            else None
        )
        return PolicyNotificationResponse.from_notification(notification, corpus)

    @router.get("/notifications", response_model=PublishedNotificationPageResponse)
    async def list_published_notifications(
        services: services_parameter,
        principal: PrincipalDependency,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> PublishedNotificationPageResponse:
        require_document_action(principal, Action.POLICY_NOTIFICATION_READ)
        items = await services.list_published.execute(page=page, page_size=page_size)
        return PublishedNotificationPageResponse(
            items=tuple(PublishedNotificationResponse.from_notification(item) for item in items),
            page=page,
            page_size=page_size,
        )


router = APIRouter(tags=["policy-notifications"], dependencies=[Depends(get_policy_notification_route_services)])
_register_policy_routes(router, get_policy_notification_route_services)


def build_policy_notification_router(services: PolicyNotificationRouteServices) -> APIRouter:
    """Build a concrete-services router for deterministic HTTP tests."""
    compatibility_router = APIRouter(tags=["policy-notifications"])
    _register_policy_routes(compatibility_router, lambda: services)
    return compatibility_router
