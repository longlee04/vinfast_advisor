"""Doc anh xe tu MinIO qua object key da luu trong catalog."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.adapters.vehicle_image import MinioVehicleImageSource
from src.products.infrastructure.models import VehicleRow


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class _FakeMinio:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self._objects = objects
        self.requested: list[str] = []
        self.responses: list[_FakeResponse] = []

    def get_object(self, *, bucket_name: str, object_name: str) -> _FakeResponse:
        del bucket_name
        self.requested.append(object_name)
        response = _FakeResponse(self._objects[object_name])
        self.responses.append(response)
        return response


class _FailingMinio:
    def get_object(self, *, bucket_name: str, object_name: str) -> _FakeResponse:
        del bucket_name, object_name
        raise OSError("storage unavailable")


class _SessionContext:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        return None


class _SessionFactory:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def __call__(self) -> _SessionContext:
        return _SessionContext(self._session)


async def _insert_vehicle(session: AsyncSession, image_object_key: str | None) -> UUID:
    vehicle_id = uuid4()
    now = datetime.now(UTC)
    model_name = f"VF 8 {vehicle_id}"
    session.add(
        VehicleRow(
            vehicle_id=str(vehicle_id),
            vehicle_type="CAR",
            brand="VinFast",
            model_name=model_name,
            variant_name=None,
            model_year=None,
            status="ACTIVE",
            slug=f"vf-8-{vehicle_id}",
            image_url=None,
            image_object_key=image_object_key,
            image_sha256=None,
            detail_url=None,
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()
    return vehicle_id


@pytest.mark.asyncio
async def test_vehicle_without_object_key_returns_none(agent_session: AsyncSession) -> None:
    vehicle_id = await _insert_vehicle(agent_session, None)
    client = _FakeMinio({})
    source = MinioVehicleImageSource(session_factory=_SessionFactory(agent_session), client=client, bucket_name="p150")

    result = await source.load(vehicle_id)

    assert result is None
    assert client.requested == []


@pytest.mark.asyncio
async def test_storage_failure_returns_none_instead_of_raising(agent_session: AsyncSession) -> None:
    vehicle_id = await _insert_vehicle(agent_session, "vehicles/failing.png")
    source = MinioVehicleImageSource(
        session_factory=_SessionFactory(agent_session), client=_FailingMinio(), bucket_name="p150"
    )

    result = await source.load(vehicle_id)

    assert result is None


@pytest.mark.asyncio
async def test_successful_read_closes_and_releases_response(agent_session: AsyncSession) -> None:
    object_key = "vehicles/success.png"
    vehicle_id = await _insert_vehicle(agent_session, object_key)
    client = _FakeMinio({object_key: b"png-bytes"})
    source = MinioVehicleImageSource(session_factory=_SessionFactory(agent_session), client=client, bucket_name="p150")

    result = await source.load(vehicle_id)

    assert result == b"png-bytes"
    assert client.requested == [object_key]
    assert client.responses[0].closed is True
    assert client.responses[0].released is True
