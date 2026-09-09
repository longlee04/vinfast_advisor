# Data flow, transaction, and migration map: Document module

## Checkpoint conclusion

Document separates two kinds of data deliberately: raw uploaded bytes live in a private MinIO bucket, while PostgreSQL stores the durable metadata, integrity hash, storage reference, state, and audit trail. `Document` is a pure frozen domain value/entity; it does not know SQLAlchemy, MinIO, sessions, commits, or transactions. The application coordinates the two external systems through ports, and the infrastructure `DocumentUnitOfWork` owns the PostgreSQL metadata transaction. Since MinIO and PostgreSQL do not share a distributed transaction, an uploaded object is removed as compensation if metadata persistence fails.

This continues the module placement recorded in [00-repository-map.md](00-repository-map.md): `presentation → application → domain`, with infrastructure adapters implementing the application ports.

## 1. Domain representation versus persistence model

| Khái niệm | Domain representation | SQLAlchemy representation | Mapping ở đâu |
| --- | --- | --- | --- |
| Document | `Document` frozen dataclass; `DocumentMetadata`; `DocumentId`; `ApprovalStatus` and `ProcessingStatus` values | mutable `DocumentRow`, table `documents` | `src/document/infrastructure/repositories.py::_to_document`; `SqlAlchemyDocumentRepository.add` |
| Archive state | `Document.archive(actor_id, archived_at)` returns self when already archived; `archived_at`/`archived_by` express the state | nullable `archived_at` and `archived_by`; active-row predicate is `archived_at IS NULL` | `SqlAlchemyDocumentRepository.archive`; application `ArchiveDocument`; route authorization precedes it |
| Object key | optional opaque `Document.object_key`; no client-selected key rule in the entity | nullable `documents.object_key` string metadata column | infrastructure `generate_object_key` creates `documents/{document_id}/{token}`; `MinioObjectStorage.upload` returns it; `CreateUploadedDocument` puts it on the domain document; repository persists it |

The ORM row is intentionally mutable because SQLAlchemy requires it; the domain `Document` is frozen and represents business data and rules. `_to_document` converts ORM strings to `DocumentId`, `ApprovalStatus`, and `ProcessingStatus`, and normalizes datetimes to UTC. `add` performs the reverse conversion in an `INSERT`.

`Document.create` enforces a non-blank title and initializes `approval_status=draft`, `processing_status=not_started`, audit fields, and a generated UUID. `ensure_processing_transition` restricts state transitions in the domain. The database independently protects a subset of invariants, but it does not replace domain validation (for example, `length(title) > 0` permits a whitespace-only title).

## 2. Upload flow and transaction boundary

```text
multipart request
→ schema/dependency
→ application contract
→ object storage write
→ metadata transaction
→ compensation nếu metadata fail
→ response metadata
```

| Step | Concrete symbol and behavior |
| --- | --- |
| Multipart request | `presentation.routes.build_document_router` declares `POST /documents`; `create_document` accepts `UploadFile` plus `Form` fields. `_DocumentMultipartRoute` maps malformed multipart `400` to its stable `422` response. |
| Schema/dependency | `title: Form(min_length=1)` validates the external title; `PrincipalDependency` gets an authenticated principal and `require_document_action(..., Action.CREATE_DOCUMENT)` permits the admin role. |
| Application contract | The route makes `UploadDocumentCommand` and calls `CreateUploadedDocument.execute`. `ObjectStorage` and `DocumentUnitOfWork` are application ports in `application/ports.py`. |
| Object storage write | `CreateUploadedDocument` first calls `storage.upload`. `MinioObjectStorage.upload` validates MIME type/extension, reads at most 25 MiB while calculating SHA-256, generates a server-owned opaque key, then writes the bytes to the configured private MinIO bucket. It returns `StoredObject(object_key, content_hash, content_type, byte_size)`. |
| Metadata transaction | The use case copies verified storage fields into the provisional `Document`, then enters `async with uow.transaction()`. Concrete `DocumentUnitOfWork.transaction` is `async with session_factory() as session, session.begin()`; `SqlAlchemyDocumentRepository.add` inserts metadata into `documents`. Normal context exit commits; an exception rolls the metadata transaction back. |
| Compensation nếu metadata fail | `CreateUploadedDocument.execute` catches `DocumentPersistenceError` (or wraps another persistence exception as one), calls `_compensate(stored.object_key)`, and re-raises. `_compensate` calls `storage.remove`; a storage-unavailable cleanup failure is deliberately best-effort so it does not hide the database failure. |
| Response metadata | `create_document` maps the persisted `Document` using `DocumentResponse.from_document` and returns `201`. The response includes safe metadata but excludes `object_key`, content hash, audit actor IDs, and bucket details. |

