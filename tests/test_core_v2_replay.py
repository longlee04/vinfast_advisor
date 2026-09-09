"""`scripts/core_v2_replay.py` — chỉ kiểm các hàm thuần (parse/tóm tắt/vẽ báo cáo).

Không gọi mạng: không có login()/run_replay() thật nào chạy trong file này.
"""

from __future__ import annotations

from scripts import core_v2_replay as r

# Trích một đoạn nhỏ đúng định dạng thật của docs/handoff/loi-v2-34-phien.md,
# gồm cả dòng trace [...] và B: '...' cần bị bỏ qua khi parse.
FIXTURE = """\
# tiêu đề file, không phải phiên

```

### 19e89de7 2026-08-25T19:13 (2 lượt)
1. U: 'chào em'
   [|SOCIAL|NONE|SOCIAL||g=|rec=0]
   B: 'Chào anh/chị ạ.'
2. U: 'anh muốn tư vấn em ơi'
   [|REQUEST|NONE|SOCIAL||g=advisory_requested|rec=0]
   B: 'Anh/chị có đang tìm ô tô điện hay xe máy điện không ạ?'

### ad80fd39 2026-08-25T20:27 (1 lượt)
1. U: '__lichlaithu__|2026-08-27T09:00:00+00:00|VinFast HTA Hai Bà Trưng'
   [|SLOT_ANSWER|NONE|IN_SCOPE||g=|rec=0]
   B: 'Dạ vâng ạ.'
```
"""


# --- parse_sessions --------------------------------------------------------------


def test_parse_sessions_lay_dung_2_phien() -> None:
    sessions = r.parse_sessions(FIXTURE)
    assert [s["sid"] for s in sessions] == ["19e89de7", "ad80fd39"]


def test_parse_sessions_bo_qua_dong_trace_va_bot() -> None:
    sessions = r.parse_sessions(FIXTURE)
    first = sessions[0]
    assert first["started_at"] == "2026-08-25T19:13"
    assert first["declared_turns"] == 2
    assert first["messages"] == ["chào em", "anh muốn tư vấn em ơi"]


def test_parse_sessions_giu_nguyen_tin_nhan_nut() -> None:
    sessions = r.parse_sessions(FIXTURE)
    assert sessions[1]["messages"] == ["__lichlaithu__|2026-08-27T09:00:00+00:00|VinFast HTA Hai Bà Trưng"]


def test_parse_sessions_van_ban_khong_co_phien_tra_rong() -> None:
    assert r.parse_sessions("không có phiên nào ở đây\nchỉ có chữ") == []


# --- substitute_button_value ------------------------------------------------------


def test_substitute_button_giu_nguyen_neu_khong_phai_nut() -> None:
    message, reason = r.substitute_button_value("chào em", None)
    assert message == "chào em"
    assert reason is None


def test_substitute_button_thay_bang_option_dau_tien() -> None:
    last_body = {"test_drive_card": {"options": [{"value": "slot-A"}, {"value": "slot-B"}]}}
    message, reason = r.substitute_button_value("__lichlaithu__|cu", last_body)
    assert message == "slot-A"
    assert reason is None


def test_substitute_button_bo_qua_khi_khong_co_card() -> None:
    message, reason = r.substitute_button_value("__lichlaithu__|cu", None)
    assert message == "__lichlaithu__|cu"
    assert reason is not None


def test_substitute_button_bo_qua_khi_options_rong() -> None:
    last_body = {"test_drive_card": {"options": []}}
    _message, reason = r.substitute_button_value("__lichlaithu__|cu", last_body)
    assert reason is not None


# --- summarize_turn_response -------------------------------------------------------


def test_summarize_turn_response_binh_thuong() -> None:
    body = {
        "answer": "Dạ vâng ạ.",
        "pending_question": "",
        "terminal_reason": None,
        "quick_replies": [{"label": "Có", "value": "yes"}],
        "test_drive_card": {"showrooms": [{"id": 1}], "options": [{"value": "a"}, {"value": "b"}]},
    }
    fields = r.summarize_turn_response(body, 200)
    assert fields["status"] == 200
    assert fields["answer"] == "Dạ vâng ạ."
    assert fields["quick_replies"] == 1
    assert fields["card"] == {"showrooms": 1, "options": 2}
    assert fields["raw_leak"] is False
    assert fields["empty"] is False


def test_summarize_turn_response_rong_khong_co_answer_lan_pending() -> None:
    fields = r.summarize_turn_response({"answer": "", "pending_question": ""}, 200)
    assert fields["empty"] is True
    assert fields["card"] is None


def test_summarize_turn_response_bat_duoc_enum_tho() -> None:
    fields = r.summarize_turn_response({"answer": "Xe có ADAS_LEVEL2 tốt", "pending_question": ""}, 200)
    assert fields["raw_leak"] is True


