"""Brochure Ingestion Service implementing Gate A10 (A10-1 to A10-4)."""

from __future__ import annotations

import datetime
import hashlib
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.embedding import DeterministicEmbeddingAdapter
from src.agents.adapters.feature_retriever import reverse_write_pending_flag
from src.agents.logging import get_agent_logger, log_file_execution
from src.agents.ports import EmbeddingPort
from src.document.infrastructure.models import DocumentRow, VehicleDocumentRow
from src.document.infrastructure.pdf_extractor import extract_pdf_sections
from src.products.infrastructure.models import FeatureDefinitionRow, VehicleRow

logger = get_agent_logger("document.application.brochure_ingestion")


class BrochureIngestionResult:
    """Result data object returned after ingesting a brochure PDF."""

    def __init__(
        self,
        document_id: str,
        content_hash: str,
        revision: str,
        is_duplicate: bool,
        chunks_created: int,
        feature_proposals_created: int,
    ) -> None:
        self.document_id = document_id
        self.content_hash = content_hash
        self.revision = revision
        self.is_duplicate = is_duplicate
        self.chunks_created = chunks_created
        self.feature_proposals_created = feature_proposals_created


class BrochureIngestionService:
    """Service handling brochure PDF ingestion, deduplication, chunking, embedding, and feature proposal (A10-1 to A10-4)."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_port: EmbeddingPort | None = None,
    ) -> None:
        log_file_execution("src/document/application/brochure_ingestion.py", logger)
        self._session = session
        self._embedding_port = embedding_port or DeterministicEmbeddingAdapter()

    async def ingest_brochure(
        self,
        vehicle_id: str,
        pdf_bytes: bytes,
        filename: str = "brochure.pdf",
        uploaded_by: str = "admin",
    ) -> BrochureIngestionResult:
        """Ingest a brochure PDF for a vehicle.

        1. A10-1: Compute content_hash (SHA-256). Detect duplicates. Determine revision.
        2. A10-2: Extract section-aware text by page, preserving equipment tables.
        3. A10-3: Create vehicle_documents chunks with status='DRAFT' and embeddings.
        4. A10-4: Propose PENDING feature flags using shared reverse_write_pending_flag.
        """
        if not pdf_bytes:
            raise ValueError("Brochure PDF bytes cannot be empty")

        # Check vehicle existence
        v_stmt = select(VehicleRow).where(VehicleRow.vehicle_id == vehicle_id)
        v_res = await self._session.execute(v_stmt)
        vehicle = v_res.scalar_one_or_none()
        if vehicle is None:
            raise ValueError(f"Vehicle {vehicle_id} not found")

        # 1. A10-1 Deduplication: Calculate SHA-256 content_hash
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()

        # Check existing document with same content_hash
        doc_stmt = select(DocumentRow).where(DocumentRow.content_hash == content_hash)
        doc_res = await self._session.execute(doc_stmt)
        existing_doc = doc_res.scalar_one_or_none()

        now_utc = datetime.datetime.now(datetime.UTC)

        if existing_doc is not None:
            logger.info("Duplicate brochure PDF detected for content_hash=%s", content_hash)
            # Find existing revision for this vehicle & document
            rev_stmt = select(func.max(VehicleDocumentRow.source_revision)).where(
                VehicleDocumentRow.vehicle_id == vehicle_id,
                VehicleDocumentRow.source_document_id == existing_doc.id,
            )
            rev_res = await self._session.execute(rev_stmt)
            existing_rev = rev_res.scalar() or "1"
            return BrochureIngestionResult(
                document_id=existing_doc.id,
                content_hash=content_hash,
                revision=existing_rev,
                is_duplicate=True,
                chunks_created=0,
                feature_proposals_created=0,
            )

        # Determine revision for new brochure PDF of this vehicle
        max_rev_stmt = select(func.max(VehicleDocumentRow.source_revision)).where(
            VehicleDocumentRow.vehicle_id == vehicle_id
        )
        max_rev_res = await self._session.execute(max_rev_stmt)
        max_rev_val = max_rev_res.scalar()
        if max_rev_val and max_rev_val.isdigit():
            revision = str(int(max_rev_val) + 1)
        else:
            revision = "1"

        # Create original document record in documents table
        doc_id = str(uuid4())
        new_doc = DocumentRow(
            id=doc_id,
            title=f"Brochure {vehicle.model_name or filename}",
            description=f"Brochure PDF for vehicle {vehicle_id}",
            document_type="BROCHURE",
            original_filename=filename,
            byte_size=len(pdf_bytes),
            content_hash=content_hash,
            approval_status="draft",
            processing_status="completed",
            created_by=uploaded_by,
            created_at=now_utc,
            updated_at=now_utc,
        )
        self._session.add(new_doc)
        await self._session.flush()

        # 2. A10-2 Text Extraction
        sections = extract_pdf_sections(pdf_bytes, filename=filename)

        # 3. A10-3 Chunking & Embedding
        chunk_texts = [content for _, _, content in sections]
        embeddings = await self._embedding_port.embed(chunk_texts)

        chunks_created = 0
        created_chunks: list[VehicleDocumentRow] = []

        for idx, ((page_num, section_title, content), emb) in enumerate(zip(sections, embeddings, strict=True)):
            chunk_doc_id = str(uuid4())
            # Truncate vector to 1024 dimension to fit VehicleDocumentRow schema
            emb_1024 = emb[:1024] if len(emb) >= 1024 else emb + [0.0] * (1024 - len(emb))

            v_doc = VehicleDocumentRow(
                document_id=chunk_doc_id,
                vehicle_id=vehicle_id,
                source_document_id=doc_id,
                source_content_hash=content_hash,
                source_revision=revision,
                document_type="BROCHURE",
                title=f"{filename} - p.{page_num} {section_title}",
                content=content,
                chunk_index=idx,
                section_title=section_title,
                page_number=page_num,
                embedding_model="text-embedding-3-small",
                embedding_version="v1",
                embedding=emb_1024,
                status="DRAFT",  # Initial status is DRAFT (not auto-ACTIVE)
                created_by=uploaded_by,
                created_at=now_utc,
                updated_at=now_utc,
            )
            self._session.add(v_doc)
            created_chunks.append(v_doc)
            chunks_created += 1

        await self._session.flush()
        logger.info("Created %d DRAFT chunks for brochure doc_id=%s, vehicle=%s", chunks_created, doc_id, vehicle_id)

        # 4. A10-4 Feature Flag Proposals using shared reverse_write_pending_flag
        proposals_created = await self._propose_feature_flags(vehicle_id, vehicle.vehicle_type, chunk_texts)

        return BrochureIngestionResult(
            document_id=doc_id,
            content_hash=content_hash,
            revision=revision,
            is_duplicate=False,
            chunks_created=chunks_created,
            feature_proposals_created=proposals_created,
        )

    async def _propose_feature_flags(
        self,
        vehicle_id: str,
        vehicle_type: str,
        chunk_texts: Sequence[str],
    ) -> int:
        """A10-4: Propose PENDING feature flags by matching active feature definitions against brochure text."""
        f_stmt = select(FeatureDefinitionRow).where(
            FeatureDefinitionRow.status == "ACTIVE",
            FeatureDefinitionRow.vehicle_type == vehicle_type,
        )
        f_res = await self._session.execute(f_stmt)
        features = f_res.scalars().all()

        combined_text = " ".join(chunk_texts).lower()
        proposals_count = 0

        for fdef in features:
            f_code = fdef.feature_code
            name_kw = fdef.name.lower()
            desc_kw = (fdef.description or "").lower()

            # Check keyword match in brochure text
            is_mentioned = (name_kw in combined_text) or (desc_kw and desc_kw in combined_text)
            if not is_mentioned:
                # Synonym expansions check
                synonyms = {
                    "PANORAMIC_ROOF": [
                        "cửa sổ trời",
                        "kính toàn cảnh",
                        "nóc kính",
                        "cua so troi",
                        "kinh toan canh",
                        "noc kinh",
                        "panoramic roof",
                        "sunroof",
                    ],
                    "URBAN_TRAFFIC": [
                        "đi trong phố",
                        "đường đông",
                        "di trong pho",
                        "duong dong",
                    ],
                }
                if f_code in synonyms:
                    is_mentioned = any(kw in combined_text for kw in synonyms[f_code])

            if is_mentioned:
                # Call shared write function to propose PENDING flag
                await reverse_write_pending_flag(
                    session=self._session,
                    vehicle_id=vehicle_id,
                    feature_code=f_code,
                    status="YES",
                    confidence=0.85,
                )
                proposals_count += 1

        logger.info("Proposed %d PENDING feature flags for vehicle=%s", proposals_count, vehicle_id)
        return proposals_count
