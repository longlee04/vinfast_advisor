"""Acceptance Criteria PRD 5.1 -> 5.6 tren mot luot that, hai loai phuong tien."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from src.agents.adapters.clock import SystemClock
from src.agents.adapters.conversation_repository import SqlAlchemySessionRepository
from src.agents.chain import run_turn
from src.agents.models import AgentRunRow, ReviewQueueRow, RunEvidenceRow, ScoringResultRow
from src.products.infrastructure.models import (
    CarSpecRow,
    MotorbikeSpecRow,
    VehiclePriceRow,
    VehicleRow,
)


@pytest_asyncio.fixture(autouse=True)
async def acceptance_catalog(migrated_engine: AsyncEngine) -> AsyncIterator[None]:
    """Seed minimal active catalog rows required by PRD acceptance preconditions."""

    now = datetime.now(UTC)
    car_id = str(uuid4())
    motorbike_id = str(uuid4())
    session_factory = async_sessionmaker(migrated_engine, expire_on_commit=False)
    async with session_factory() as session, session.begin():
        session.add_all(
            [
                VehicleRow(
                    vehicle_id=car_id,
                    vehicle_type="CAR",
                    brand="VinFast",
                    model_name="VF 7",
                    variant_name="Acceptance",
                    status="ACTIVE",
                    slug=f"vf-7-acceptance-{car_id}",
                    created_at=now,
                    updated_at=now,
                ),
                CarSpecRow(
                    vehicle_id=car_id,
                    seat_count=5,
                    range_km=Decimal("400"),
                    created_at=now,
                    updated_at=now,
                ),
                VehiclePriceRow(
                    price_id=str(uuid4()),
                    vehicle_id=car_id,
                    price_type="STARTING_PRICE",
                    amount_vnd=700_000_000,
                    currency="VND",
                    region_code="VN",
                    status="ACTIVE",
                    valid_from=now,
                    created_at=now,
                    updated_at=now,
                ),
                VehicleRow(
                    vehicle_id=motorbike_id,
                    vehicle_type="ELECTRIC_MOTORBIKE",
                    brand="VinFast",
                    model_name="Evo",
                    variant_name="Acceptance",
                    status="ACTIVE",
                    slug=f"evo-acceptance-{motorbike_id}",
                    created_at=now,
                    updated_at=now,
                ),
                MotorbikeSpecRow(
                    vehicle_id=motorbike_id,
                    range_min_km=Decimal("50"),
                    range_max_km=Decimal("100"),
                    created_at=now,
                    updated_at=now,
                ),
                VehiclePriceRow(
                    price_id=str(uuid4()),
                    vehicle_id=motorbike_id,
                    price_type="STARTING_PRICE",
                    amount_vnd=30_000_000,
                    currency="VND",
                    region_code="VN",
                    status="ACTIVE",
                    valid_from=now,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
    yield
    async with session_factory() as session, session.begin():
        vehicle_ids = (car_id, motorbike_id)
        await session.execute(delete(VehiclePriceRow).where(VehiclePriceRow.vehicle_id.in_(vehicle_ids)))
        await session.execute(delete(CarSpecRow).where(CarSpecRow.vehicle_id.in_(vehicle_ids)))
        await session.execute(delete(MotorbikeSpecRow).where(MotorbikeSpecRow.vehicle_id.in_(vehicle_ids)))
        await session.execute(delete(VehicleRow).where(VehicleRow.vehicle_id.in_(vehicle_ids)))


async def _create_session(engine: AsyncEngine, session_id: str, customer_id: str) -> None:
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as setup_session, setup_session.begin():
        await SqlAlchemySessionRepository(setup_session, SystemClock()).ensure_session(session_id, customer_id, None)


#: Trần số lượt tư vấn trước khi bộ test bỏ cuộc. Có trần để một luồng hỏi vòng
#: quanh gãy thành lỗi đọc được, thay vì treo cho tới khi pytest hết giờ.
_MAX_ADVISORY_TURNS = 4

#: Câu "không có yêu cầu thêm" cho những lượt hỏi tiếp theo, nếu có.
_NO_EXTRA_NEED = "khong can tinh nang gi dac biet"


async def _tu_van_toi_khi_co_de_xuat(turn, second_message: str):
    """Chạy tới KHI có bản đề xuất, không khoá cứng nó rơi vào lượt thứ mấy.

    **Quyết định 2026-08-26 thay thế quyết định 2026-08-21.** Bản cũ khoá
    "đủ lượt 1 thì lượt 2 LUÔN hỏi tính năng" và bộ test assert đúng câu đó.
    Chính sách hiện hành ngược lại: đủ nhu cầu thì ra thẳng bản đề xuất, còn
    bằng chứng tính năng suy từ `NeedTag`/evidence chứ không hỏi chủ động.
    ĐỪNG khôi phục câu assert cũ — nó kéo luồng dài ra và đảo một quyết định
    sản phẩm mới hơn.

    Đo được vì sao phải bỏ khoá số lượt: bộ này gọi LLU thật, và số lượt hỏi
    trước khi chốt đổi theo hành vi mô hình. Cùng một commit, cùng một CSDL
    (bộ test agent dựng CSDL riêng rồi xoá, nên KHÔNG có chuyện lây dữ liệu
    giữa các file), test đỏ 4/4 lần hôm nay trong khi mốc chụp sáng cùng ngày
    còn xanh. Cái đáng khoá là KẾT QUẢ, không phải đường đi tới nó.
    """

    last = None
    for index in range(_MAX_ADVISORY_TURNS):
        last = await turn(second_message if index == 0 else _NO_EXTRA_NEED)
        assert last.terminal_reason is None, f"luong dung som o luot {index + 2}: {last.terminal_reason}"
        if last.recommendations:
            return last
    raise AssertionError(f"khong ra duoc ban de xuat trong {_MAX_ADVISORY_TURNS} luot; lan cuoi: {last}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_message", "second_message"),
    [
        (
            "toi muon mua o to",
            "nha 5 nguoi, ngan sach 800 trieu, co sac tai nha, di lam moi ngay 30km, uu tien gia dinh",
        ),
        (
            "toi muon mua xe may dien",
            "de di lam, ngan sach 30 trieu, co sac tai nha, moi ngay 20km",
        ),
    ],
)
async def test_full_advisory_turn_delivers_an_evidence_backed_recommendation(
    agent_composition,
    agent_session,
    migrated_engine: AsyncEngine,
    first_message,
    second_message,
):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)

    async def turn(message: str):
        return await run_turn(
            agent_composition.graph,
            agent_composition.services,
            session_id=session_id,
            customer_id=customer_id,
            user_message=message,
        )

    # Dữ kiện CHƯA đủ (mới có loại xe) thì phải HỎI, không được đoán bừa.
    first = await turn(first_message)
    assert first.pending_question
    assert first.answer is None

    final = await _tu_van_toi_khi_co_de_xuat(turn, second_message)

    assert final.answer, "phai co phan hoi cho khach"
    assert final.awaiting_review is False

    # Một lượt tư vấn có thể mở nhiều run (lượt hỏi thêm rồi lượt ra kết quả) —
    # lấy run MỚI NHẤT, đúng cái đã chạy tới layer2/evidence.
    run_id = await agent_session.scalar(
        select(AgentRunRow.run_id)
        .where(AgentRunRow.session_id == session_id)
        .order_by(AgentRunRow.created_at.desc())
        .limit(1)
    )
    assert run_id is not None, "PRD 5.2: luot truy xuat phai mo mot run"

    evidence = await agent_session.scalar(
        select(func.count()).select_from(RunEvidenceRow).where(RunEvidenceRow.run_id == run_id)
    )
    assert evidence > 0

    scored = (
        (await agent_session.execute(select(ScoringResultRow).where(ScoringResultRow.run_id == run_id))).scalars().all()
    )
    assert 1 <= len(scored) <= 3
    assert all(len(row.reasons) >= 2 for row in scored)

    queued = (
        (await agent_session.execute(select(ReviewQueueRow).where(ReviewQueueRow.run_id == run_id))).scalars().all()
    )
    assert queued == []


@pytest.mark.asyncio
async def test_acceptance_catalog_fixture_has_an_active_vehicle_per_type(agent_session) -> None:
    total = await agent_session.scalar(
        select(func.count()).select_from(VehicleRow).where(VehicleRow.status == "ACTIVE")
    )

    assert total == 2


@pytest.mark.asyncio
async def test_out_of_scope_question_is_refused_with_an_escape_route(
    agent_composition, agent_session, migrated_engine: AsyncEngine
):
    session_id, customer_id = str(uuid4()), f"customer-{uuid4()}"
    await _create_session(migrated_engine, session_id, customer_id)

    result = await run_turn(
        agent_composition.graph,
        agent_composition.services,
        session_id=session_id,
        customer_id=customer_id,
        user_message="cho toi xin bang gia xe Toyota Vios",
    )

    assert result.terminal_reason == "OUT_OF_SCOPE"
    assert "tư vấn viên" in (result.answer or "")
    queued = await agent_session.scalar(select(func.count()).select_from(ReviewQueueRow))
    assert queued == 0, "cau ngoai pham vi khong duoc chiem cho trong hang doi"