def test_summarize_turn_response_bat_duoc_so_00_va_ngoac_vuong() -> None:
    assert r.summarize_turn_response({"answer": "đi được 500.00 km", "pending_question": ""}, 200)["raw_leak"]
    assert r.summarize_turn_response({"answer": "tham khảo [1]", "pending_question": ""}, 200)["raw_leak"]


def test_summarize_turn_response_body_none_khi_loi_http() -> None:
    fields = r.summarize_turn_response(None, 500)
    assert fields["status"] == 500
    assert fields["empty"] is True
    assert fields["card"] is None


# --- build_login_headers -----------------------------------------------------------


def test_build_login_headers_ghep_dung_cookie_va_csrf() -> None:
    headers = r.build_login_headers({"__Host-p150_csrf": "tok", "session": "sid"})
    assert headers["X-CSRF-Token"] == "tok"
    assert "session=sid" in headers["Cookie"]
    assert "__Host-p150_csrf=tok" in headers["Cookie"]


# --- build_summary + render_markdown ------------------------------------------------


def _fake_turn(**over: object) -> dict:
    base = {
        "turn": 1,
        "message": "chào em",
        "sent_message": "chào em",
        "skipped": False,
        "skip_reason": None,
        "error": "",
        "latency_s": 1.23,
        "status": 200,
        "answer": "Chào anh/chị ạ.",
        "pending_question": "",
        "terminal_reason": None,
        "quick_replies": 0,
        "card": None,
        "raw_leak": False,
        "empty": False,
    }
    base.update(over)
    return base


def test_build_summary_dem_dung_theo_luot_da_gui() -> None:
    sessions = [
        {
            "sid": "19e89de7",
            "started_at": "2026-08-25T19:13",
            "new_session_id": "abc",
            "turns": [
                _fake_turn(),
                _fake_turn(turn=2, status=500, empty=True, answer="", raw_leak=False),
                _fake_turn(turn=3, skipped=True, skip_reason="không có card", status=None),
            ],
        }
    ]
    summary = r.build_summary(sessions)
    assert summary["session_count"] == 1
    assert summary["turn_count"] == 3
    assert summary["sent_turn_count"] == 2
    assert summary["skipped_count"] == 1
    assert summary["http_errors"] == 1
    assert summary["empty_answers"] == 1


def test_render_markdown_co_bang_tong_ket_va_flags() -> None:
    report = {
        "run_at": "2026-08-29T10:00:00+00:00",
        "base_url": "http://127.0.0.1:18000/api/v1",
        "sessions": [
            {
                "sid": "19e89de7",
                "started_at": "2026-08-25T19:13",
                "new_session_id": "abcd1234-xxxx",
                "turns": [_fake_turn()],
            }
        ],
    }
    report["summary"] = r.build_summary(report["sessions"])
    markdown = r.render_markdown(report)
    assert "| Phiên | 1 |" in markdown
    assert "`19e89de7` → `abcd1234`" in markdown
    assert "**U:** chào em" in markdown
    assert "**B:** Chào anh/chị ạ." in markdown
    assert "pending=✗" in markdown
    assert "quick_replies=0" in markdown
    assert "card=—" in markdown
    assert "lat=1.23s" in markdown


def test_render_markdown_luot_bo_qua_ghi_ly_do() -> None:
    report = {
        "run_at": "2026-08-29T10:00:00+00:00",
        "base_url": "http://127.0.0.1:18000/api/v1",
        "sessions": [
            {
                "sid": "ad80fd39",
                "started_at": "2026-08-25T20:27",
                "new_session_id": "abcd1234-xxxx",
                "turns": [
                    _fake_turn(
                        message="__lichlaithu__|cu",
                        skipped=True,
                        skip_reason="không có test_drive_card.options ở lượt trước",
                        status=None,
                    )
                ],
            }
        ],
    }
    report["summary"] = r.build_summary(report["sessions"])
    markdown = r.render_markdown(report)
    assert "(bỏ qua — không có test_drive_card.options ở lượt trước)" in markdown


def test_render_markdown_cat_cau_tra_loi_qua_200_ky_tu() -> None:
    long_answer = "x" * 250
    report = {
        "run_at": "2026-08-29T10:00:00+00:00",
        "base_url": "http://127.0.0.1:18000/api/v1",
        "sessions": [
            {
                "sid": "19e89de7",
                "started_at": "2026-08-25T19:13",
                "new_session_id": "abcd1234-xxxx",
                "turns": [_fake_turn(answer=long_answer)],
            }
        ],
    }
    report["summary"] = r.build_summary(report["sessions"])
    markdown = r.render_markdown(report)
    assert ("x" * 200 + "…") in markdown
    assert ("x" * 201) not in markdown
