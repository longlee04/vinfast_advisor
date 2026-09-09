"""Scoped policy search against disposable PostgreSQL."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.agents.adapters.policy_search import SqlAlchemyPolicySearchAdapter

VEHICLE_ID = "00000000-0000-0000-0000-000000009001"
DOCUMENT_ID = "00000000-0000-0000-0000-000000009002"
NOTIFICATION_ID = "00000000-0000-0000-0000-000000009003"
OLD_SCOPE_ID = "00000000-0000-0000-0000-000000009004"
NEW_SCOPE_ID = "00000000-0000-0000-0000-000000009005"


class UnavailableEmbedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("offline integration test")


@pytest.mark.asyncio
async def test_search_selects_old_new_cohort_and_fails_closed_on_boundary(
    document_engine: AsyncEngine,
) -> None:
    now = datetime(2026, 8, 31, tzinfo=UTC)
    async with document_engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO vehicles (
                    vehicle_id, vehicle_type, brand, model_name, status, slug, created_at, updated_at
                ) VALUES (:vehicle_id, 'ELECTRIC_MOTORBIKE', 'VinFast', 'Feliz S', 'ACTIVE',
                          'feliz-s-policy-test', :now, :now)
                ON CONFLICT (vehicle_id) DO NOTHING
                """
            ),
            {"vehicle_id": VEHICLE_ID, "now": now},
        )
        await connection.execute(
            text(
                """
                INSERT INTO documents (
                    id, title, source_url, source_authority, source_revision, content_hash,
                    approval_status, processing_status, created_by, created_at, updated_at
                ) VALUES (
                    :document_id, 'Sổ bảo hành LFP', 'https://vinfastauto.com/warranty',
                    'OFFICIAL', 'reviewed', :content_hash, 'draft', 'completed', 'admin-1', :now, :now
                )
                """
            ),
            {"document_id": DOCUMENT_ID, "content_hash": "9" * 64, "now": now},
        )
        await connection.execute(
            text(
                """
                INSERT INTO policy_notifications (
                    id, source_document_id, policy_type, topic, secondary_topics, affected_models,
                    facts, evidence, ai_confidence, title, content, status, created_by,
                    published_by, created_at, updated_at, published_at
                ) VALUES (
                    :notification_id, :document_id, 'warranty_policy', 'battery_warranty', '[]',
                    '["Feliz S"]', '[]', '[]', 1, 'Đã duyệt', 'Đã duyệt', 'published',
                    'admin-1', 'admin-1', :now, :now, :now
                )
                """
            ),
            {"notification_id": NOTIFICATION_ID, "document_id": DOCUMENT_ID, "now": now},
        )
        for scope_id, start, end, current in (
            (OLD_SCOPE_ID, None, date(2025, 8, 14), False),
            (NEW_SCOPE_ID, date(2025, 8, 16), None, True),
        ):
            await connection.execute(
                text(
                    """
                    INSERT INTO policy_scopes (
                        scope_id, notification_id, source_document_id, policy_type, topic,
                        vehicle_type, component, battery_chemistry, usage_type,
                        eligibility_basis, eligibility_from, eligibility_to, is_current_default,
                        status, affected_models, resolved_vehicle_ids, evidence_quotes,
                        created_by, approved_by, created_at, updated_at, approved_at
                    ) VALUES (
                        :scope_id, :notification_id, :document_id, 'warranty_policy',
                        'battery_warranty', 'MOTORBIKE', 'LFP_BATTERY', 'LFP', 'ANY',
                        'INVOICE_DATE', :start, :end, :current, 'ACTIVE', '["Feliz S"]',
                        :resolved, '["literal"]', 'admin-1', 'admin-1', :now, :now, :now
                    )
                    """
                ),
                {
                    "scope_id": scope_id,
                    "notification_id": NOTIFICATION_ID,
                    "document_id": DOCUMENT_ID,
                    "start": start,
                    "end": end,
                    "current": current,
                    "resolved": f'["{VEHICLE_ID}"]',
                    "now": now,
                },
            )
        for chunk_id, scope_id, content in (
            ("00000000-0000-0000-0000-000000009006", OLD_SCOPE_ID, "Pin LFP bảo hành 5 năm."),
            ("00000000-0000-0000-0000-000000009007", NEW_SCOPE_ID, "Pin LFP bảo hành 8 năm."),
        ):
            await connection.execute(
                text(
                    """
                    INSERT INTO vehicle_documents (
                        document_id, vehicle_id, policy_scope_id, source_document_id,
                        source_content_hash, source_revision, document_type, title, content,
                        chunk_index, source_url, status, created_by, approved_by,
                        approved_at, created_at, updated_at
                    ) VALUES (
                        :chunk_id, :vehicle_id, :scope_id, :document_id, :content_hash,
                        'reviewed', 'WARRANTY_POLICY', 'Sổ bảo hành LFP', :content, 0,
                        'https://vinfastauto.com/warranty', 'ACTIVE', 'admin-1', 'admin-1',
                        :now, :now, :now
                    )
                    """
                ),
                {
                    "chunk_id": chunk_id,
                    "vehicle_id": VEHICLE_ID,
                    "scope_id": scope_id,
                    "document_id": DOCUMENT_ID,
                    "content_hash": "9" * 64,
                    "content": content,
                    "now": now,
                },
            )

    session_factory = async_sessionmaker(document_engine, expire_on_commit=False, class_=AsyncSession)
    search = SqlAlchemyPolicySearchAdapter(session_factory, UnavailableEmbedding())
    old = await search.search(query="pin bảo hành 14/08/2025", vehicle_id=VEHICLE_ID)
    boundary = await search.search(query="pin bảo hành 15/08/2025", vehicle_id=VEHICLE_ID)
    new = await search.search(query="pin bảo hành 16/08/2025", vehicle_id=VEHICLE_ID)
    current = await search.search(query="pin bảo hành hiện nay", vehicle_id=VEHICLE_ID)

    assert [item["chunk_text"] for item in old] == ["Pin LFP bảo hành 5 năm."]
    assert boundary == []
    assert [item["chunk_text"] for item in new] == ["Pin LFP bảo hành 8 năm."]
    assert [item["chunk_text"] for item in current] == ["Pin LFP bảo hành 8 năm."]
