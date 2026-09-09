import pytest

from src.agents.api.dependencies import get_current_customer_id
from src.main import _customer_id_from_auth, app, lifespan


@pytest.mark.asyncio
async def test_lifespan_wires_runtime_dependency_for_current_test() -> None:
    # Given / When
    async with lifespan(app):
        # Then
        assert app.dependency_overrides[get_current_customer_id] is _customer_id_from_auth


def test_next_test_receives_clean_dependency_overrides() -> None:
    # Given / When / Then
    assert get_current_customer_id not in app.dependency_overrides
