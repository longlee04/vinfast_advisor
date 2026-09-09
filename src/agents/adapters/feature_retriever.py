"""FeatureRetrievalAdapter — Layer 2 Need & Feature Retriever implementation (mục 7.2 schema, A1-3/6/7)."""

from __future__ import annotations

import datetime
import math
import unicodedata
from collections import defaultdict
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.embedding import DeterministicEmbeddingAdapter
from src.agents.contracts import FeatureAssertion
from src.agents.domain.need_tags import NEED_TAG_REGISTRY
from src.agents.domain.values import VehicleType
from src.agents.logging import get_agent_logger, log_file_execution
from src.agents.ports import EmbeddingPort
from src.document.infrastructure.models import VehicleDocumentRow
from src.products.infrastructure.models import (
    FeatureDefinitionRow,
    FeatureNeedTagRow,
    VehicleFeatureFlagRow,
)

logger = get_agent_logger("agent.adapters.feature_retriever")

DEFAULT_SIMILARITY_THRESHOLD = 0.45
RRF_K_CONSTANT = 60
PLACEHOLDER_FEATURE_CODE = "UNKNOWN_FEATURE"
# Chunk brochure sau khi lọc dài trung bình hơn 400 ký tự, nên ngưỡng cũ cắt cụt
# gần như mọi trích dẫn giữa câu.
MAX_EXCERPT_CHARS = 700
# Chọn tài liệu theo cặp (xe, tính năng) nên mỗi xe cần nhiều ứng viên hơn một.
DOCUMENT_FETCH_LIMIT = 60


def _excerpt(content: str) -> str | None:
    """Cắt đoạn trích đủ ngắn để chèn vào câu trả lời, cắt ở ranh giới từ."""

    text_value = " ".join(content.split())
    if not text_value:
        return None
    if len(text_value) <= MAX_EXCERPT_CHARS:
        return text_value
    cut = text_value[:MAX_EXCERPT_CHARS].rsplit(" ", 1)[0]
    return cut or text_value[:MAX_EXCERPT_CHARS]


def _fold(text_value: str) -> str:
    """Bỏ dấu tiếng Việt và hạ chữ thường để so khớp không phụ thuộc cách gõ dấu."""

    decomposed = unicodedata.normalize("NFD", text_value.lower())
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return stripped.replace("đ", "d")


def _document_supports_feature(content: str, feature_code: str, feature_name: str | None) -> bool:
    """Đoạn tài liệu có thật sự nói về tính năng này không.

    Placeholder không gắn với tính năng nào nên không bao giờ kết luận được — câu
    hỏi mô tả chỉ cần đoạn trích, không cần khẳng định YES/NO.
    """

    if feature_code == PLACEHOLDER_FEATURE_CODE or not content:
        return False

    folded = _fold(content)
    code_tokens = [token for token in _fold(feature_code).split("_") if len(token) >= 4]
    if any(token in folded for token in code_tokens):
        return True

    if not feature_name:
        return False
    name_tokens = [token for token in _fold(feature_name).split() if len(token) >= 3]
    return bool(name_tokens) and all(token in folded for token in name_tokens)


def documents_needed(assertions: Sequence[FeatureAssertion]) -> list[FeatureAssertion]:
    """Chọn assertion nào cần đọc tài liệu (nhánh 2e)."""
    return [assertion for assertion in assertions if assertion.status == "UNKNOWN"]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two float vectors safely, with query-side coverage scaling."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    cos_sim = dot / (norm_a * norm_b)
    query_coverage = dot / norm_a
    return max(cos_sim, query_coverage * 0.70)


async def reverse_write_pending_flag(
    session: AsyncSession,
    vehicle_id: str,
    feature_code: str,
    status: str,
    confidence: float,
) -> None:
    """A1-6 & A10-4 shared write function: Upsert feature evidence to vehicle_feature_flags with verification_status = PENDING.

    Guarantees:
    - Never overwrites APPROVED or REJECTED flags.
    - Idempotent updates for PENDING or missing flags.
    """
    check_stmt = select(VehicleFeatureFlagRow).where(
        VehicleFeatureFlagRow.vehicle_id == vehicle_id,
        VehicleFeatureFlagRow.feature_code == feature_code,
    )
    res = await session.execute(check_stmt)
    existing = res.scalar_one_or_none()

    now_utc = datetime.datetime.now(datetime.UTC)

    if existing is None:
        new_flag = VehicleFeatureFlagRow(
            vehicle_id=vehicle_id,
            feature_code=feature_code,
            status=status,
            verification_status="PENDING",
            confidence=confidence,
            created_at=now_utc,
            updated_at=now_utc,
        )
        session.add(new_flag)
        await session.flush()
        logger.info(
            "Shared Reverse Write: Created PENDING feature flag for vehicle=%s, feature=%s", vehicle_id, feature_code
        )
    elif existing.verification_status not in ("APPROVED", "REJECTED"):
        existing.status = status
        existing.verification_status = "PENDING"
        existing.confidence = confidence
        existing.updated_at = now_utc
        await session.flush()
        logger.info(
            "Shared Reverse Write: Updated PENDING feature flag for vehicle=%s, feature=%s", vehicle_id, feature_code
        )


