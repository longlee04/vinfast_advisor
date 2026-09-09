"""Chạy BLIND SET lên prod: bắn từng lượt, ghi TRANSCRIPT — không chấm gì cả.

Khác `full_flow_probe.py` một cách có chủ đích: blind set không có `expect`
để khớp chuỗi. Việc của script này chỉ là làm KHÁCH gõ đúng kịch bản và ghi
lại trung thực bot trả gì; chấm điểm là việc của `rubric_judge.py` + người
soát. Trộn hai việc vào một là mở đường cho "sửa expect tới khi xanh" — đúng
thứ blind set sinh ra để chống.

Mỗi case một tài khoản benchmark mới (bài học run 2026-08-31: dồn một tài
khoản là húc rate limit 429 hàng loạt), và mọi request mang header Origin
thật vì cổng chống CSRF của prod chặn request thiếu Origin.

Chạy trong container backend trên VPS (gọi 127.0.0.1) hoặc qua SSH tunnel:

    python scripts/blind_run.py --base http://127.0.0.1:8000/api/v1 \
        --cases eval/blind/blind_cases.json --out eval/blind/runs
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

ORIGIN = {"Origin": "https://evadvisor150.id.vn"}
PASSWORD = "Benchmark@2026x"


def login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password}, headers=ORIGIN)
    response.raise_for_status()
    jar = dict(response.cookies.items())
    client.cookies.clear()
    return {
        "X-CSRF-Token": jar["__Host-p150_csrf"],
        "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items()),
        **ORIGIN,
    }


def make_account(client: httpx.Client) -> dict[str, str]:
    email = f"bench.blind.{uuid.uuid4().hex[:10]}@gmail.com"
    client.post("/auth/register", json={"email": email, "password": PASSWORD}, headers=ORIGIN)
    return login(client, email, PASSWORD)


def summarize_cards(body: dict) -> dict:
    """Tóm tắt thẻ đi kèm — người chấm cần biết khách THẤY gì ngoài chữ."""

    return {
        "recommendations": [
            item.get("display_name") for item in (body.get("recommendations") or [])
        ],
        "tco_card": bool(body.get("tco_card")),
        "test_drive_card": bool(body.get("test_drive_card")),
        "comparison": bool(body.get("comparison")),
        "nearby_locations": bool(body.get("nearby_locations")),
        "quick_replies": [item.get("label") for item in (body.get("quick_replies") or [])],
        "awaiting_review": bool(body.get("awaiting_review")),
        "terminal_reason": body.get("terminal_reason"),
    }


def run_case(case: dict, client: httpx.Client, headers: dict[str, str]) -> dict:
    session_id = str(uuid.uuid4())
    transcript: list[dict] = []
    for message in case["turns"]:
        body: dict | None = None
        status = 0
        for _ in range(8):
            response = client.post(
                "/agent/turn",
                headers=headers,
                json={"session_id": session_id, "client_turn_id": str(uuid.uuid4()), "message": message},
            )
            status = response.status_code
            if status != 429:
                body = response.json() if status == 200 else None
                break
            time.sleep(10)
        transcript.append(
            {
                "user": message,
                "status": status,
                "assistant": (body or {}).get("answer") or (body or {}).get("pending_question") or "",
                "cards": summarize_cards(body or {}),
            }
        )
        # Vào hàng duyệt là hết vai KHÁCH trong kịch bản — gửi tiếp là thành
        # xin-gặp-người và phiên khoá (bài học probe 2026-08-31).
        if (body or {}).get("awaiting_review"):
            transcript.append({"note": "awaiting_review=True — dừng kịch bản khách tại đây"})
            break
        time.sleep(1)
    return {
        "id": case["id"],
        "persona": case.get("persona", ""),
        "muc_tieu": case.get("muc_tieu", ""),
        "session_id": session_id,
        "transcript": transcript,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--out", default="eval/blind/runs")
    args = parser.parse_args()

    payload = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = payload["cases"]
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    with httpx.Client(base_url=args.base, timeout=90) as client:
        for index, case in enumerate(cases, start=1):
            headers = make_account(client)
            print(f"[{index}/{len(cases)}] {case['id']} ...", flush=True)
            results.append(run_case(case, client, headers))
            time.sleep(2)

    (out_dir / "transcripts.json").write_text(
        json.dumps({"ran_at": stamp, "base": args.base, "results": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [f"# Blind run {stamp}", ""]
    for result in results:
        lines += [f"## {result['id']} — {result['persona']}", f"*Mục tiêu:* {result['muc_tieu']}", ""]
        for entry in result["transcript"]:
            if "note" in entry:
                lines.append(f"> _{entry['note']}_")
                continue
            lines.append(f"**Khách:** {entry['user']}")
            lines.append(f"**Bot:** {entry['assistant'] or '(không có chữ — status ' + str(entry['status']) + ')'}")
            cards = entry["cards"]
            shown = [k for k, v in cards.items() if v and k != "quick_replies"]
            if shown:
                lines.append(f"_Thẻ/cờ: {shown}_")
            lines.append("")
    (out_dir / "transcripts.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Xong. Transcript: {out_dir}/transcripts.json (+ .md để đọc mắt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