The transaction cannot be on `Document`: an entity cannot atomically coordinate a SQLAlchemy session and remote MinIO operation without depending on infrastructure. The explicit Unit of Work instead gives a transaction to the repository implementation for PostgreSQL metadata only. The upload order creates a short-lived cross-system inconsistency risk, which is why compensation exists; this is not a two-phase distributed commit.

## 3. Read, download, and archive flow

| Operation | Actor / allowed roles | DB effect | Storage effect | Response / idempotency |
| --- | --- | --- | --- | --- |
| List | `require_document_action(..., Action.READ_DOCUMENT)`: Admin, Advisor; Customer denied by Auth action matrix | `SqlAlchemyDocumentRepository.list` selects only `archived_at IS NULL`, ordered `created_at DESC, id DESC`, with bounded pagination | none | `DocumentPageResponse`; read-only |
| Detail | Admin, Advisor | `get` looks up the metadata row; route rejects missing or archived documents | none | `DocumentResponse` or `404`; read-only |
| Download | Admin, Advisor; route checks `READ_DOCUMENT`, then `DownloadDocument.execute` checks it again before lookup | `get` metadata; missing/archived becomes `LookupError` → route `404` | `MinioObjectStorage.presign` uses the stored opaque key to issue a private GET URL expiring in 60 seconds; it does not stream bytes through the API | `DownloadResponse(url=...)`; read-only |
| Archive | `require_document_action(..., Action.ARCHIVE_DOCUMENT)`: Admin | `archive` updates only a currently active row: `archived_at`, `archived_by`, `updated_at`, and `updated_by`, then reads the row | object retained; no MinIO delete | `DocumentResponse`; repeated call is safe because the second `UPDATE ... archived_at IS NULL` changes no row and returns the original archival data |

The public contract in `docs/document-mvp.md` agrees: customers and anonymous callers cannot use these operations; archived rows disappear from normal reads and cannot be downloaded, but the raw private object remains for a future retention policy.

## 4. Migration and test mapping

Migration `migrations/document/versions/4d0cument0001_create_document_schema.py` has revision `4d0cument0001`, no predecessor, and creates the Document-owned `documents` table. It creates:

- Primary key: UUID `id`.
- Required metadata/audit fields: non-null `title`, `content_hash`, status fields, `created_by`, `created_at`, and `updated_at`; optional document descriptors, object metadata, and archival fields.
- Constraints: `ck_documents_title_present` (`length(title) > 0`); `ck_documents_byte_size_non_negative`; fixed MVP approval status (`draft`); and the enumerated processing-status values.
- Indexes: partial active-row index `ix_documents_active` on `archived_at WHERE archived_at IS NULL`, and `ix_documents_created_desc` on `(created_at, id)` for the list ordering.

Its downgrade removes the two indexes and then the `documents` table. It does not touch unrelated tables.

