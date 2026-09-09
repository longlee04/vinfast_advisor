"""Bộ kịch bản live-probe v2 — kiểm HÌNH DẠNG bộ dữ liệu và LOGIC chấm thuần.

Không gọi mạng: không có `_login()` / `run()` nào chạy trong file này. Bộ dữ liệu
chỉ chạy thật khi bắn vào server (xem `docs/handoff/probe-v2.md`), nên thứ duy
nhất test đơn vị gác được là: bộ đọc lên được, id không trùng, mỗi lượt có ít
nhất một tiêu chí, và MỌI khoá `expect` đều có nhánh thật trong `_check`.

Cái bẫy được gác ở đây: `_check` bỏ qua khoá lạ trong im lặng. Một khoá gõ nhầm
(`text_al`, `card_option_min`) không làm test đỏ, không làm probe đỏ — nó chỉ
biến kịch bản đó thành một lượt KHÔNG kiểm gì mà vẫn báo xanh.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from scripts import live_probe_eval as p

V2 = p.DATASET_V2
V1 = p.DATASET


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset() -> dict:
    return _load(V2)


# --- hình dạng bộ dữ liệu --------------------------------------------------------


def test_bo_v2_doc_len_duoc_va_du_kich_ban(dataset: dict) -> None:
    assert dataset["version"] == 2
    assert len(dataset["scenarios"]) >= 40


def test_id_khong_trung_va_dung_tien_to(dataset: dict) -> None:
    ids = [s["id"] for s in dataset["scenarios"]]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("V2-") for i in ids)


def test_moi_kich_ban_co_ten_nguon_va_it_nhat_mot_luot(dataset: dict) -> None:
    for scenario in dataset["scenarios"]:
        assert scenario["name"].strip(), scenario["id"]
        assert scenario["source"].strip(), scenario["id"]
        assert scenario["turns"], scenario["id"]


def test_moi_luot_co_it_nhat_mot_tieu_chi(dataset: dict) -> None:
    for scenario in dataset["scenarios"]:
        for index, turn in enumerate(scenario["turns"], start=1):
            assert turn["message"].strip(), f"{scenario['id']} t{index}"
            assert turn.get("expect"), f"{scenario['id']} t{index} không có tiêu chí nào"


def test_moi_khoa_expect_deu_duoc_check_ho_tro(dataset: dict) -> None:
    for scenario in dataset["scenarios"]:
        for index, turn in enumerate(scenario["turns"], start=1):
            unknown = set(turn["expect"]) - p.SUPPORTED_EXPECT_KEYS
            assert not unknown, f"{scenario['id']} t{index}: khoá lạ {unknown}"
    assert not set(dataset["global_expect"]) - p.SUPPORTED_EXPECT_KEYS


def test_moi_khoa_trong_danh_sach_ho_tro_deu_co_nhanh_that_trong_check() -> None:
    """Danh sách `SUPPORTED_EXPECT_KEYS` không được phép nói dối.

    `no_500` đứng ngoài: nó không có nhánh riêng — `_check` trả `http_<status>`
    cho mọi lượt khác 200 nên tiêu chí đó LUÔN bật.
    """

    source = inspect.getsource(p._check)
    for key in p.SUPPORTED_EXPECT_KEYS - {"no_500"}:
        assert f'"{key}"' in source, key
    assert "status != 200" in source


def test_the_duoc_dat_ten_dung_bang_card_fields(dataset: dict) -> None:
    for scenario in dataset["scenarios"]:
        for turn in scenario["turns"]:
            card = turn["expect"].get("card")
            if card is not None:
                assert card in p.CARD_FIELDS, f"{scenario['id']}: thẻ lạ {card}"


def test_bo_v1_van_doc_duoc_va_khong_co_global_expect() -> None:
    """`--dataset` mặc định vẫn là bộ v1, và bộ v1 KHÔNG bị đổi cách chấm."""

    v1 = _load(V1)
    assert v1["version"] == 1
    assert "global_expect" not in v1
    for scenario in v1["scenarios"]:
        for turn in scenario["turns"]:
            assert not set(turn.get("expect", {})) - p.SUPPORTED_EXPECT_KEYS


# --- logic chấm thuần ------------------------------------------------------------


def _body(**over: object) -> dict:
    body = {
        "answer": "Dạ, VF 5 tầm chạy 326 km mỗi lần sạc ạ.",
        "pending_question": "",
        "terminal_reason": None,
        "recommendations": [],
        "quick_replies": [],
        "test_drive_card": None,
        "tco_card": None,
        "comparison": None,
        "nearby_locations": None,
        "next_step_panel": None,
        "vehicle_details": None,
    }
    body.update(over)
    return body


def test_text_all_doi_du_moi_cum() -> None:
    assert p._check({"text_all": ["VF 5", "326"]}, _body(), 200) == []
    assert p._check({"text_all": ["VF 5", "VF 6"]}, _body(), 200) == ["text_all[VF 6]"]


def test_text_all_khong_phan_biet_hoa_thuong() -> None:
    assert p._check({"text_all": ["vf 5"]}, _body(), 200) == []


def test_card_doi_dung_field_cua_turn_response() -> None:
    assert p._check({"card": "tco"}, _body(), 200) == ["card[tco]"]
    assert p._check({"card": "tco"}, _body(tco_card={"vehicle_id": "v1"}), 200) == []
    assert p._check({"card": "khong-co-that"}, _body(), 200) == ["card[khong-co-that?]"]


def test_card_options_min_dem_o_khung_gio_con_cho() -> None:
    empty = _body(test_drive_card={"options": []})
    assert p._check({"card_options_min": 1}, empty, 200) == ["card_options_min(0<1)"]
    full = _body(test_drive_card={"options": [{"value": "a"}, {"value": "b"}]})
    assert p._check({"card_options_min": 2}, full, 200) == []
    # Không có thẻ nào thì cũng là không có ô nào — không được nổ AttributeError.
    assert p._check({"card_options_min": 1}, _body(), 200) == ["card_options_min(0<1)"]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("Xe có 7_SEATER và ADAS ạ.", "no_raw_output[enum:7_SEATER]"),
        ("Tầm chạy 500.00 km mỗi lần sạc.", "no_raw_output[decimal:500.00]"),
        ("Tầm chạy 500 km [1] mỗi lần sạc.", "no_raw_output[citation:[1]]"),
    ],
)
def test_no_raw_output_bat_ba_thu_spec_cam(answer: str, expected: str) -> None:
    assert p._check({"no_raw_output": True}, _body(answer=answer), 200) == [expected]


def test_no_raw_output_khong_bat_nham_gia_tien_va_ten_viet() -> None:
    clean = "Dạ giá VF 3 là 278.000.000 đồng, gói ADAS đầy đủ ạ."
    assert p._check({"no_raw_output": True}, _body(answer=clean), 200) == []


def test_no_raw_output_quet_ca_cau_hoi_tiep() -> None:
    body = _body(answer="Dạ vâng ạ.", pending_question="Anh/chị chọn LONG_RANGE hay bản thường ạ?")
    assert p._check({"no_raw_output": True}, body, 200) == ["no_raw_output[enum:LONG_RANGE]"]


def test_global_expect_gop_vao_moi_luot_va_expect_luot_thang() -> None:
    """Đúng phép gộp `run()` dùng: `{**global_expect, **turn_expect}`."""

    global_expect = {"no_raw_output": True}
    dirty = _body(answer="Bản 7_SEATER ạ.")
    assert p._check({**global_expect, **{"alive": True}}, dirty, 200) == [
        "no_raw_output[enum:7_SEATER]"
    ]
    assert p._check({**global_expect, **{"no_raw_output": False}}, dirty, 200) == []


def test_cac_tieu_chi_cu_van_cham_y_nhu_truoc() -> None:
    assert p._check({"alive": True, "asks": True}, _body(), 200) == ["asks"]
    assert p._check({"recs_min": 2}, _body(recommendations=[{}]), 200) == ["recs_min(1<2)"]
    assert p._check({"quick_replies_min": 1}, _body(), 200) == ["quick_replies_min"]
    assert p._check({"text_any": ["VF 9"]}, _body(), 200) == ["text_any['VF 9']"]
    assert p._check({"text_none": ["326"]}, _body(), 200) == ["text_none[326]"]
    assert p._check({"terminal_none": ["OUT_OF_SCOPE"]}, _body(terminal_reason="OUT_OF_SCOPE"), 200) == [
        "terminal[OUT_OF_SCOPE]"
    ]
    assert p._check({"alive": True}, None, 500) == ["http_500"]
