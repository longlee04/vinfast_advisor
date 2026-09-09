"""Câu hỏi chính sách đi đường tài liệu, KHÔNG đi đường danh mục xe.

Món nợ I4 của bước 3: `Lookup(mode=LOOKUP_POLICY)` rơi vào `catalog_browse`, mà
service đó chỉ biết đọc bảng `vehicles` rồi render danh sách theo loại — "bảo
hành mấy năm ạ?" nhận về một danh mục xe. Ở đây chốt ba điều: policy KHÔNG chạm
`catalog_browse`; có tài liệu thì câu trả lời do `synthesize_policy` viết từ
đúng các đoạn tìm được; không tài liệu (hoặc hỏng) thì nói thật và mời tư vấn
viên chứ không bịa.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.agents.core.act import ActResult, act
from src.agents.core.actions import LOOKUP_POLICY, Lookup
from src.agents.core.state import CoreState
from src.agents.services.registry import AgentServices


class FakeCatalogBrowse:
    """Nếu đường policy chạm tới đây là đã sai — fake này chỉ để bắt quả tang."""

    def __init__(self) -> None:
        self.calls = 0

    async def answer(self, **_kwargs: Any) -> None:
        self.calls += 1
        return None


class FakePolicySearch:
    def __init__(self, chunks: list[dict] | Exception) -> None:
        self._chunks = chunks
        self.queries: list[str] = []
        self.vehicle_ids: list[str | None] = []

    async def search(self, *, query: str, top_k: int = 5, **_kwargs: Any) -> list[dict]:
        self.queries.append(query)
        self.vehicle_ids.append(_kwargs.get("vehicle_id"))
        if isinstance(self._chunks, Exception):
            raise self._chunks
        return self._chunks


class FakeSynthesis:
    def __init__(self, answer: str | Exception) -> None:
        self._answer = answer
        self.seen: list[tuple[str, list[dict]]] = []

    async def synthesize_policy(self, *, query: str, chunks: list[dict], application: bool = False) -> str:
        self.seen.append((query, chunks))
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


_CHUNKS = [{"chunk_text": "Xe điện VinFast bảo hành 10 năm.", "source_file": "chinh-sach-bao-hanh.pdf"}]


async def _policy(services: AgentServices, *, user_message: str = "bảo hành mấy năm ạ") -> ActResult:
    return await act(
        Lookup(mode=LOOKUP_POLICY),
        CoreState(session_id="s1", chosen_vehicle_id="00000000-0000-0000-0000-000000000005"),
        services,
        run_id=None,
        customer_id="c1",
        user_message=user_message,
    )


@pytest.mark.asyncio
async def test_co_tai_lieu_thi_tra_cau_viet_tu_dung_cac_doan_do() -> None:
    search = FakePolicySearch(_CHUNKS)
    synthesis = FakeSynthesis("Dạ xe điện VinFast bảo hành 10 năm ạ.")
    browse = FakeCatalogBrowse()

    result = await _policy(AgentServices(policy_search=search, synthesis=synthesis, catalog_browse=browse))

    assert result.text == "Dạ xe điện VinFast bảo hành 10 năm ạ."
    assert search.queries == ["bảo hành mấy năm ạ"]
    assert synthesis.seen == [("bảo hành mấy năm ạ", _CHUNKS)]
    assert browse.calls == 0, "câu hỏi chính sách không bao giờ được hỏi danh mục xe"


@pytest.mark.asyncio
async def test_chua_cam_port_thi_noi_that_chu_khong_liet_ke_xe() -> None:
    browse = FakeCatalogBrowse()

    result = await _policy(AgentServices(catalog_browse=browse))

    assert "đã chuyển tư vấn viên" in result.text
    assert browse.calls == 0


@pytest.mark.asyncio
async def test_khong_tim_ra_doan_nao_thi_khong_goi_llm() -> None:
    synthesis = FakeSynthesis("câu này không được phép xuất hiện")

    result = await _policy(AgentServices(policy_search=FakePolicySearch([]), synthesis=synthesis))

    assert "đã chuyển tư vấn viên" in result.text
    assert synthesis.seen == [], "danh sách đoạn rỗng thì không có gì để dựa vào mà viết"


@pytest.mark.asyncio
async def test_tim_tai_lieu_hong_thi_khong_no_luot() -> None:
    result = await _policy(AgentServices(policy_search=FakePolicySearch(TimeoutError("pg 504"))))

    assert "đã chuyển tư vấn viên" in result.text


@pytest.mark.asyncio
async def test_viet_cau_hong_hoac_rong_thi_noi_that() -> None:
    hong = await _policy(
        AgentServices(policy_search=FakePolicySearch(_CHUNKS), synthesis=FakeSynthesis(RuntimeError("llm 500")))
    )
    rong = await _policy(AgentServices(policy_search=FakePolicySearch(_CHUNKS), synthesis=FakeSynthesis("   ")))

    assert "đã chuyển tư vấn viên" in hong.text
    assert "đã chuyển tư vấn viên" in rong.text


@pytest.mark.asyncio
async def test_luot_chinh_sach_khong_bao_gio_gan_the_lookup_facts() -> None:
    result = await _policy(
        AgentServices(policy_search=FakePolicySearch(_CHUNKS), synthesis=FakeSynthesis("Dạ 10 năm ạ."))
    )

    assert result.cards == {}


@pytest.mark.asyncio
async def test_citation_url_and_revision_are_appended_deterministically() -> None:
    chunks = [
        {
            **_CHUNKS[0],
            "source_url": "https://vinfastauto.com/vn_vi/thong-tin-bao-hanh",
            "source_revision": "2.2",
        }
    ]

    result = await _policy(
        AgentServices(policy_search=FakePolicySearch(chunks), synthesis=FakeSynthesis("Dạ 10 năm ạ."))
    )

    assert "Nguồn chính thức:" in result.text
    assert "bản 2.2" in result.text
    assert "https://vinfastauto.com/vn_vi/thong-tin-bao-hanh" in result.text


@pytest.mark.asyncio
async def test_policy_with_evidence_port_asks_for_model_before_searching() -> None:
    search = FakePolicySearch(_CHUNKS)

    result = await act(
        Lookup(mode=LOOKUP_POLICY),
        CoreState(session_id="s1"),
        AgentServices(policy_search=search, synthesis=FakeSynthesis("không được gọi")),
        run_id=None,
        customer_id="c1",
        user_message="bảo hành pin thế nào?",
    )

    assert result.text == "Anh/chị muốn hỏi chính sách cho mẫu xe nào ạ?"
    assert search.queries == []


@pytest.mark.asyncio
async def test_follow_up_policy_keeps_the_vehicle_already_chosen_in_state() -> None:
    search = FakePolicySearch(_CHUNKS)
    result = await act(
        Lookup(mode=LOOKUP_POLICY),
        CoreState(session_id="s1", chosen_vehicle_id="00000000-0000-0000-0000-000000000005"),
        AgentServices(policy_search=search, synthesis=FakeSynthesis("Dạ có ạ.")),
        run_id=None,
        customer_id="c1",
        user_message="bảo hành pin thì sao?",
    )

    assert result.text == "Dạ có ạ."
    assert search.vehicle_ids == ["00000000-0000-0000-0000-000000000005"]
