"""Enabled-only Document adapter composition."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from minio import Minio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from src.document.application.contracts import (
    ArchiveDocument,
    CreateUploadedDocument,
    DetailDocument,
    DownloadDocument,
    ListDocuments,
    ListDocumentsQuery,
)
from src.document.application.policy_corpus import (
    DefaultPolicyCorpusBuilder,
    PolicyCorpusBuilder,
    PolicyCorpusSummary,
    PolicyCorpusSummaryReader,
)
from src.document.application.policy_notifications import (
    AnalyzePolicyDocument,
    ListPublishedPolicyNotifications,
    PolicyAnalyzer,
    PolicyNotificationRepository,
    PolicyTextExtractor,
    PublishPolicyNotification,
    UpdatePolicyNotificationDraft,
)
from src.document.application.ports import DocumentRepository, DocumentUnitOfWork, ObjectStorage
from src.document.domain.entities import Document
from src.document.domain.policy_notifications import PolicyNotification, PolicyNotificationId
from src.document.domain.values import DocumentId
from src.document.infrastructure.minio_storage import MinioObjectStorage
from src.document.infrastructure.policy_analyzer import OpenAIPolicyAnalyzer
from src.document.infrastructure.policy_embedding import OpenAIPolicyEmbeddingAdapter
from src.document.infrastructure.policy_text import PolicyDocumentTextExtractor
from src.document.infrastructure.policy_vehicle_resolver import (
    SqlAlchemyPolicyVehicleResolver,
)
from src.document.infrastructure.repositories import DocumentUnitOfWork as SqlAlchemyDocumentUnitOfWork
from src.document.infrastructure.repositories import (
    SqlAlchemyDocumentRepository,
    SqlAlchemyPolicyNotificationRepository,
    SqlAlchemyVehicleDocumentRepository,
)
from src.document.infrastructure.settings import DocumentSettings
from src.document.presentation.routes import DocumentRouteServices


@dataclass(frozen=True, slots=True)
class DocumentResources:
    """Concrete adapters serving the enabled feature, or injected by HTTP tests."""

    repository: DocumentRepository
    unit_of_work: DocumentUnitOfWork
    storage: ObjectStorage
    engine: AsyncEngine | None = None
    policy_repository: PolicyNotificationRepository | None = None
    policy_analyzer: PolicyAnalyzer | None = None
    policy_text_extractor: PolicyTextExtractor | None = None
    policy_corpus_builder: PolicyCorpusBuilder | None = None
    policy_corpus_reader: PolicyCorpusSummaryReader | None = None

    def route_services(self) -> DocumentRouteServices:
        """Expose use cases while keeping presentation independent of infrastructure."""
        return DocumentRouteServices(
            create=CreateUploadedDocument(self.unit_of_work, self.storage),
            list_documents=ListDocuments(self.repository),
            detail=DetailDocument(self.repository),
            archive=ArchiveDocument(self.repository),
            download=DownloadDocument(self.repository, self.storage),
        )

    def policy_route_services(self) -> "PolicyNotificationRouteServices":
        """Expose policy use cases only when all feature adapters are configured."""
        if (
            self.policy_repository is None
            or self.policy_analyzer is None
            or self.policy_text_extractor is None
            or self.policy_corpus_builder is None
            or self.policy_corpus_reader is None
        ):
            raise RuntimeError("policy notification services are unavailable")
        from src.document.presentation.policy_routes import PolicyNotificationRouteServices

        return PolicyNotificationRouteServices(
            analyze=AnalyzePolicyDocument(
                self.repository,
                self.unit_of_work,
                self.storage,
                self.policy_text_extractor,
                self.policy_analyzer,
                self.policy_corpus_builder,
            ),
            update=UpdatePolicyNotificationDraft(self.unit_of_work),
            publish=PublishPolicyNotification(self.unit_of_work),
            list_published=ListPublishedPolicyNotifications(self.policy_repository),
            corpus_summary=self.policy_corpus_reader,
        )


class DocumentComposition:
    """Construct concrete Document adapters only for enabled deployments."""

    def __init__(self, settings: DocumentSettings, resources: DocumentResources | None = None) -> None:
        self._settings = settings
        self._resources = resources

    @property
    def enabled(self) -> bool:
        """Return whether the Document feature is enabled."""
        return self._settings.enabled

    @property
    def resources(self) -> DocumentResources | None:
        """Return constructed or injected resources without forcing disabled setup."""
        return self._resources

    async def start(self) -> None:
        """Create the database and storage adapters for enabled deployments."""
        if not self.enabled or self._resources is not None:
            return
        engine = create_async_engine(self._settings.database_url, pool_pre_ping=True)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        client = Minio(
            self._settings.minio_endpoint.removeprefix("http://").removeprefix("https://"),
            access_key=self._settings.access_key.get_secret_value(),
            secret_key=self._settings.secret_key.get_secret_value(),
            secure=self._settings.minio_endpoint.startswith("https://"),
        )
        try:
            bucket = self._settings.bucket_name
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except Exception:
            pass
        repository = _SessionRepository(session_factory)
        policy_repository = _SessionPolicyNotificationRepository(session_factory)
        self._resources = DocumentResources(
            repository=repository,
            unit_of_work=SqlAlchemyDocumentUnitOfWork(session_factory),
            storage=MinioObjectStorage(client, self._settings),
            engine=engine,
            policy_repository=policy_repository,
            policy_analyzer=OpenAIPolicyAnalyzer(),
            policy_text_extractor=PolicyDocumentTextExtractor(),
            policy_corpus_builder=DefaultPolicyCorpusBuilder(
                SqlAlchemyPolicyVehicleResolver(session_factory),
                OpenAIPolicyEmbeddingAdapter(),
            ),
            policy_corpus_reader=_SessionPolicyCorpusReader(session_factory),
        )

    async def shutdown(self) -> None:
        """Dispose only the engine owned by enabled production composition."""
        resources, self._resources = self._resources, None
        if resources is not None and resources.engine is not None:
            await resources.engine.dispose()


class _SessionRepository:
    """Open a short-lived session for read and archive use cases."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def add(self, document: Document) -> Document:
        async with self._session_factory() as session, session.begin():
            await SqlAlchemyDocumentRepository(session).add(document)
        return document

    async def list(self, query: ListDocumentsQuery) -> tuple[Document, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyDocumentRepository(session).list(query)

    async def get(self, document_id: DocumentId) -> Document | None:
        async with self._session_factory() as session:
            return await SqlAlchemyDocumentRepository(session).get(document_id)

    async def get_by_source_hash(self, source_url: str, content_hash: str) -> Document | None:
        async with self._session_factory() as session:
            return await SqlAlchemyDocumentRepository(session).get_by_source_hash(
                source_url, content_hash
            )

    async def get_latest_by_source_url(self, source_url: str) -> Document | None:
        async with self._session_factory() as session:
            return await SqlAlchemyDocumentRepository(session).get_latest_by_source_url(source_url)

    async def archive(self, document_id: DocumentId, actor_id: str, archived_at: datetime) -> Document:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyDocumentRepository(session).archive(document_id, actor_id, archived_at)


class _SessionPolicyNotificationRepository:
    """Open short-lived sessions for policy notification reads."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get(self, notification_id: PolicyNotificationId) -> PolicyNotification | None:
        async with self._session_factory() as session:
            return await SqlAlchemyPolicyNotificationRepository(session).get(notification_id)

    async def get_by_source(self, source_document_id: DocumentId) -> PolicyNotification | None:
        async with self._session_factory() as session:
            return await SqlAlchemyPolicyNotificationRepository(session).get_by_source(source_document_id)

    async def add(self, notification: PolicyNotification) -> PolicyNotification:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyPolicyNotificationRepository(session).add(notification)

    async def save(self, notification: PolicyNotification) -> PolicyNotification:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyPolicyNotificationRepository(session).save(notification)

    async def list_published(self, page: int, page_size: int) -> tuple[PolicyNotification, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyPolicyNotificationRepository(session).list_published(page, page_size)

    async def activate_scopes_for_source(
        self,
        source_document_id: str,
        actor_id: str,
        approved_at: datetime,
        resolution: "PolicyConflictResolution | None" = None,
    ) -> int:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyPolicyNotificationRepository(session).activate_scopes_for_source(
                source_document_id, actor_id, approved_at, resolution
            )

    async def set_current_default(
        self,
        scope_id: str,
        actor_id: str,
        changed_at: datetime,
    ) -> "PolicyScope":
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyPolicyNotificationRepository(session).set_current_default(
                scope_id,
                actor_id,
                changed_at,
            )


class _SessionPolicyCorpusReader:
    """Open a short-lived read session for Admin corpus readiness."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def summary_for_source(self, source_document_id: str) -> PolicyCorpusSummary:
        async with self._session_factory() as session:
            return await SqlAlchemyVehicleDocumentRepository(session).summary_for_source(
                source_document_id
            )


if TYPE_CHECKING:
    from src.document.domain.policy_scopes import PolicyConflictResolution, PolicyScope
    from src.document.presentation.policy_routes import PolicyNotificationRouteServices
