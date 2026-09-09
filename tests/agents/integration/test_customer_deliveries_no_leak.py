"""T13: customer deliveries (REST + SSE) khong duoc lo ho so noi bo.

`GET /agent/deliveries/{session_id}` va SSE `/agent/events/{session_id}` chi
duoc tra `deliverable_content` (edited_content hoac content) + review_id +
anh so sanh. Test nay seed mot review co `profile_snapshot` day du trong DB
(offer_state, matched_promotions, unmet_demand_flag, unmet_bottleneck,...) roi
assert cac key noi bo khong lot ra tren RAW JSON STRING cua response (khong
chi tren model da parse, vi model co the tinh cach an field ma serializer
van co the leak neu code sau nay vo tinh dua object goc vao response).
"""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import anyio
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.repositories import build_agent_transaction
from src.agents.adapters.unit_of_work import AgentUnitOfWork
from src.agents.api.customer_routes import customer_turn_events
from src.agents.api.dependencies import get_current_customer_id
from src.agents.api.review_routes import review_operations
from src.agents.models import AgentRunRow, ConversationSessionRow, ReviewQueueRow
from src.agents.services.operations.review import ReviewOperations
from src.agents.services.operations.turn_events import InMemoryTurnEventBroker, TurnEvent
from src.api.router import api_router

NOW = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)
CUSTOMER_ID = "customer-1"

# Snapshot noi bo day du - phai co that trong DB de test khong "gia vo pass".
FULL_INTERNAL_SNAPSHOT = {
    "needs": ["gia re", "sac nhanh"],
    "considered_vehicles": ["VF8", "VF9"],
    "bottlenecks": [{"bottleneck": "PRICE", "verbatim_quote": "gia cao qua anh oi"}],
    "matched_promotions": [
        {"promotion_code": "FIN-1", "promotion_type": "FINANCING", "description": "Ho tro lai suat"}
    ],
    "verified_number_tokens": ["1200000000"],
    "offer_state": "BOTTLENECK_NO_OFFER",
    "unmet_demand_flag": True,
    "unmet_bottleneck": "PRICE",
    "color_preference": "trang",
    "adjustment_policies": {"FINANCING": {"financing_months_max": 36}},
}

LEAK_KEYS = [
    "profile_snapshot",
    "offer_state",
    "matched_promotions",
    "adjustment_policies",
    "unmet_demand_flag",
    "unmet_bottleneck",
]


class FrozenClock:
    def now(self) -> datetime:
        return NOW


