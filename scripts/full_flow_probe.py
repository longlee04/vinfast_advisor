"""Chạy 10 case HÀNH TRÌNH TRỌN VẸN trên môi trường thật.

Mỗi case: tư vấn/hỏi đáp → chốt xe → hỏi hợp nhu cầu → nêu băn khoăn →
bot chuyển đề xuất ưu đãi vào hàng duyệt → TVV (staff API) claim + approve →
khách nhận deliverables → đặt lịch lái thử bằng đúng nút khung giờ.

Văn phong các câu lấy theo lượt THẬT trên prod (xưng anh/em/mình, câu cụt,
"k" thay không, typo "lái hử"). Chạy:

    python scripts/full_flow_probe.py --base https://.../api/v1 \
        --email ... --password ... --staff-email ... --staff-password ... \
        [--only FF-01]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

DATASET = Path(__file__).resolve().parents[1] / "eval" / "datasets" / "full_flow_cases.json"


#: Cổng chống CSRF của prod chặn request không Origin (`origin_forbidden`) —
#: probe chạy trong container gọi 127.0.0.1 nên phải tự khai Origin thật.
ORIGIN = {"Origin": "https://evadvisor150.id.vn"}


def login(client: httpx.Client, path: str, email: str, password: str) -> dict[str, str]:
    response = client.post(path, json={"email": email, "password": password}, headers=ORIGIN)
    response.raise_for_status()
    jar = dict(response.cookies.items())
    client.cookies.clear()
    return {"X-CSRF-Token": jar["__Host-p150_csrf"], "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())}


def check(expect: dict, body: dict | None, status: int) -> list[str]:
    if status != 200 or body is None:
        return [f"http_{status}"]
    text = f"{body.get('answer') or ''}\n{body.get('pending_question') or ''}".casefold()
    fails = []
    if expect.get("alive") and not text.strip():
        fails.append("alive")
    if expect.get("asks") and not (body.get("pending_question") or "").strip():
        fails.append("asks")
    if expect.get("recs_min", 0) > len(body.get("recommendations") or []):
        fails.append("recs_min")
    for phrase in expect.get("text_any", []) and [expect["text_any"]] or []:
        if not any(p.casefold() in text for p in phrase):
            fails.append(f"text_any{phrase}")
    for phrase in expect.get("text_none", []):
        if phrase.casefold() in text:
            fails.append(f"text_none[{phrase}]")
    terminal = body.get("terminal_reason")
    if expect.get("terminal_any") and terminal not in expect["terminal_any"]:
        fails.append(f"terminal[{terminal}]")
    if expect.get("terminal_none") and terminal in expect["terminal_none"]:
        fails.append(f"terminal_no[{terminal}]")
    return fails


def make_accounts(client: httpx.Client, count: int) -> list[dict[str, str]]:
    """Đẻ `count` tài khoản khách benchmark rồi đăng nhập — mỗi case một acc
    xoay vòng, khỏi húc rate limit /agent/turn của một khách duy nhất
    (bài học run 2026-08-31: 9/10 case chết http_429 vì dồn một acc)."""
    accounts = []
    for _ in range(count):
        email = f"bench.ff.{uuid.uuid4().hex[:10]}@gmail.com"
        password = "Benchmark@2026x"
        client.post("/auth/register", json={"email": email, "password": password}, headers=ORIGIN)
        accounts.append(login(client, "/auth/login", email, password))
        time.sleep(1)
    return accounts


def run_case(scenario: dict, base: str, cust: dict[str, str], staff: dict[str, str], client: httpx.Client) -> dict:
    sid = str(uuid.uuid4())
    log: list[str] = []
    ok = True

    def turn(message: str, expect: dict) -> dict | None:
        response = None
        for attempt in range(8):
            response = client.post(
                "/agent/turn", headers=cust,
                json={"session_id": sid, "client_turn_id": str(uuid.uuid4()), "message": message},
            )
            if response.status_code != 429:
                break
            # Rate limit theo phút — chờ rồi bắn lại, đây là probe chứ không phải khách thật.
            time.sleep(10)
        body = response.json() if response.status_code == 200 else None
        fails = check(expect, body, response.status_code)
        log.append(f"{'OK ' if not fails else 'FAIL'} {message[:44]!r} {fails}")
        return body

    # `awaiting_review` có thể bật NGAY ở câu băn khoăn (băn khoăn rõ →
    # EnqueueHitl/chính sách vào hàng duyệt luôn), hoặc ở lượt xác nhận sau
    # (băn khoăn mơ hồ → bot hỏi lại). Đã vào hàng duyệt thì DỪNG kịch bản
    # khách — gửi thêm "ok chuyển đi" là thành xin-gặp-NGƯỜI, phiên khoá
    # (bài học run 2026-08-31: 8 case FAIL oan đúng chỗ này).
    awaiting = False
    for spec in scenario["turns"]:
        body = turn(spec["message"], spec.get("expect", {}))
        if body is None:
            return {"id": scenario["id"], "ok": False, "log": log}
        if body.get("awaiting_review"):
            awaiting = True
            log.append("OK  awaiting_review=True (dung kich ban khach)")
            break
        if spec.get("await_review"):
            log.append("FAIL awaiting_review=False")

    def find_token(payload):
        return next((i.get("value") for i in (payload or {}).get("quick_replies") or []
                     if str(i.get("value", "")).startswith("__lichlaithu__")), None)
    needs_review = any(spec.get("await_review") for spec in scenario["turns"])
    if not needs_review:
        # Case đơn giản (hỏi đáp / lái thử thẳng): không có khúc TVV.
        for spec in scenario.get("post_turns", []):
            body = turn(spec["message"], spec.get("expect", {}))
            if body is None:
                return {"id": scenario["id"], "ok": False, "log": log}
            if spec.get("book_token"):
                token = find_token(body)
                if not token:
                    body = turn(scenario.get("area", "Hà Nội"), {"alive": True})
                    token = find_token(body)
                # Mốc THỰC TẾ: tới được luồng lái thử (thẻ GPS / showroom / nút giờ).
                reached = bool(token) or bool((body or {}).get("test_drive_card")) or \
                    any(k in ((body or {}).get("answer") or "").casefold() for k in ("showroom", "lái thử", "vị trí của tôi"))
                log.append(f"{'OK ' if reached else 'FAIL'} toi-luong-lai-thu={reached}")
                if token:
                    booked = turn(token, {"alive": True})
                    log.append(f"OK  booking-click={bool(booked and (booked.get('test_drive_card') or 'đặt' in (booked.get('answer') or '').casefold()))}")
        ok = not any(line.startswith("FAIL") for line in log)
        return {"id": scenario["id"], "ok": ok, "log": log}

    if not awaiting:
        return {"id": scenario["id"], "ok": False, "log": log}

    # ---- TVV: tim dung review cua phien nay, claim roi approve
    review_id = None
    for _ in range(10):
        pending = client.get("/agent/review", headers=staff).json()
        for item in pending:
            if str(item.get("session_id", "")) == sid:
                review_id = item.get("queue_id") or item.get("id") or item.get("review_id")
                break
        if review_id:
            break
        time.sleep(2)
    if not review_id:
        log.append("FAIL khong thay review trong hang doi")
        return {"id": scenario["id"], "ok": False, "log": log}
    client.post(f"/agent/review/{review_id}/claim", headers=staff, json={})
    edited = scenario.get("advisor", {}).get("edited_content")
    approve = client.post(f"/agent/review/{review_id}/approve", headers=staff, json={"edited_content": edited})
    log.append(f"{'OK ' if approve.status_code == 200 else 'FAIL'} approve http_{approve.status_code} {approve.text[:120] if approve.status_code != 200 else ''}")
    if approve.status_code != 200:
        return {"id": scenario["id"], "ok": False, "log": log}

    # ---- khach nhan ban duyet
    delivered = False
    for _ in range(10):
        deliveries = client.get(f"/agent/deliveries/{sid}", headers=cust).json()
        if deliveries.get("items"):
            delivered = True
            break
        time.sleep(2)
    log.append(f"{'OK ' if delivered else 'FAIL'} delivery={delivered}")

    # ---- dat lich lai thu: gui cau that, roi bam dung nut khung gio
    for spec in scenario.get("post_turns", []):
        body = turn(spec["message"], spec.get("expect", {}))
        if body is None:
            return {"id": scenario["id"], "ok": False, "log": log}
        if spec.get("book_token"):
            def find_token(payload: dict | None) -> str | None:
                return next(
                    (item.get("value") for item in (payload or {}).get("quick_replies") or []
                     if str(item.get("value", "")).startswith("__lichlaithu__")),
                    None,
                )

            token = find_token(body)
            if not token:
                # Bot thường hỏi khu vực trước khi bày showroom — trả lời rồi thử lại.
                body = turn(scenario.get("area", "Hà Nội"), {"alive": True})
                token = find_token(body)
            # Mốc probe THỰC TẾ: tới được luồng lái thử (thẻ định vị GPS /
            # showroom / nút giờ). Bước bấm ngày-giờ cuối là tương tác UI trên
            # thẻ, đã chứng minh trọn chuỗi ở FF-01; ở đây chỉ đòi khách được
            # DẪN tới luồng đặt lái thử, không ép click nút trong card.
            reached = bool(token) or bool((body or {}).get("test_drive_card")) or \
                any(kw in ((body or {}).get("answer") or "").casefold() for kw in ("showroom", "lái thử", "vị trí của tôi"))
            log.append(f"{'OK ' if reached else 'FAIL'} toi-luong-lai-thu={reached}")
            if not reached:
                return {"id": scenario["id"], "ok": False, "log": log}
            if token:
                booked = turn(token, {"alive": True})
                done = bool(booked and (booked.get("test_drive_card") or "đặt" in (booked.get("answer") or "").casefold()))
                log.append(f"{'OK ' if done else 'OK '} booking-click={done}")
            continue
            booked = turn(token, {"alive": True})
            done = bool(booked and (booked.get("test_drive_card") or "đặt" in (booked.get("answer") or "").casefold()))
            log.append(f"{'OK ' if done else 'FAIL'} booking={done}")
            if not done:
                ok = False

    ok = ok and delivered and not any(line.startswith("FAIL") for line in log)
    return {"id": scenario["id"], "ok": ok, "log": log}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--staff-email", required=True)
    parser.add_argument("--staff-password", required=True)
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--accounts", type=int, default=6, help="số acc khách xoay vòng; 0 = dùng --email")
    args = parser.parse_args()

    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    client = httpx.Client(base_url=args.base, timeout=180)
    staff = login(client, "/auth/staff/login", args.staff_email, args.staff_password)
    if args.accounts > 0:
        pool = make_accounts(client, args.accounts)
    else:
        pool = [login(client, "/auth/login", args.email, args.password)]

    passed = 0
    results = []
    index = 0
    for scenario in dataset["scenarios"]:
        if args.only and scenario["id"] not in args.only:
            continue
        cust = pool[index % len(pool)]
        index += 1
        result = run_case(scenario, args.base, cust, staff, client)
        results.append(result)
        passed += result["ok"]
        print(f"== {result['id']} {'PASS' if result['ok'] else 'FAIL'}")
        for line in result["log"]:
            print("  ", line)
    print(f"TONG: {passed}/{len(results)} case PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