class InMemoVocabularyCache:
    """In-memory vocabulary & vector embeddings cache for 2a (features) and 2b (need tags)."""

    def __init__(self) -> None:
        self.feature_entries: list[tuple[str, str, list[float]]] = []  # (feature_code, text, embedding)
        self.need_entries: list[tuple[str, list[str], list[float]]] = []  # (need_tag, default_feature_codes, embedding)
        self.is_loaded: bool = False

    async def load(self, session: AsyncSession, embedding_port: EmbeddingPort) -> None:
        """Load feature definitions & closed set need tags, and compute vector embeddings in a single batched call."""
        self.feature_entries.clear()
        self.need_entries.clear()

        # 1. Load feature definitions (2a)
        f_stmt = select(
            FeatureDefinitionRow.feature_code,
            FeatureDefinitionRow.name,
            FeatureDefinitionRow.description,
        )
        f_result = await session.execute(f_stmt)
        f_rows = f_result.all()

        feature_texts = []
        feature_codes = []

        synonym_expansions = {
            "PANORAMIC_ROOF": "cửa sổ trời cửa sổ trời toàn cảnh kính toàn cảnh nóc kính trần kính",
            "URBAN_TRAFFIC": "hay đi trong phố đi lại nội thành đường đông đúc nhỏ hẹp dễ xoay xở",
        }

        for f_code, name, desc in f_rows:
            combined_desc = f"{name} {desc or ''} {synonym_expansions.get(f_code, '')}".strip().lower()
            feature_texts.append(combined_desc)
            feature_codes.append(f_code)

        # 2. Load need tags from closed set domain registry and DB (2b)
        n_stmt = select(FeatureNeedTagRow.need_tag, FeatureNeedTagRow.feature_code)
        n_result = await session.execute(n_stmt)
        db_need_mappings = defaultdict(list)
        for need_tag_str, f_code in n_result.all():
            db_need_mappings[need_tag_str.upper()].append(f_code)

        need_texts = []
        need_keys = []
        need_feat_codes = []

        for need_enum, need_def in NEED_TAG_REGISTRY.items():
            tag_str = need_enum.value
            fcodes = list(set(list(need_def.default_feature_codes) + db_need_mappings.get(tag_str, [])))
            combined_need_text = f"{need_def.name_vi} {need_def.description_vi}".strip().lower()
            need_texts.append(combined_need_text)
            need_keys.append(tag_str)
            need_feat_codes.append(fcodes)

        # Efficient single batched embedding call for features and need tags
        all_texts = feature_texts + need_texts
        if all_texts:
            all_embeddings = await embedding_port.embed(all_texts)
            f_embeddings = all_embeddings[: len(feature_texts)]
            n_embeddings = all_embeddings[len(feature_texts) :]

            for f_code, text_val, emb in zip(feature_codes, feature_texts, f_embeddings, strict=True):
                self.feature_entries.append((f_code, text_val, emb))

            for tag_str, fcodes, emb in zip(need_keys, need_feat_codes, n_embeddings, strict=True):
                self.need_entries.append((tag_str, fcodes, emb))

        self.is_loaded = True
        logger.info(
            "In-memory vocabulary vector cache loaded in 1 batched call: %d features, %d need tags",
            len(self.feature_entries),
            len(self.need_entries),
        )

    def invalidate(self) -> None:
        """Invalidate the cache so it will be rebuilt on next load."""
        self.feature_entries.clear()
        self.need_entries.clear()
        self.is_loaded = False


# Shared cache instance
_vocab_cache = InMemoVocabularyCache()


