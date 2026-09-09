"""Chạy lại 34 phiên prod đã gán nhãn tay qua API thật (spec mục 9, Bước 4).

Nguồn 34 phiên: `docs/handoff/loi-v2-34-phien.md` — mỗi phiên một khối
`### <sid8> <ts> (N lượt)` rồi các dòng `N. U: '<tin nhắn khách>'` xen giữa
dòng trace `[...]` và dòng `B: '...'` (bỏ qua, không phải nguồn sự thật —
nguồn sự thật là API trả về lúc chạy lại). Mỗi phiên cũ được bắn lại bằng
MỘT `session_id` mới, giữ nguyên thứ tự tin nhắn khách.

Đăng nhập giống `scripts/live_probe_eval.py`: cookie `__Host-p150_csrf` khó
set tay nên ghép `Cookie` thủ công từ toàn bộ cookie đăng nhập trả về; thêm
header `Origin` vì backend chặn theo origin khi cookie có tiền tố `__Host-`.

Nút bấm dạng `__lichlaithu__|...` trong file nhãn không còn nghĩa gì khi bắn
lại qua API (giá trị cũ trỏ khung giờ/showroom của lần chạy trước) — thay
bằng `test_drive_card.options[0].value` của câu trả lời NGAY TRƯỚC đó; nếu
lượt trước không có card thì bỏ qua lượt này và ghi chú lại trong báo cáo.

Chạy:
    uv run python -m scripts.core_v2_replay \\
        --base http://127.0.0.1:18000/api/v1 \\
        --email <email đã bật cờ v2> --password <mk> \\
        --out eval/results/core-v2-replay/latest.md

Script CHỈ đọc file nhãn + gọi API. Không chạm DB, không sửa
`scripts/live_probe_eval.py`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

try:
    from scripts.core_v2_metrics import RE_RAW_LEAK
except ImportError:  # pragma: no cover — dự phòng nếu core_v2_metrics đổi chỗ/tên
    RE_RAW_LEAK = re.compile(r"\b[A-Z0-9]+_[A-Z0-9_]+\b|\d+\.00 (lít|km)|\[\d+\]")

DEFAULT_BASE = "http://127.0.0.1:18000/api/v1"
DEFAULT_FILE = "docs/handoff/loi-v2-34-phien.md"
LOGIN_ORIGIN = "https://evadvisor150.id.vn"
BUTTON_PREFIX = "__lichlaithu__"

#: `### 19e89de7 2026-08-25T19:13 (7 lượt)`
HEADER_RE = re.compile(r"^### ([0-9a-f]{8}) (\S+) \((\d+) lượt\)\s*$")
#: `1. U: 'chào em'` — chỉ khớp dòng U, bỏ qua dòng trace `[...]` và `B: '...'`.
USER_LINE_RE = re.compile(r"^\d+\.\s*U:\s*'(.*)'\s*$")


# --- parsing thuần (không mạng) --------------------------------------------------


def parse_sessions(text: str) -> list[dict[str, Any]]:
    """Tách file nhãn thành danh sách phiên `{sid, started_at, declared_turns, messages}`.

    Chỉ lấy dòng `U:` theo đúng thứ tự xuất hiện; dòng trace `[...]` và `B: '...'`
    bị bỏ qua vì đó là câu trả lời của LÕI CŨ, không phải nguồn sự thật khi chạy lại.
    """

    sessions: list[dict[str, Any]] = []
    for line in text.splitlines():
        header = HEADER_RE.match(line)
        if header:
            sid, started_at, declared_turns = header.group(1), header.group(2), int(header.group(3))
            sessions.append({"sid": sid, "started_at": started_at, "declared_turns": declared_turns, "messages": []})
            continue
        if not sessions:
            continue
        user = USER_LINE_RE.match(line)
        if user:
            sessions[-1]["messages"].append(user.group(1))
    return sessions


def substitute_button_value(message: str, last_body: dict[str, Any] | None) -> tuple[str, str | None]:
    """Thay tin nhắn nút `__lichlaithu__|...` bằng option thật lấy từ lượt trước.

    Trả `(tin_nhắn_để_gửi, lý_do_bỏ_qua)`. `lý_do_bỏ_qua` khác `None` nghĩa là
    KHÔNG gửi lượt này — file nhãn ghi giá trị nút của lần chạy cũ, không dùng lại được.
    """

    if not message.startswith(BUTTON_PREFIX):
        return message, None
    options = ((last_body or {}).get("test_drive_card") or {}).get("options") or []
    if not options:
        return message, "không có test_drive_card.options ở lượt trước"
    first = options[0]
    value = first.get("value") if isinstance(first, dict) else None
    if not value:
        return message, "option đầu tiên của test_drive_card không có value"
    return str(value), None


def summarize_turn_response(body: dict[str, Any] | None, status: int) -> dict[str, Any]:
    """Rút các trường cần cho báo cáo từ một câu trả lời `/agent/turn`."""

    body = body or {}
    answer = (body.get("answer") or "").strip()
    pending = (body.get("pending_question") or "").strip()
    card_raw = body.get("test_drive_card") or None
    card = None
    if card_raw:
        card = {
            "showrooms": len(card_raw.get("showrooms") or []),
            "options": len(card_raw.get("options") or []),
        }
    combined = f"{answer}\n{pending}"
    return {
        "status": status,
        "answer": answer,
        "pending_question": pending,
        "terminal_reason": body.get("terminal_reason"),
        "quick_replies": len(body.get("quick_replies") or []),
        "card": card,
        "raw_leak": bool(RE_RAW_LEAK.search(combined)) if combined.strip() else False,
        "empty": not (answer or pending),
    }


def build_summary(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Đếm dồn cho bảng tổng kết — chỉ tính trên các lượt THẬT SỰ đã gửi."""

    all_turns = [turn for session in sessions for turn in session["turns"]]
    sent_turns = [turn for turn in all_turns if not turn["skipped"]]
    return {
        "session_count": len(sessions),
        "turn_count": len(all_turns),
        "sent_turn_count": len(sent_turns),
        "skipped_count": sum(1 for turn in all_turns if turn["skipped"]),
        "http_errors": sum(1 for turn in sent_turns if turn["status"] != 200),
        "empty_answers": sum(1 for turn in sent_turns if turn["empty"]),
        "raw_leaks": sum(1 for turn in sent_turns if turn["raw_leak"]),
    }