| Test / assertion mapping | What it proves |
| --- | --- |
| `test_migrations.py::test_history_has_one_head` | Alembic reports exactly one Document migration head. |
| `test_migrations.py::test_upgrade_downgrade_and_reupgrade_preserve_legacy_tables` | The upgrade/downgrade/re-upgrade succeeds and an unrelated `document_legacy_probe` table and its row survive. |
| `test_migrations.py::test_schema_defines_required_indexes_and_columns` | Required indexes and key columns are introspected from PostgreSQL after upgrade. |
| `test_repositories.py::test_round_trips_mvp_metadata_when_committed` | A committed transaction can write and faithfully reconstruct metadata. |
| `test_repositories.py::test_rolls_back_write_when_transaction_exits_with_exception` | Raising within `uow.transaction()` leaves no row, demonstrating PostgreSQL metadata rollback. |
| `test_repositories.py::test_lists_active_documents_newest_then_id_and_excludes_archived` | List filters archived rows and follows the specified stable order. |
| `test_repositories.py::test_archive_is_idempotent_when_repeated` | A second archive preserves the first archive actor/time, matching the `archived_at IS NULL` update predicate. |
| `test_repositories.py::test_allows_duplicate_content_hashes_when_committed` | The schema intentionally has no uniqueness invariant on content hashes (no object deduplication in MVP). |

The two prescribed modules contain no HTTP authorization assertion. Authorization evidence is instead in the route/action source and `docs/document-mvp.md`; the broader integration file `tests/document/integration/test_full_flow.py` additionally demonstrates Advisor list/detail/download access after an Admin upload. Its execution is not part of the prescribed command below.

## 5. Checkpoint evidence

Why MinIO for raw files and PostgreSQL for metadata: raw PDFs/DOCX/text are binary objects addressed by a server-controlled opaque key and are served through a short-lived private presigned URL; relational queries instead need small, indexed rows for active filtering, pagination/order, states, checksums, and audit fields. Storing only metadata in PostgreSQL avoids loading file bytes in `SqlAlchemyDocumentRepository` (its class docstring explicitly says “without byte loading”), while storing only bytes in MinIO avoids treating object storage as a relational query engine.

Why transaction ownership is outside the entity: domain `Document` only validates/builds immutable values and state rules. `DocumentUnitOfWork` is an infrastructure adapter for an application-defined port; it owns the SQLAlchemy session lifecycle and transaction because those are external persistence concerns. The application use case coordinates the separate storage operation and compensation.

### Files read

- Prior roadmap context: `notes/architecture-learning/00-repository-map.md`, `01-http-trace.md`, `02-agent-trace.md`, and `03-llm-config-boundary.md`.
- Required Document data sources: `src/document/domain/entities.py`, `domain/values.py`, `application/ports.py`, `infrastructure/models.py`, and `infrastructure/repositories.py`.
- Flow and boundary sources: `src/document/application/contracts.py`, `presentation/routes.py`, `presentation/dependencies.py`, `presentation/schemas.py`, `infrastructure/minio_storage.py`, and `infrastructure/object_keys.py`.
- Migration/contract/tests: `migrations/document/versions/4d0cument0001_create_document_schema.py`, `docs/document-mvp.md`, `tests/document/integration/test_migrations.py`, `test_repositories.py`, and (authorization/compensation context) `test_full_flow.py`.

### Commands and outcomes

```bash
uv run pytest tests/document/integration/test_migrations.py tests/document/integration/test_repositories.py -v --tb=short
```

Outcome: exit status `127` before pytest collection: `/bin/bash: line 1: uv: command not found`. No tests ran. The assertion mapping above was inspected directly from the two prescribed test files.

## Uncertainties and limits

- No runtime test result is available because `uv` is absent from `PATH`; PostgreSQL/MinIO behavior is documented from source/tests, not observed in this run.
- The required test command does not include HTTP authorization or the real-service compensation test, so those claims are source-level/test-code evidence rather than executed evidence.
- Compensation is best effort: if MinIO cleanup is unavailable after a database failure, the original persistence failure remains the outcome and an orphan object may need operational cleanup.
- The archive repository assumes its caller uses an existing document ID; the named repository test covers idempotency for an existing row, not the missing-ID HTTP mapping.