async def _seed_review(
    engine: AsyncEngine,
    *,
    customer_id: str = CUSTOMER_ID,
    status: str = "APPROVED",
    content: str = "Draft goc chua duyet",
    edited_content: str | None = "VF 8 gia 1.200.000.000 dong, tra gop uu dai.",
    snapshot: dict | None = None,
) -> tuple[UUID, UUID]:
    session_id = uuid4()
    run_id = uuid4()
    review_id = uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            insert(ConversationSessionRow).values(
                session_id=session_id,
                customer_id=customer_id,
                started_at=NOW,
                last_activity_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(AgentRunRow).values(
                run_id=run_id,
                session_id=session_id,
                state="APPROVED",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        await connection.execute(
            insert(ReviewQueueRow).values(
                review_id=review_id,
                session_id=session_id,
                run_id=run_id,
                content=content,
                edited_content=edited_content,
                status=status,
                created_at=NOW,
                updated_at=NOW,
                profile_snapshot=snapshot,
            )
        )
    return session_id, review_id


@pytest.fixture
def app(migrated_engine: AsyncEngine, clean_agent_database: None) -> FastAPI:
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    unit_of_work = AgentUnitOfWork(
        session_factory=session_factory,
        transaction_factory=lambda session: build_agent_transaction(session, clock=FrozenClock()),
    )
    application = FastAPI()
    application.include_router(api_router)
    application.dependency_overrides[get_current_customer_id] = lambda: CUSTOMER_ID
    application.dependency_overrides[review_operations] = lambda: ReviewOperations(unit_of_work)
    return application


@pytest.mark.asyncio
async def test_customer_deliveries_raw_json_does_not_leak_internal_profile_fields(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given: mot review DA DUYET voi profile_snapshot noi bo day du trong DB.
    session_id, review_id = await _seed_review(migrated_engine, status="APPROVED", snapshot=FULL_INTERNAL_SNAPSHOT)

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/deliveries/{session_id}")

    # Then: request thanh cong va noi dung khach nhan dung, nhung snapshot noi bo
    # KHONG lot ra tren RAW JSON STRING (khong chi tren model da parse).
    assert response.status_code == 200
    raw_text = response.text
    for leak_key in LEAK_KEYS:
        assert leak_key not in raw_text, f"leak: '{leak_key}' xuat hien trong response raw JSON"

    body = json.loads(raw_text)
    assert body["items"] == [
        {
            "review_id": str(review_id),
            "content": "VF 8 gia 1.200.000.000 dong, tra gop uu dai.",
            "status": "APPROVED",
            "comparison_image_base64": None,
        }
    ]
    # Chi dung 4 key duoc phep tren moi item - khong co key thua nao khac lot ra.
    # `status` la trang thai duyet (APPROVED/EDITED/EXPIRED), khong phai du lieu
    # noi bo: khach can phan biet noi dung that voi loi xin loi qua han.
    assert set(body["items"][0].keys()) == {
        "review_id",
        "content",
        "status",
        "comparison_image_base64",
    }


@pytest.mark.asyncio
async def test_customer_deliveries_edited_item_with_snapshot_does_not_leak(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    # Given: item EDITED cung mang snapshot day du - duong doc khac (edited_content).
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="EDITED",
        content="Ban nhap goc",
        edited_content="Ban da sua boi tu van vien",
        snapshot=FULL_INTERNAL_SNAPSHOT,
    )

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/deliveries/{session_id}")

    # Then
    assert response.status_code == 200
    raw_text = response.text
    for leak_key in LEAK_KEYS:
        assert leak_key not in raw_text
    assert json.loads(raw_text)["items"][0]["content"] == "Ban da sua boi tu van vien"


@pytest.mark.asyncio
async def test_customer_deliveries_never_returns_a_pending_unapproved_draft(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """T12: mot ban nhap con PENDING (chua tu van vien duyet) khong duoc lot ra
    tren GET /agent/deliveries duoi bat ky hinh thuc nao - khong trong `items`,
    khong trong raw JSON string.
    """
    # Given: mot review con PENDING mang dung noi dung nhu guardrail se giu lai
    # cho tu van vien (`draft_answer`/`advisor_content`) - chua ai duyet.
    draft_content = "BAN NHAP CHUA KIEM CHUNG - tuyet doi khong duoc ra khach"
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="PENDING",
        content=draft_content,
        edited_content=None,
    )

    # When
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/deliveries/{session_id}")

    # Then: request thanh cong nhung khong co gi de tra - muc PENDING bi loc bo
    # hoan toan, va noi dung ban nhap khong xuat hien tren raw JSON string.
    assert response.status_code == 200
    raw_text = response.text
    assert draft_content not in raw_text
    assert str(review_id) not in raw_text
    body = json.loads(raw_text)
    assert body["items"] == []


@pytest.mark.asyncio
async def test_customer_deliveries_scrub_markers_but_keep_advisor_draft_raw(
    app: FastAPI, migrated_engine: AsyncEngine, clean_agent_database: None
) -> None:
    """[Todo 9] Nội dung khách nhận sạch marker nội bộ; bản nháp tư vấn viên giữ nguyên.

    REST delivery scrub `[evidence_id:...]`/`[source_record:...]` + bare UUID
    (qua `customer_safe_answer` ở biên delivery), nhưng hàng `ReviewQueueRow`
    (advisor draft) vẫn chứa bản gốc có marker — mapper không đụng draft.
    """

    raw_uuid = "550e8400-e29b-41d4-a716-446655440000"
    draft = f"VF 8 giá 1090000000 đồng [evidence_id:{raw_uuid}] [source_record:cars:row]."
    session_id, review_id = await _seed_review(
        migrated_engine,
        status="APPROVED",
        content=draft,
        edited_content=None,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://agent-test") as client:
        response = await client.get(f"/api/v1/agent/deliveries/{session_id}")

    assert response.status_code == 200
    raw_text = response.text
    assert raw_uuid not in raw_text
    assert "evidence_id" not in raw_text
    assert "source_record" not in raw_text
    body = json.loads(raw_text)
    assert body["items"][0]["content"] == "VF 8 giá 1090000000 đồng."

    async with migrated_engine.connect() as connection:
        stored = await connection.scalar(select(ReviewQueueRow.content).where(ReviewQueueRow.review_id == review_id))
    assert stored == draft


@pytest.mark.asyncio
async def test_customer_turn_events_sse_raw_payload_does_not_leak_internal_profile_fields() -> None:
    # Given: review that trong DB mang profile_snapshot day du (goi qua broker
    # thuan, nhung xac nhan schema TurnEvent/SSE khong co truong nao dinh
    # chuyen tai du lieu snapshot noi bo - regression guard).
    session_id = uuid4()
    review_id = uuid4()
    broker = InMemoryTurnEventBroker()

    class FakeCustomerOperations:
        async def authorize_customer_session(self, sid: UUID, customer_id: str) -> None:
            return None

    response = await customer_turn_events(
        session_id=session_id,
        customer_id=CUSTOMER_ID,
        operations=FakeCustomerOperations(),
        broker=broker,
    )

    async def publish() -> None:
        await anyio.sleep(0)
        await broker.publish(TurnEvent(session_id=session_id, review_id=review_id, kind="approved"))

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(publish)
        with anyio.fail_after(1):
            event_block = await anext(response.body_iterator)
        task_group.cancel_scope.cancel()
    await response.body_iterator.aclose()

    # Then
    for leak_key in LEAK_KEYS:
        assert leak_key not in event_block, f"leak: '{leak_key}' xuat hien trong SSE raw payload"
    lines = event_block.splitlines()
    payload = json.loads(lines[1].removeprefix("data: ").strip())
    assert set(payload.keys()) == {"event_id", "kind", "review_id", "client_turn_id", "message_id"}
