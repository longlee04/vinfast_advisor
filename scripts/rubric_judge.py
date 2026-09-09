"""Chấm hội thoại theo RUBRIC 4 tiêu chí — LLM chấm, NGƯỜI soát.

Nguồn hội thoại: transcript của blind run (`--transcripts`), hoặc phiên THẬT
của khách trong DB prod (`--from-db`, chạy trong container backend nơi có
`DATABASE_URL`/`AGENT_DATABASE_URL` và `OPENAI_API_KEY`).

Rubric mỗi lượt bot:
  1. dung_y     — trả lời đúng điều khách vừa hỏi/kể.
  2. dung_buoc  — câu trả lời đưa khách tới bước kế (chọn xe → chi phí →
                  lái thử), không kéo lùi, không lặp vô ích.
  3. dung_giong — xưng em/gọi anh chị, không lộ mã máy, không khen vô căn cứ,
                  không từ chối oan.
  4. so_lieu    — LLM KHÔNG phán số đúng/sai (nó không có catalog): nó chỉ
                  LIỆT KÊ các con số bot nêu để người đối chiếu. Cột này trong
                  báo cáo là "cần đối chiếu", không phải điểm.

Con số in ra chỉ đáng tin sau khi người soát tối thiểu 20% file chi tiết —
LLM chấm LLM là thước đo rẻ, không phải quan toà.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

JUDGE_MODEL = os.environ.get("RUBRIC_JUDGE_MODEL", "gpt-4o")

_PROMPT = """Bạn là giám khảo chấm chất lượng hội thoại của một trợ lý tư vấn xe điện VinFast (xưng "em", gọi khách "anh/chị").
Cho hội thoại dưới đây (mỗi lượt: KHACH rồi BOT). Chấm TỪNG lượt BOT theo 3 tiêu chí đúng/sai:
- dung_y: bot trả lời đúng điều khách vừa hỏi/kể (không lạc đề, không nuốt câu hỏi).
- dung_buoc: câu trả lời đưa khách tiến tới bước kế của việc mua xe (hiểu nhu cầu → gợi ý xe → chi phí → lái thử), không lặp vô ích, không kéo lùi.
- dung_giong: đúng giọng em/anh chị, không lộ mã máy hay chữ hệ thống, không khen vô căn cứ, không từ chối oan câu hỏi hợp lệ.
Với MỖI lượt bot, liệt kê thêm "so_lieu": mảng các con số/giá/thông số bot nêu (chuỗi ngắn), để người đối chiếu catalog — bạn KHÔNG được phán số đúng hay sai.
Trả về DUY NHẤT một JSON: {"luot": [{"stt": <số thứ tự lượt bot, từ 1>, "dung_y": true/false, "dung_buoc": true/false, "dung_giong": true/false, "so_lieu": [...], "ghi_chu": "<1 câu, chỉ khi có tiêu chí false>"}]}
"""


def conversations_from_transcripts(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    conversations = []
    for result in data["results"]:
        turns = [
            {"user": t["user"], "assistant": t["assistant"]}
            for t in result["transcript"]
            if "user" in t
        ]
        conversations.append({"id": result["id"], "muc_tieu": result.get("muc_tieu", ""), "turns": turns})
    return conversations


async def conversations_from_db(days: int, limit: int) -> list[dict]:
    """Phiên thật gần nhất: gom conversation_messages theo session, mới trước."""

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get("AGENT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Thiếu AGENT_DATABASE_URL/DATABASE_URL — chạy trong container backend.")
    engine = create_async_engine(url)
    async with engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT session_id, role, content, created_at FROM conversation_messages "
                    "WHERE session_id IN (SELECT session_id FROM conversation_messages "
                    "  WHERE created_at > now() - (:days || ' days')::interval "
                    "  GROUP BY session_id ORDER BY max(created_at) DESC LIMIT :limit) "
                    "ORDER BY session_id, created_at"
                ),
                {"days": days, "limit": limit},
            )
        ).all()
    await engine.dispose()

    grouped: dict[str, list] = {}
    for session_id, role, content, _created in rows:
        grouped.setdefault(str(session_id), []).append((role, content))
    conversations = []
    for session_id, messages in grouped.items():
        turns = []
        pending_user: str | None = None
        for role, content in messages:
            if role == "USER":
                pending_user = content
            elif role == "ASSISTANT" and pending_user is not None:
                turns.append({"user": pending_user, "assistant": content})
                pending_user = None
        if turns:
            conversations.append({"id": session_id[:8], "muc_tieu": "", "turns": turns})
    return conversations


def judge_one(client, conversation: dict) -> list[dict]:
    lines = []
    for turn in conversation["turns"]:
        lines.append(f"KHACH: {turn['user']}")
        lines.append(f"BOT: {turn['assistant']}")
    response = client.chat.completions.create(
        model=JUDGE_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _PROMPT},
            {"role": "user", "content": "\n".join(lines)},
        ],
    )
    payload = json.loads(response.choices[0].message.content or "{}")
    return payload.get("luot", [])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcripts")
    parser.add_argument("--from-db", action="store_true")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", default="eval/blind/rubric")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("Thiếu OPENAI_API_KEY.")
    if args.transcripts:
        conversations = conversations_from_transcripts(args.transcripts)
    elif args.from_db:
        conversations = asyncio.run(conversations_from_db(args.days, args.limit))
    else:
        raise SystemExit("Cần --transcripts <file> hoặc --from-db.")

    from openai import OpenAI

    client = OpenAI()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    totals = {"dung_y": [0, 0], "dung_buoc": [0, 0], "dung_giong": [0, 0]}
    need_check = 0
    details = []
    for index, conversation in enumerate(conversations, start=1):
        print(f"[{index}/{len(conversations)}] {conversation['id']} ...", flush=True)
        try:
            verdicts = judge_one(client, conversation)
        except Exception as error:  # noqa: BLE001 — một phiên chấm hỏng không được giết cả run
            details.append({"id": conversation["id"], "error": str(error)})
            continue
        for verdict, turn in zip(verdicts, conversation["turns"], strict=False):
            for key in totals:
                totals[key][1] += 1
                if verdict.get(key):
                    totals[key][0] += 1
            need_check += len(verdict.get("so_lieu") or [])
            details.append({"id": conversation["id"], "user": turn["user"], "bot": turn["assistant"], **verdict})

    (out_dir / "chi_tiet.jsonl").write_text(
        "\n".join(json.dumps(d, ensure_ascii=False) for d in details), encoding="utf-8"
    )
    lines = [f"# Rubric run {stamp} — {len(conversations)} hội thoại", ""]
    for key, (ok, total) in totals.items():
        pct = f"{ok}/{total} = {ok * 100 // total}%" if total else "0/0"
        lines.append(f"- **{key}**: {pct}")
    lines.append(f"- **so_lieu cần người đối chiếu**: {need_check} con số (xem chi_tiet.jsonl)")
    lines.append("")
    lines.append("> LLM chấm LLM là thước rẻ — soát tay tối thiểu 20% chi_tiet.jsonl trước khi tin.")
    report = "\n".join(lines)
    (out_dir / "bao_cao.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nChi tiết: {out_dir}/chi_tiet.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