def _fmt_bool(flag: bool) -> str:
    return "✓" if flag else "✗"


def render_markdown(report: dict[str, Any]) -> str:
    """Vẽ báo cáo Markdown: bảng tổng kết rồi từng phiên/lượt (U:/B:/flags)."""

    summary = report["summary"]
    lines = [
        f"# Chạy lại phiên gán nhãn qua lõi v2 — {report['run_at']}",
        "",
        f"Server `{report['base_url']}`",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Phiên | {summary['session_count']} |",
        f"| Lượt | {summary['turn_count']} (gửi {summary['sent_turn_count']}, bỏ qua {summary['skipped_count']}) |",
        f"| Lỗi HTTP | {summary['http_errors']} |",
        f"| Lượt câm (answer + pending đều rỗng) | {summary['empty_answers']} |",
        f"| Lượt lộ enum thô / số `.00` / `[n]` | {summary['raw_leaks']} |",
        "",
    ]
    for session in report["sessions"]:
        lines += [
            f"## `{session['sid']}` → `{session['new_session_id'][:8]}` ({session['started_at']})",
            "",
        ]
        for turn in session["turns"]:
            lines.append(f"- **U:** {turn['message']}")
            if turn["skipped"]:
                lines.append(f"  **B:** (bỏ qua — {turn['skip_reason']})")
                lines.append("")
                continue
            answer_text = turn["answer"] or turn["pending_question"] or "(RỖNG)"
            if len(answer_text) > 200:
                answer_text = answer_text[:200] + "…"
            lines.append(f"  **B:** {answer_text}")
            card = turn["card"]
            card_str = f"showrooms={card['showrooms']},options={card['options']}" if card else "—"
            flags = (
                f"pending={_fmt_bool(bool(turn['pending_question'].strip()))} "
                f"quick_replies={turn['quick_replies']} card={card_str} "
                f"term={turn['terminal_reason'] or '—'} lat={turn['latency_s']}s"
            )
            if turn.get("raw_leak"):
                flags += " raw_leak=✓"
            if turn.get("error"):
                flags += f" lỗi=`{turn['error']}`"
            lines.append(f"  flags: {flags}")
            lines.append("")
    return "\n".join(lines) + "\n"


# --- mạng (điểm chạm httpx duy nhất) ---------------------------------------------


def build_login_headers(cookies: dict[str, str]) -> dict[str, str]:
    """Ghép `Cookie`/`X-CSRF-Token` tay vì cookie `__Host-` khó set qua jar thường."""

    return {
        "X-CSRF-Token": cookies["__Host-p150_csrf"],
        "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items()),
    }


def login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": LOGIN_ORIGIN},
    )
    if response.status_code == 429:
        raise RuntimeError("Đăng nhập bị rate limit (429) — nhờ operator xoá auth_rate_limit_counters rồi thử lại")
    response.raise_for_status()
    cookies = dict(response.cookies.items())
    client.cookies.clear()
    return build_login_headers(cookies)


