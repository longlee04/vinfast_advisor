"""Live probe benchmark: bắn hội thoại THẬT vào API, chấm từng lượt theo tiêu chí tất định.

Khác `evaluate_slot_conversations.py` (offline, LLM giả): bộ này đi qua TOÀN BỘ
luồng — moderation, pending slot, graph, guardrail, HITL — với LLM thật, nên nó
đo đúng thứ khách nhìn thấy. Đổi lại nó chậm (~5 phút/25 kịch bản) và cần server
đang chạy + tài khoản khách.

Tiêu chí mỗi lượt (`expect`):
- `no_500`        không lỗi HTTP.
- `alive`         có chữ trả lời hoặc câu hỏi tiếp; không rơi UNAVAILABLE/rỗng.
- `asks`          có `pending_question` (bot đang dẫn tiếp).
- `recs_min`      số đề xuất tối thiểu.
- `quick_replies_min`
- `text_any`      answer+pending chứa ÍT NHẤT MỘT cụm (không phân biệt hoa thường).
- `text_all`      answer+pending chứa TẤT CẢ các cụm trong danh sách.
- `text_none`     KHÔNG chứa cụm nào trong danh sách.
- `terminal_none` `terminal_reason` KHÔNG thuộc danh sách.
- `card`          tên thẻ phải có mặt: test_drive | tco | comparison | nearby |
                  next_step | vehicle_details.
- `card_options_min`  số ô khung giờ còn chỗ trong `test_drive_card.options`.
- `no_raw_output` câu trả khách KHÔNG lộ enum thô (`7_SEATER`), số thô (`500.00`)
                  hay dấu trích dẫn `[1]`. Đặt ở `global_expect` để phủ mọi lượt.

Bộ dữ liệu: `--dataset`. Mặc định là bộ v1 (`live_probe_scenarios.json`); bộ v2
(`live_probe_v2.json`) viết theo lõi hội thoại v2 — xem `docs/handoff/probe-v2.md`.
Khoá `global_expect` ở cấp bộ dữ liệu được gộp vào MỌI lượt; `expect` của lượt
thắng khi trùng khoá.

Chạy:
    python scripts/live_probe_eval.py --base http://127.0.0.1:8000/api/v1 --out eval/results/live-probe
    python scripts/live_probe_eval.py --dataset eval/datasets/live_probe_v2.json --out eval/results/live-probe-v2
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx

DATASET = Path(__file__).resolve().parents[1] / "eval" / "datasets" / "live_probe_scenarios.json"
DATASET_V2 = DATASET.parent / "live_probe_v2.json"
DEAD_TERMINALS = {"UNAVAILABLE", "OUT_OF_SCOPE", "CONTENT_BLOCKED", "NO_CANDIDATE_ADVISOR_HANDOFF", "EXPIRED"}

#: Tên thẻ trong `expect.card` → tên field của `TurnResponse`. Dùng tên NGẮN ở
#: bộ dữ liệu để kịch bản đọc được bằng mắt, và một bảng duy nhất ở đây để đổi
#: field không phải sửa 40 kịch bản.
CARD_FIELDS = {
    "test_drive": "test_drive_card",
    "tco": "tco_card",
    "comparison": "comparison",
    "nearby": "nearby_locations",
    "next_step": "next_step_panel",
    "vehicle_details": "vehicle_details",
}

#: Ba thứ spec mục 7 CẤM tuyệt đối trong chữ trả khách. Xét trên chữ GỐC (không
#: casefold): enum thô phân biệt được với chữ thường chỉ nhờ hoa/thường.
#: Lookahead đòi ÍT NHẤT MỘT chữ hoa: `7_SEATER` mở đầu bằng số (đúng mã đã lọt
#: ra prod), còn `2026_08` thì không phải enum.
_RAW_ENUM = re.compile(r"\b(?=[A-Z0-9_]*[A-Z])[A-Z0-9]+(?:_[A-Z0-9]+)+\b")
#: `500.00 km`. Hai lớp chặn số liền kề để KHÔNG bắt nhầm `278.000.000` — dấu
#: chấm ở tiếng Việt còn là dấu phân nhóm nghìn.
_RAW_DECIMAL = re.compile(r"(?<!\d)\d+\.00(?!\d)")
_CITATION_MARK = re.compile(r"\[\d+\]")

#: Toàn bộ từ vựng `expect` mà `_check` hiểu. Bộ dữ liệu dùng khoá ngoài danh
#: sách này là gõ nhầm — nó sẽ được BỎ QUA trong im lặng, tức một kịch bản không
#: kiểm gì cả mà vẫn báo xanh. `tests/test_live_probe_v2_dataset.py` gác chỗ đó.
#: `no_500` không có nhánh riêng: `_check` đã trả `http_<status>` cho mọi lượt
#: khác 200, nên nó là tiêu chí LUÔN bật, giữ lại để bộ v1 đọc được bằng mắt.
SUPPORTED_EXPECT_KEYS = frozenset(
    {
        "no_500",
        "alive",
        "asks",
        "recs_min",
        "quick_replies_min",
        "text_any",
        "text_all",
        "text_none",
        "terminal_none",
        "card",
        "card_options_min",
        "no_raw_output",
    }
)


def _login(client: httpx.Client, email: str, password: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"email": email, "password": password})
    response.raise_for_status()
    jar = dict(response.cookies.items())
    client.cookies.clear()
    return {"X-CSRF-Token": jar["__Host-p150_csrf"], "Cookie": "; ".join(f"{k}={v}" for k, v in jar.items())}


def _check(expect: dict, body: dict | None, status: int) -> list[str]:
    """Trả danh sách tiêu chí ĐỎ (rỗng = lượt đạt)."""

    failures: list[str] = []
    if status != 200 or body is None:
        return [f"http_{status}"]
    answer = body.get("answer") or ""
    pending = body.get("pending_question") or ""
    raw = f"{answer}\n{pending}"
    text = raw.casefold()
    terminal = body.get("terminal_reason")
    recs = body.get("recommendations") or []
    quick = body.get("quick_replies") or []
    if expect.get("alive") and (not text.strip() or terminal == "UNAVAILABLE"):
        failures.append("alive")
    if expect.get("asks") and not pending.strip():
        failures.append("asks")
    if expect.get("recs_min", 0) > len(recs):
        failures.append(f"recs_min({len(recs)}<{expect['recs_min']})")
    if expect.get("quick_replies_min", 0) > len(quick):
        failures.append("quick_replies_min")
    if expect.get("text_any") and not any(term.casefold() in text for term in expect["text_any"]):
        failures.append(f"text_any{expect['text_any']}")
    for term in expect.get("text_all", []):
        if term.casefold() not in text:
            failures.append(f"text_all[{term}]")
    for term in expect.get("text_none", []):
        if term.casefold() in text:
            failures.append(f"text_none[{term}]")
    if terminal in expect.get("terminal_none", []):
        failures.append(f"terminal[{terminal}]")
    card_name = expect.get("card")
    if card_name:
        field = CARD_FIELDS.get(card_name)
        if field is None:
            failures.append(f"card[{card_name}?]")
        elif not body.get(field):
            failures.append(f"card[{card_name}]")
    if expect.get("card_options_min", 0):
        options = ((body.get("test_drive_card") or {}).get("options")) or []
        if len(options) < expect["card_options_min"]:
            failures.append(f"card_options_min({len(options)}<{expect['card_options_min']})")
    if expect.get("no_raw_output"):
        for name, pattern in (("enum", _RAW_ENUM), ("decimal", _RAW_DECIMAL), ("citation", _CITATION_MARK)):
            found = pattern.search(raw)
            if found:
                failures.append(f"no_raw_output[{name}:{found.group(0)}]")
    return failures


def run(base: str, email: str, password: str, only: set[str], dataset_path: Path = DATASET) -> dict:
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    # Tiêu chí phủ MỌI lượt (v2: cấm enum thô / số thô / `[n]`). Bộ v1 không có
    # khoá này nên nó chấm y hệt như trước.
    global_expect: dict = dataset.get("global_expect") or {}
    client = httpx.Client(base_url=base, timeout=180)
    headers = _login(client, email, password)
    scenarios: list[dict] = []
    for scenario in dataset["scenarios"]:
        if only and scenario["id"] not in only:
            continue
        session_id = str(uuid.uuid4())
        turns: list[dict] = []
        for index, turn in enumerate(scenario["turns"], start=1):
            started = time.perf_counter()
            response = client.post(
                "/agent/turn",
                headers=headers,
                json={"session_id": session_id, "client_turn_id": str(uuid.uuid4()), "message": turn["message"]},
            )
            latency = time.perf_counter() - started
            body = response.json() if response.status_code == 200 else None
            failures = _check({**global_expect, **turn.get("expect", {})}, body, response.status_code)
            turns.append(
                {
                    "turn": index,
                    "message": turn["message"],
                    "status": response.status_code,
                    "latency_s": round(latency, 2),
                    "terminal_reason": (body or {}).get("terminal_reason"),
                    "answer": ((body or {}).get("answer") or "")[:400],
                    "pending_question": ((body or {}).get("pending_question") or "")[:300],
                    "recommendations": len((body or {}).get("recommendations") or []),
                    "failures": failures,
                    "passed": not failures,
                }
            )
            print(
                f"{scenario['id']} t{index} {'OK ' if not failures else 'FAIL'} {latency:4.1f}s {turn['message'][:40]!r} {failures}",
                flush=True,
            )
        scenarios.append(
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "source": scenario.get("source", ""),
                "session_id": session_id,
                "turns": turns,
                "passed": all(t["passed"] for t in turns),
                "turns_passed": sum(t["passed"] for t in turns),
                "turns_total": len(turns),
            }
        )
    return _summarize(scenarios, base, Path(dataset_path).name)


def _summarize(scenarios: list[dict], base: str, dataset: str = DATASET.name) -> dict:
    turns = [t for s in scenarios for t in s["turns"]]
    latencies = [t["latency_s"] for t in turns]
    by_source: dict[str, dict[str, int]] = {}
    for scenario in scenarios:
        bucket = by_source.setdefault(scenario["source"] or "?", {"scenarios": 0, "passed": 0})
        bucket["scenarios"] += 1
        bucket["passed"] += int(scenario["passed"])
    return {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "base_url": base,
        "dataset": dataset,
        "scenario_count": len(scenarios),
        "scenario_pass": sum(s["passed"] for s in scenarios),
        "turn_count": len(turns),
        "turn_pass": sum(t["passed"] for t in turns),
        "http_errors": sum(t["status"] != 200 for t in turns),
        "dead_turns": sum(t["terminal_reason"] in DEAD_TERMINALS for t in turns),
        "latency_p50_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95_s": round(sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)], 2) if latencies else None,
        "by_source": by_source,
        "scenarios": scenarios,
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# Live probe benchmark — {report['run_at']}",
        "",
        f"Server: `{report['base_url']}` · bộ dữ liệu: `{report.get('dataset', DATASET.name)}`",
        "",
        "| Chỉ số | Giá trị |",
        "|---|---|",
        f"| Kịch bản đạt | **{report['scenario_pass']}/{report['scenario_count']}** |",
        f"| Lượt đạt | **{report['turn_pass']}/{report['turn_count']}** |",
        f"| Lỗi HTTP (500/429…) | {report['http_errors']} |",
        f"| Lượt chết (OUT_OF_SCOPE / UNAVAILABLE / CONTENT_BLOCKED / NO_CANDIDATE / EXPIRED) | {report['dead_turns']} |",
        f"| Độ trễ p50 / p95 | {report['latency_p50_s']}s / {report['latency_p95_s']}s |",
        "",
        "| Nguồn | Kịch bản đạt |",
        "|---|---|",
    ]
    for source, bucket in report["by_source"].items():
        lines.append(f"| {source} | {bucket['passed']}/{bucket['scenarios']} |")
    lines += ["", "## Từng kịch bản", "", "| ID | Tên | Lượt đạt | Lượt đỏ (tiêu chí) |", "|---|---|---|---|"]
    for scenario in report["scenarios"]:
        failed = (
            "; ".join(f"t{t['turn']} {','.join(t['failures'])}" for t in scenario["turns"] if not t["passed"]) or "—"
        )
        mark = "✅" if scenario["passed"] else "❌"
        lines.append(
            f"| {scenario['id']} | {mark} {scenario['name']} | {scenario['turns_passed']}/{scenario['turns_total']} | {failed} |"
        )
    lines += ["", "## Lượt đỏ — chi tiết", ""]
    for scenario in report["scenarios"]:
        for turn in scenario["turns"]:
            if turn["passed"]:
                continue
            lines += [
                f"### {scenario['id']} t{turn['turn']} — `{turn['message']}`",
                f"- tiêu chí đỏ: `{turn['failures']}` · terminal: `{turn['terminal_reason']}` · HTTP {turn['status']}",
                f"- bot: {(turn['answer'] or turn['pending_question'] or '(rỗng)')[:300]}",
                "",
            ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--email", default="customer@gmail.com")
    parser.add_argument("--password", default="Customer@123456")
    parser.add_argument("--out", default="eval/results/live-probe")
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--dataset", default=str(DATASET), help="bộ kịch bản; mặc định bộ v1")
    args = parser.parse_args()
    report = run(args.base, args.email, args.password, set(args.only), Path(args.dataset))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = report["run_at"].replace(":", "").replace("+00:00", "Z")
    (out / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / f"{stamp}.md").write_text(render_markdown(report), encoding="utf-8")
    (out / "latest.md").write_text(render_markdown(report), encoding="utf-8")
    print(
        f"\n{report['scenario_pass']}/{report['scenario_count']} kịch bản, {report['turn_pass']}/{report['turn_count']} lượt → {out / (stamp + '.md')}"
    )
    return 0 if report["scenario_pass"] == report["scenario_count"] else 1


if __name__ == "__main__":
    sys.exit(main())
