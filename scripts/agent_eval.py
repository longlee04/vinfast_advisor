"""Chạy bộ 30 câu của plan agent-migration §5.1 qua API thật, cờ OFF rồi cờ ON.

Mỗi case chạy trên MỘT `session_id` mới: các lượt `setup` đưa phiên tới đúng
chặng, rồi lượt đo mới được gửi. Hai vòng (OFF/ON) dùng hai bộ `session_id`
khác nhau nên không dính state của nhau.

Cờ bật/tắt bằng chính bảng `agent_feature_flags` (TTL cache 60s ở adapter), nên
script ĐỢI `--flag-wait` giây sau mỗi lần đổi cờ. Không có DSN thì script chỉ
chạy được vòng "as-is" (`--mode current`) — dùng khi cờ đã được đặt tay.

Chạy:
    uv run python -m scripts.agent_eval \\
        --base http://127.0.0.1:18000/api/v1 \\
        --email <email> --password <mk> \\
        --dsn "$AGENT_DATABASE_URL" \\
        --out eval/results/agent-fallback/latest.md

Script CHỈ gọi API + `UPDATE agent_feature_flags`. Không sửa code, không đụng
bảng nghiệp vụ nào khác.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE = "http://127.0.0.1:18000/api/v1"
DEFAULT_DATASET = "eval/datasets/agent_fallback_cases.json"
DEFAULT_OUT_DIR = "eval/results/agent-fallback"
LOGIN_ORIGIN = "https://evadvisor150.id.vn"
FLAG_NAME = "agent_fallback"


# --- dataset (thuần, không mạng) -------------------------------------------------


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Đọc dataset và soát hình dạng — thiếu khoá là hỏng dữ liệu, không im lặng."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = list(payload.get("cases") or [])
    for case in cases:
        missing = {"id", "message", "ky_vong", "regression"} - set(case)
        if missing:
            raise ValueError(f"case {case.get('id')} thieu khoa: {sorted(missing)}")
        case.setdefault("setup", [])
    return cases


def regression_ids(cases: list[dict[str, Any]]) -> list[int]:
    """9 câu chặn phát hành (§5.1) — chữ cờ ON phải giống hệt cờ OFF."""

    return [int(case["id"]) for case in cases if case.get("regression")]


def compare_runs(off: dict[int, dict[str, Any]], on: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """So hai vòng: câu đổi chữ, câu regression bị đổi, latency, số lượt agent."""

    changed = [case_id for case_id in sorted(off) if case_id in on and off[case_id]["answer"] != on[case_id]["answer"]]
    agent_turns = [case_id for case_id in sorted(on) if on[case_id].get("agent_used")]
    return {
        "changed_ids": changed,
        "agent_ids": agent_turns,
        "latency_off": _percentiles([row["latency_s"] for row in off.values() if row["latency_s"] is not None]),
        "latency_on": _percentiles([row["latency_s"] for row in on.values() if row["latency_s"] is not None]),
    }


def _percentiles(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"p50": None, "p95": None}
    ordered = sorted(values)
    p95_index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return {"p50": round(statistics.median(ordered), 2), "p95": round(ordered[p95_index], 2)}


def render_markdown(report: dict[str, Any]) -> str:
    """Bảng so sánh OFF/ON + từng case, theo khuôn `scripts/core_v2_replay.py`."""

    diff = report["comparison"]
    cases = report["cases"]
    regression = set(report["regression_ids"])
    broken = sorted(set(diff["changed_ids"]) & regression)
    lines = [
        f"# Danh gia agent fallback — {report['run_at']}",
        "",
        f"Server `{report['base_url']}` · dataset `{report['dataset']}` · {len(cases)} case",
        "",
        "| Chi so | Co OFF | Co ON |",
        "|---|---|---|",
        f"| Case chay duoc | {report['ok_off']} | {report['ok_on']} |",
        f"| Luot di qua agent | 0 | {len(diff['agent_ids'])} |",
        f"| Latency p50 (s) | {diff['latency_off']['p50']} | {diff['latency_on']['p50']} |",
        f"| Latency p95 (s) | {diff['latency_off']['p95']} | {diff['latency_on']['p95']} |",
        f"| Case doi chu | — | {len(diff['changed_ids'])} |",
        f"| **Case regression bi doi (nguong A1 = 0)** | — | **{len(broken)}** |",
        "",
        f"Case doi chu: {diff['changed_ids'] or '—'}",
        "",
        f"Case di qua agent: {diff['agent_ids'] or '—'}",
        "",
        "## Tung case",
        "",
    ]
    for case in cases:
        case_id = int(case["id"])
        off = report["off"].get(case_id, {})
        on = report["on"].get(case_id, {})
        tag = " · REGRESSION" if case.get("regression") else ""
        lines += [
            f"### {case_id}. {case['message']}{tag}",
            "",
            f"- Ky vong: {case['ky_vong']}",
            f"- **OFF:** {_short(off.get('answer'))}",
            f"- **ON:**  {_short(on.get('answer'))}",
            f"- flags: doi_chu={'co' if off.get('answer') != on.get('answer') else 'khong'}"
            f" agent_used={'co' if on.get('agent_used') else 'khong'}"
            f" lat_off={off.get('latency_s')}s lat_on={on.get('latency_s')}s",
            "",
        ]
    return "\n".join(lines) + "\n"


def _short(text: str | None, limit: int = 220) -> str:
    value = (text or "").strip() or "(RONG)"
    return value if len(value) <= limit else value[:limit] + "…"


# --- mạng + DB (điểm chạm httpx / sqlalchemy duy nhất) ---------------------------


def build_login_headers(cookies: dict[str, str]) -> dict[str, str]:
    return {
        "X-CSRF-Token": cookies["__Host-p150_csrf"],
        "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
    }


def login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password}, headers={"Origin": LOGIN_ORIGIN})
    if response.status_code == 429:
        raise RuntimeError("Dang nhap bi rate limit (429) — xoa auth_rate_limit_counters roi thu lai")
    response.raise_for_status()
    cookies = dict(response.cookies.items())
    client.cookies.clear()
    return build_login_headers(cookies)


async def set_flag(dsn: str, *, enabled: bool, percent: int, allowlist: str) -> None:
    """Bật/tắt cờ bằng đúng bảng vận hành — không có đường tắt nào khác."""

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(dsn)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO agent_feature_flags (name, enabled, rollout_percent, customer_allowlist) "
                    "VALUES (:name, :enabled, :percent, :allow) "
                    "ON CONFLICT (name) DO UPDATE SET enabled = EXCLUDED.enabled, "
                    "rollout_percent = EXCLUDED.rollout_percent, customer_allowlist = EXCLUDED.customer_allowlist, "
                    "updated_at = now()"
                ),
                {"name": FLAG_NAME, "enabled": enabled, "percent": percent, "allow": allowlist},
            )
    finally:
        await engine.dispose()


def _post_turn(client: httpx.Client, headers: dict[str, str], session_id: str, message: str) -> tuple[Any, float, str]:
    started = time.perf_counter()
    try:
        response = client.post(
            "/agent/turn",
            headers=headers,
            json={"session_id": session_id, "client_turn_id": str(uuid.uuid4()), "message": message},
        )
        body = response.json() if response.status_code == 200 else None
        error = "" if response.status_code == 200 else f"HTTP {response.status_code}"
    except Exception:  # noqa: BLE001 — một case hỏng không được giết cả vòng
        body, error = None, traceback.format_exc().splitlines()[-1]
    return body, round(time.perf_counter() - started, 2), error


def run_round(
    client: httpx.Client, headers: dict[str, str], cases: list[dict[str, Any]], *, label: str, delay: float
) -> dict[int, dict[str, Any]]:
    """Một vòng chạy cả bộ case. Trả `{case_id: {answer, latency_s, error, ...}}`."""

    rows: dict[int, dict[str, Any]] = {}
    for index, case in enumerate(cases, start=1):
        session_id = str(uuid.uuid4())
        for setup_message in case["setup"]:
            _post_turn(client, headers, session_id, setup_message)
            time.sleep(delay)
        body, latency, error = _post_turn(client, headers, session_id, case["message"])
        body = body or {}
        rows[int(case["id"])] = {
            "answer": (body.get("answer") or "").strip(),
            "pending_question": (body.get("pending_question") or "").strip(),
            "terminal_reason": body.get("terminal_reason"),
            "has_card": any(bool(body.get(key)) for key in ("tco_card", "test_drive_card", "comparison")),
            "recommendations": len(body.get("recommendations") or []),
            "latency_s": latency,
            "error": error,
            # `agent_used` không có trong response HTTP (contract không đổi) —
            # suy bằng cách so với vòng OFF ở `compare_runs`, hoặc đọc
            # `turn_traces.payload.agent_used` bằng `scripts/core_v2_metrics.py`.
            "agent_used": None,
        }
        print(f"[{label}] {index}/{len(cases)} case {case['id']} ({latency}s) {error}", flush=True)
        time.sleep(delay)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Danh gia hai moc agent tren bo 30 cau (plan §5.1)")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--email", default=os.environ.get("REPLAY_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("REPLAY_PASSWORD", ""))
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--dsn", default=os.environ.get("AGENT_DATABASE_URL", ""))
    parser.add_argument("--mode", choices=("both", "off", "on", "current"), default="both")
    parser.add_argument("--flag-wait", type=float, default=65.0, help="Giay cho TTL cache co (60s) het han")
    parser.add_argument("--delay", type=float, default=0.5, help="Giay nghi giua hai luot goi API")
    parser.add_argument("--out", default="", help="File .md (mac dinh eval/results/agent-fallback/<stamp>.md)")
    args = parser.parse_args()

    if not args.email or not args.password:
        print("Thieu --email/--password (hoac REPLAY_EMAIL/REPLAY_PASSWORD)", file=sys.stderr)
        return 2
    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        print(f"Khong thay dataset: {dataset_path}", file=sys.stderr)
        return 2
    if args.mode in {"both", "off", "on"} and not args.dsn:
        print("Thieu --dsn (hoac AGENT_DATABASE_URL) de bat/tat co; dung --mode current neu da dat co tay", file=sys.stderr)
        return 2

    cases = load_cases(dataset_path)
    client = httpx.Client(base_url=args.base, timeout=180)
    headers = login(client, args.email, args.password)

    off_rows: dict[int, dict[str, Any]] = {}
    on_rows: dict[int, dict[str, Any]] = {}
    if args.mode in {"both", "off"}:
        asyncio.run(set_flag(args.dsn, enabled=False, percent=0, allowlist=""))
        time.sleep(args.flag_wait)
        off_rows = run_round(client, headers, cases, label="OFF", delay=args.delay)
    if args.mode in {"both", "on"}:
        asyncio.run(set_flag(args.dsn, enabled=True, percent=100, allowlist=""))
        time.sleep(args.flag_wait)
        on_rows = run_round(client, headers, cases, label="ON", delay=args.delay)
        # Tra cờ về TẮT ngay khi đo xong — không để môi trường ở trạng thái bật.
        asyncio.run(set_flag(args.dsn, enabled=False, percent=0, allowlist=""))
    if args.mode == "current":
        off_rows = run_round(client, headers, cases, label="AS-IS", delay=args.delay)

    for case_id, row in on_rows.items():
        row["agent_used"] = bool(off_rows) and off_rows.get(case_id, {}).get("answer") != row["answer"]

    report = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "base_url": args.base,
        "dataset": str(dataset_path),
        "cases": cases,
        "regression_ids": regression_ids(cases),
        "off": off_rows,
        "on": on_rows,
        "ok_off": sum(1 for row in off_rows.values() if not row["error"]),
        "ok_on": sum(1 for row in on_rows.values() if not row["error"]),
        "comparison": compare_runs(off_rows, on_rows),
    }
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    out_path = Path(args.out) if args.out else Path(DEFAULT_OUT_DIR) / f"{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_markdown(report), encoding="utf-8")
    out_path.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDa ghi {out_path} va {out_path.with_suffix('.json')}")
    broken = sorted(set(report["comparison"]["changed_ids"]) & set(report["regression_ids"]))
    if broken:
        print(f"CHAN PHAT HANH: {len(broken)} case regression doi chu: {broken}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
