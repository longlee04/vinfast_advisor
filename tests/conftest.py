import os
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app

# Static production seams (not test leftovers) must survive per-test cleanup.
# Document/Image authentication is intentionally wired before lifespan/Agent
# startup, so those routes do not depend on Agent availability.
_APPLICATION_OVERRIDES_AT_IMPORT = dict(app.dependency_overrides)

#: Ảnh chụp môi trường tại thời điểm `conftest` được import — tức TRƯỚC khi
#: pytest import bất kỳ module test nào. Xem `isolate_dotenv_from_collection`.
_ENVIRONMENT_AT_IMPORT = dict(os.environ)


@pytest.fixture(autouse=True, scope="session")
def isolate_dotenv_from_collection():
    """Bộ test chỉ được đọc môi trường NGƯỜI CHẠY cung cấp, không đọc `.env`.

    Bất kỳ module nào gọi `load_dotenv()` ở mức module cũng đủ để bơm toàn bộ
    `.env` của máy dev vào `os.environ` vĩnh viễn — và điều đó xảy ra ở bước
    COLLECT, trước khi test đầu tiên chạy, nên không thứ tự nào tránh được.

    Hậu quả: `tests/test_product/test_tco_assumptions_data.py` skip khi chạy
    riêng (không có DSN) nhưng lại CHẠY THẬT khi chạy cả bộ — đâm thẳng vào
    database đang phát triển của lập trình viên. Kết quả của nó khi đó phản ánh
    trạng thái migration trên máy đó, không phản ánh code trong commit. Cùng một
    commit cho hai kết quả khác nhau trên hai máy, và không ai nhìn vào file test
    đó mà đoán ra được lý do.

    Khôi phục về ảnh chụp đầu, KHÔNG xoá sạch: biến do shell/CI export ra vẫn còn
    nguyên, nên ai thật sự muốn chạy test cần database chỉ việc `export` như cũ.
    Thứ bị gỡ đúng là thứ một module không liên quan đã lén nạp vào.
    """

    for key in set(os.environ) - set(_ENVIRONMENT_AT_IMPORT):
        del os.environ[key]
    os.environ.update(_ENVIRONMENT_AT_IMPORT)
    yield


@pytest.fixture(autouse=True)
def restore_shared_app_state():
    """Trả `src.main.app` về đúng trạng thái trước mỗi test.

    `app` là một object DUY NHẤT ở mức module, dùng chung cho cả phiên test. Mọi
    test chạy lifespan thật đều để lại dấu vết trên nó — `_wire_agent_operations`
    ghi `dependency_overrides[get_current_customer_id] = _customer_id_from_auth`
    và `state.agent = AgentComposition(...)`, và không có ai gỡ ra.

    Hậu quả không nhìn thấy được từ chỗ gây ra nó. Test sau đó gọi
    `POST /api/v1/agent/turn` với body sai và mong 422; nhưng seam danh tính giờ
    đã bị nối vào Auth, nên FastAPI giải dependency TRƯỚC khi validate body →
    `_auth_identity` chạm database đã đóng → `SQLAlchemyError` → handler toàn cục
    trả 503 `auth_unavailable`. Test đỏ ở một file không liên quan gì, với một mã
    lỗi không liên quan gì, và chỉ đỏ khi chạy cả bộ.

    Đây đúng là ca mà `src/agents/api/dependencies.py` đã cảnh báo trong
    docstring ("raise ở đây sẽ che mất 422") — chỉ khác chỗ raise không nằm
    trong seam đó mà nằm sâu hơn một tầng.

    Ảnh chụp cả hai vì chúng luôn đi cùng nhau: gỡ override mà để lại
    `state.agent` thì route vẫn thấy một composition có engine đã đóng.
    """

    overrides = dict(app.dependency_overrides)
    state = dict(app.state._state)
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides)
        app.state._state.clear()
        app.state._state.update(state)


@pytest.fixture(autouse=True)
def isolate_application_singleton():
    """Give every test a clean FastAPI singleton and clear it afterward.

    Dọn SẠCH trước mỗi test (không chỉ khôi phục sau), rồi trả lại đúng bộ
    override có từ trước khi test chạy — `app.state._state.clear()` đã xoá luôn
    các attr `auth/document/image/locations/product/agent` vì chúng nằm trong
    chính dict đó.
    """
    overrides_before = dict(app.dependency_overrides)
    app.dependency_overrides.clear()
    app.dependency_overrides.update(_APPLICATION_OVERRIDES_AT_IMPORT)
    app.state._state.clear()
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(overrides_before)
        app.state._state.clear()


@pytest_asyncio.fixture
async def client():
    """Run application lifespan around each HTTP client."""
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