def run_replay(
    base: str,
    email: str,
    password: str,
    sessions: list[dict[str, Any]],
    delay: float,
) -> dict[str, Any]:
    client = httpx.Client(base_url=base, timeout=180)
    headers = login(client, email, password)
    out_sessions: list[dict[str, Any]] = []
    for index, session in enumerate(sessions, start=1):
        new_session_id = str(uuid.uuid4())
        turns: list[dict[str, Any]] = []
        last_body: dict[str, Any] | None = None
        for order, raw_message in enumerate(session["messages"], start=1):
            sent_message, skip_reason = substitute_button_value(raw_message, last_body)
            if skip_reason:
                turns.append(
                    {
                        "turn": order,
                        "message": raw_message,
                        "sent_message": None,
                        "skipped": True,
                        "skip_reason": skip_reason,
                        "status": None,
                        "latency_s": None,
                        "answer": "",
                        "pending_question": "",
                        "terminal_reason": None,
                        "quick_replies": 0,
                        "card": None,
                        "raw_leak": False,
                        "empty": False,
                        "error": "",
                    }
                )
                print(f"[{index}/{len(sessions)}] t{order} BỎ QUA ({skip_reason})", flush=True)
                continue
            started = time.perf_counter()
            error = ""
            try:
                response = client.post(
                    "/agent/turn",
                    headers=headers,
                    json={
                        "session_id": new_session_id,
                        "client_turn_id": str(uuid.uuid4()),
                        "message": sent_message,
                    },
                )
                status = response.status_code
                body = response.json() if status == 200 else None
            except Exception:  # noqa: BLE001 — chạy trên prod: một lượt hỏng không được giết cả vòng
                status, body = 0, None
                error = traceback.format_exc().splitlines()[-1]
            latency = round(time.perf_counter() - started, 2)
            fields = summarize_turn_response(body, status)
            if body is not None:
                last_body = body
            turns.append(
                {
                    "turn": order,
                    "message": raw_message,
                    "sent_message": sent_message,
                    "skipped": False,
                    "skip_reason": None,
                    "error": error,
                    "latency_s": latency,
                    **fields,
                }
            )
            print(
                f"[{index}/{len(sessions)}] t{order} HTTP {status} {sent_message[:48]!r}" + (" ERROR" if error else ""),
                flush=True,
            )
            if delay > 0:
                time.sleep(delay)
        out_sessions.append(
            {
                "sid": session["sid"],
                "started_at": session["started_at"],
                "new_session_id": new_session_id,
                "turns": turns,
            }
        )

    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "base_url": base,
        "summary": build_summary(out_sessions),
        "sessions": out_sessions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Chạy lại 34 phiên prod đã gán nhãn qua lõi v2 (spec mục 9)")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--email", default=os.environ.get("REPLAY_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("REPLAY_PASSWORD", ""))
    parser.add_argument("--file", default=DEFAULT_FILE, help="File nhãn 34 phiên")
    parser.add_argument("--only", default="", help="Chỉ chạy các sid8 này, cách nhau dấu phẩy")
    parser.add_argument(
        "--out", default="", help="File .md ghi báo cáo (mặc định eval/results/core-v2-replay/<stamp>.md)"
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Giây nghỉ giữa hai lượt gọi API")
    args = parser.parse_args()

    if not args.email or not args.password:
        print("Thiếu --email/--password (hoặc biến môi trường REPLAY_EMAIL/REPLAY_PASSWORD)", file=sys.stderr)
        return 2

    label_path = Path(args.file)
    if not label_path.is_file():
        print(f"Không thấy file nhãn: {label_path}", file=sys.stderr)
        return 2

    sessions = parse_sessions(label_path.read_text(encoding="utf-8"))
    only = {sid.strip() for sid in args.only.split(",") if sid.strip()}
    if only:
        sessions = [session for session in sessions if session["sid"] in only]
    if not sessions:
        print("Không có phiên nào khớp điều kiện", file=sys.stderr)
        return 1

    try:
        report = run_replay(args.base, args.email, args.password, sessions, args.delay)
    except Exception:  # noqa: BLE001 — chạy trên prod: in đủ traceback rồi mới thoát
        traceback.print_exc()
        return 1

    stamp = report["run_at"].replace(":", "").replace("+00:00", "Z")
    out_path = Path(args.out) if args.out else Path("eval/results/core-v2-replay") / f"{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(report), encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = report["summary"]
    print(f"\n{summary['session_count']} phiên, {summary['turn_count']} lượt → {out_path}")
    return 0 if summary["http_errors"] == 0 and summary["empty_answers"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