class FeatureRetrievalAdapter:
    """Adapter executing 5 branches of Layer 2 retrieval (2a - 2e) using Vector Similarity & Hybrid RAG."""

    def __init__(
        self,
        session: AsyncSession,
        embedding_port: EmbeddingPort | None = None,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        log_file_execution("src/agents/adapters/feature_retriever.py", logger)
        self._session = session
        self._embedding_port = embedding_port or DeterministicEmbeddingAdapter()
        self._threshold = threshold

    async def resolve(
        self,
        utterance: str,
        vehicle_type: VehicleType | str,
        candidate_ids: Sequence[UUID],
    ) -> list[FeatureAssertion]:
        """Resolve customer utterance into feature assertions using Vector Matching (2a/2b) & Hybrid RAG (2e)."""
        if not candidate_ids:
            return []

        # Ensure vocabulary cache is loaded
        if not _vocab_cache.is_loaded:
            await _vocab_cache.load(self._session, self._embedding_port)

        utterance_clean = utterance.strip().lower()
        if not utterance_clean:
            return []

        # A1-7: Single embedding pass for customer utterance
        utterance_embeddings = await self._embedding_port.embed([utterance_clean])
        utterance_vec = utterance_embeddings[0] if utterance_embeddings else []

        matched_feature_codes: set[str] = set()

        # 2a Vector similarity match: Customer phrase -> feature_code
        matched_code, f_score = self._match_feature_vector(utterance_vec)
        if matched_code and f_score >= self._threshold:
            matched_feature_codes.add(matched_code)
            logger.info("2a vector matched phrase '%s' -> %s (score %.3f)", utterance, matched_code, f_score)

        # 2b Vector similarity match: Customer habit/need -> need_tag -> feature_codes
        matched_need_tag, matched_need_fcodes, n_score = self._match_need_vector(utterance_vec)
        if matched_need_tag and n_score >= self._threshold:
            for fc in matched_need_fcodes:
                matched_feature_codes.add(fc)
            logger.info(
                "2b vector matched need '%s' -> %s -> %s (score %.3f)",
                utterance,
                matched_need_tag,
                matched_need_fcodes,
                n_score,
            )

        assertions: list[FeatureAssertion] = []
        str_ids = [str(cid) for cid in candidate_ids]

        if matched_feature_codes:
            # 2c: Query vehicle_feature_flags for matched feature codes
            flag_stmt = select(VehicleFeatureFlagRow).where(
                VehicleFeatureFlagRow.vehicle_id.in_(str_ids),
                VehicleFeatureFlagRow.feature_code.in_(list(matched_feature_codes)),
                VehicleFeatureFlagRow.verification_status == "APPROVED",
            )
            flag_result = await self._session.execute(flag_stmt)
            flag_rows = flag_result.scalars().all()

            found_keys: set[tuple[UUID, str]] = set()
            for row in flag_rows:
                v_uuid = UUID(row.vehicle_id)
                status_val = row.status if row.status in ("YES", "NO") else "UNKNOWN"
                assertions.append(
                    FeatureAssertion(
                        vehicle_id=v_uuid,
                        feature_code=row.feature_code,
                        status=status_val,
                        source="FLAG",
                        evidence_ref=f"vehicle_feature_flags:{row.vehicle_id}:{row.feature_code}",
                        confidence=float(row.confidence) if row.confidence is not None else 1.0,
                    )
                )
                found_keys.add((v_uuid, row.feature_code))

            # Missing candidates/features default to UNKNOWN
            for cid in candidate_ids:
                for fcode in matched_feature_codes:
                    if (cid, fcode) not in found_keys:
                        assertions.append(
                            FeatureAssertion(
                                vehicle_id=cid,
                                feature_code=fcode,
                                status="UNKNOWN",
                                source="FLAG",
                                evidence_ref="flag_not_found",
                                confidence=None,
                            )
                        )
        else:
            # If similarity is below threshold, return UNKNOWN (no guessing)
            for cid in candidate_ids:
                assertions.append(
                    FeatureAssertion(
                        vehicle_id=cid,
                        feature_code=PLACEHOLDER_FEATURE_CODE,
                        status="UNKNOWN",
                        source="FLAG",
                        evidence_ref="below_similarity_threshold",
                        confidence=None,
                    )
                )

        # 2e: Hybrid RAG Document Retrieval.
        #
        # Chạy cho cả hai mục đích, không chỉ khi flag bó tay:
        #   - assertion UNKNOWN: tài liệu để kết luận tính năng;
        #   - mọi ứng viên: một đoạn mô tả theo đúng câu khách hỏi, để phần diễn
        #     giải luôn có dẫn chứng. Nếu chỉ chạy khi UNKNOWN thì càng duyệt
        #     nhiều flag, RAG càng biến mất — dữ liệu tốt lên lại làm mất tiếng nói.
        targets = list(documents_needed(assertions))
        described = {a.vehicle_id for a in targets if a.feature_code == PLACEHOLDER_FEATURE_CODE}
        targets.extend(
            FeatureAssertion(
                vehicle_id=cid,
                feature_code=PLACEHOLDER_FEATURE_CODE,
                status="UNKNOWN",
                source="FLAG",
                evidence_ref="descriptive_lookup",
                confidence=None,
            )
            for cid in candidate_ids
            if cid not in described
        )

        if targets:
            doc_assertions = await self._retrieve_documents_hybrid(utterance_clean, utterance_vec, str_ids, targets)
            doc_map = {(d.vehicle_id, d.feature_code): d for d in doc_assertions}
            merged = [doc_map.pop((a.vehicle_id, a.feature_code), a) for a in assertions]
            # Đoạn mô tả của xe chưa có assertion nào tương ứng vẫn phải đi tiếp,
            # nếu không thì công truy hồi bị vứt đi ngay tại đây.
            merged.extend(doc_map.values())
            assertions = merged

        return assertions

    def _match_feature_vector(self, utterance_vec: list[float]) -> tuple[str | None, float]:
        """Find best matching feature code using pure vector cosine similarity."""
        best_code: str | None = None
        best_score: float = 0.0

        for f_code, _text_val, f_vec in _vocab_cache.feature_entries:
            sim = cosine_similarity(utterance_vec, f_vec)
            if sim > best_score:
                best_score = sim
                best_code = f_code

        return best_code, best_score

    def _match_need_vector(self, utterance_vec: list[float]) -> tuple[str | None, list[str], float]:
        """Find best matching need tag using pure vector cosine similarity."""
        best_tag: str | None = None
        best_fcodes: list[str] = []
        best_score: float = 0.0

        for tag_str, fcodes, n_vec in _vocab_cache.need_entries:
            sim = cosine_similarity(utterance_vec, n_vec)
            if sim > best_score:
                best_score = sim
                best_tag = tag_str
                best_fcodes = fcodes

        return best_tag, best_fcodes, best_score

    async def _retrieve_documents_hybrid(
        self,
        query_text: str,
        query_vec: list[float],
        candidate_ids: list[str],
        target_assertions: list[FeatureAssertion],
    ) -> list[FeatureAssertion]:
        """A1-6 (2e): Hybrid Document Retrieval (PostgreSQL FTS + pgvector Dense Search + RRF k=60)."""
        logger.info("Executing 2e Hybrid RAG Document Retrieval for candidates=%s", candidate_ids)
        doc_assertions: list[FeatureAssertion] = []

        # 1. Full-Text Search (FTS) Rank
        fts_stmt = (
            select(
                VehicleDocumentRow.document_id,
                VehicleDocumentRow.vehicle_id,
                VehicleDocumentRow.content,
            )
            .where(
                VehicleDocumentRow.vehicle_id.in_(candidate_ids),
                VehicleDocumentRow.status == "ACTIVE",
                text("content_tsv @@ plainto_tsquery('simple', :query)").params(query=query_text),
            )
            .limit(DOCUMENT_FETCH_LIMIT)
        )
        fts_result = await self._session.execute(fts_stmt)
        fts_rows = fts_result.all()
        fts_ranks: dict[str, tuple[int, str]] = {}  # doc_id -> (rank, vehicle_id)
        doc_content: dict[str, str] = {}
        for idx, (doc_id, v_id, content) in enumerate(fts_rows, start=1):
            fts_ranks[doc_id] = (idx, v_id)
            doc_content[doc_id] = content

        # 2. Dense Vector Search Rank (pgvector cosine distance or vector match)
        dense_stmt = select(
            VehicleDocumentRow.document_id,
            VehicleDocumentRow.vehicle_id,
            VehicleDocumentRow.content,
        ).where(
            VehicleDocumentRow.vehicle_id.in_(candidate_ids),
            VehicleDocumentRow.status == "ACTIVE",
        )
        try:
            dense_stmt = dense_stmt.order_by(VehicleDocumentRow.embedding.cosine_distance(query_vec)).limit(
                DOCUMENT_FETCH_LIMIT
            )
        except Exception:
            dense_stmt = dense_stmt.limit(DOCUMENT_FETCH_LIMIT)

        dense_result = await self._session.execute(dense_stmt)
        dense_rows = dense_result.all()
        dense_ranks: dict[str, tuple[int, str]] = {}
        for idx, (doc_id, v_id, content) in enumerate(dense_rows, start=1):
            dense_ranks[doc_id] = (idx, v_id)
            doc_content[doc_id] = content

        # 3. Reciprocal Rank Fusion (RRF) with k = 60
        all_doc_ids = set(fts_ranks.keys()).union(set(dense_ranks.keys()))
        rrf_scores: dict[str, float] = {}
        doc_vehicle_map: dict[str, str] = {}

        for doc_id in all_doc_ids:
            score = 0.0
            v_id = None
            if doc_id in fts_ranks:
                rank_fts, v_id = fts_ranks[doc_id]
                score += 1.0 / (RRF_K_CONSTANT + rank_fts)
            if doc_id in dense_ranks:
                rank_dense, v_id = dense_ranks[doc_id]
                score += 1.0 / (RRF_K_CONSTANT + rank_dense)

            rrf_scores[doc_id] = score
            if v_id:
                doc_vehicle_map[doc_id] = v_id

        if not rrf_scores:
            return []

        # Xếp tài liệu của TỪNG XE theo RRF. Lấy top-1 toàn cục thì khách hỏi so
        # sánh 3 xe chỉ có một xe được đọc tài liệu, hai xe kia im lặng dù corpus
        # có đủ nội dung.
        ranked_per_vehicle: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for doc_id, score in sorted(rrf_scores.items(), key=lambda item: item[1], reverse=True):
            vehicle_key = doc_vehicle_map.get(doc_id)
            if vehicle_key:
                ranked_per_vehicle[vehicle_key].append((doc_id, score))

        logger.info("RRF k=60 hybrid search: %d xe co tai lieu khop", len(ranked_per_vehicle))

        feature_names = await self._feature_names({target.feature_code for target in target_assertions})

        for target in target_assertions:
            v_id_str = str(target.vehicle_id)
            ranked = ranked_per_vehicle.get(v_id_str)
            if not ranked:
                continue

            # Chọn theo cặp (xe, tính năng): đoạn xếp hạng cao nhất mà thật sự nói
            # về tính năng đang xét. Không có đoạn nào nói tới thì lùi về đoạn khớp
            # truy vấn nhất của xe đó và để trạng thái UNKNOWN — vẫn có dẫn chứng
            # để diễn giải, nhưng không khẳng định điều tài liệu không nói.
            #
            # Trúng truy vấn ngữ nghĩa KHÔNG đồng nghĩa xe có tính năng đó: một đoạn
            # tả ghế ngồi vẫn có thể là kết quả gần nhất cho câu hỏi về eSIM.
            feature_name = feature_names.get(target.feature_code)
            doc_id, rrf_score = ranked[0]
            supported = False
            for candidate_doc_id, candidate_score in ranked:
                if _document_supports_feature(doc_content.get(candidate_doc_id, ""), target.feature_code, feature_name):
                    doc_id, rrf_score = candidate_doc_id, candidate_score
                    supported = True
                    break

            content = doc_content.get(doc_id, "")
            confidence = min(1.0, rrf_score * 30.0)
            doc_assertions.append(
                FeatureAssertion(
                    vehicle_id=target.vehicle_id,
                    feature_code=target.feature_code,
                    status="YES" if supported else "UNKNOWN",
                    source="DOCUMENT",
                    evidence_ref=f"vehicle_documents:{doc_id}",
                    confidence=confidence if supported else None,
                    excerpt=_excerpt(content),
                )
            )

            # Placeholder has no feature_definitions row; never reverse-write it.
            if supported and target.feature_code != PLACEHOLDER_FEATURE_CODE:
                await reverse_write_pending_flag(
                    session=self._session,
                    vehicle_id=v_id_str,
                    feature_code=target.feature_code,
                    status="YES",
                    confidence=confidence,
                )

        return doc_assertions

    async def _feature_names(self, feature_codes: set[str]) -> dict[str, str]:
        """Tên hiển thị của feature, dùng để đối chiếu đoạn trích với tính năng."""

        codes = {code for code in feature_codes if code != PLACEHOLDER_FEATURE_CODE}
        if not codes:
            return {}
        rows = (
            await self._session.execute(
                select(FeatureDefinitionRow.feature_code, FeatureDefinitionRow.name).where(
                    FeatureDefinitionRow.feature_code.in_(list(codes))
                )
            )
        ).all()
        return {code: name for code, name in rows if name}
