"""Đo 6 chỉ số của lõi hội thoại v2 (spec 2026-08-29 mục 8), tách theo lõi.

Cách đo bám đúng phép đo đã dựng số nền 25–29/08/2026 trên `turn_traces` +
`conversation_messages`, để số mới so được với số cũ. Số nền:
    1) 175/188 = 93%   2) 36 lượt   3) 27 lượt   4) 80 câu   5) 21 lượt

Chạy trong container backend trên prod (`./scripts` được bind-mount):
    docker compose -f /root/p150-prod-src/docker-compose.yml exec -T backend \
        python -m scripts.core_v2_metrics --days 3 --core both

Script CHỈ ĐỌC. Không INSERT/UPDATE/DELETE bảng nào.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# --- luật đếm (bám đúng phép đo đã dựng số nền) ---------------------------------

#: Lượt khách CHỈ trả lời loại xe. Có/không dấu, có/không "điện", cho phép chấm cuối.
RE_VEHICLE_TYPE_ONLY = re.compile(
    r"^(ô tô( điện)?|o to( dien)?|xe máy( điện)?|xe may( dien)?)\.?$",
    re.IGNORECASE,
)
#: Câu mở đầu bài đổ catalog 7 dòng.
CATALOG_DUMP_MARKER = "dải sản phẩm"
#: Khách "chọn/xem/so sánh/tư vấn" là CHOICE — không tính vào chỉ số 3.
RE_CHOICE_WORDS = re.compile(r"chọn|xem|so sánh|tư vấn", re.IGNORECASE)
#: Bài đề xuất luôn mở bằng tên xe in đậm.
PITCH_PREFIXES = ("**VinFast", "(thấp hơn ngân sách) **VinFast")
#: Ba biến thể câu từ chối trong `src/agents/prompts/reply_variants.py`.
REFUSAL_MARKERS = ("Dạ em không trả lời được", "ngoài phần em", "em đành chịu")
#: Câu từ chối luôn nằm ở MỞ ĐẦU. Chỉ soi 160 ký tự đầu để một bài dài vô tình
#: chứa cụm "ngoài phần em" ở cuối không bị đếm nhầm.
REFUSAL_WINDOW = 160
#: Enum thô, số `.00` có đơn vị, dấu trích `[n]`.
RE_RAW_LEAK = re.compile(r"\b[A-Z0-9]+_[A-Z0-9_]+\b|\d+\.00 (lít|km)|\[\d+\]")
#: Chặng "sau đề xuất" của lõi v2 (v1 dùng cờ gate `in_post_pitch_stage`).
POST_PITCH_STAGES = frozenset({"RECOMMENDED", "CHOSEN"})
#: `conversation_messages` và `turn_traces` ghi trong CÙNG transaction — tin nhắn
#: ASSISTANT có thể được flush sớm hơn trace vài chục ms (đo thực tế trên prod:
#: tin 14:05:00.465, trace 14:05:00.487, lệch ~22ms). Lùi biên dưới cửa sổ tìm
#: câu trả lời 5 giây để chỉ số 5 không đếm nhầm các lượt này là "câm".
ANSWER_LOOKBACK = timedelta(seconds=5)


def _in_answer_window(
    message_created_at: datetime,
    trace_created_at: datetime,
    next_trace_created_at: datetime | None,
) -> bool:
    """Tin nhắn ASSISTANT có thuộc cửa sổ trả lời của lượt này không.

    Biên dưới lùi `ANSWER_LOOKBACK` so với `trace_created_at` (bù độ trễ ghi
    trong cùng transaction). Biên trên vẫn chặn ở `next_trace_created_at`
    (LEAD) như cũ để không mượn nhầm câu của lượt sau.
    """

    lower = trace_created_at - ANSWER_LOOKBACK
    if message_created_at < lower:
        return False
    return next_trace_created_at is None or message_created_at < next_trace_created_at


@dataclass(frozen=True)
class Metric:
    number: int
    name: str
    hit: int
    total: int
    baseline: str
    target: str
    #: True khi số đo đạt ngưỡng spec mục 8.
    passed: bool

    @property
    def percent(self) -> float:
        return 0.0 if self.total == 0 else 100.0 * self.hit / self.total

    def cell(self) -> str:
        if self.total == 0:
            return "—"
        return f"{self.hit}/{self.total} = {self.percent:.0f}%"


def _under_5_percent(hit: int, total: int) -> bool:
    """Chưa có lượt nào thì CHƯA đạt — không lấy mẫu rỗng làm bằng chứng thắng."""

    return total > 0 and (100.0 * hit / total) < 5.0


def _answer(row: dict[str, Any]) -> str:
    return (row.get("bot_answer") or "").strip()


def core_of(row: dict[str, Any]) -> str:
    """Lượt thuộc lõi nào — khoá `core` trong payload là nguồn sự thật duy nhất."""

    return "v2" if (row.get("payload") or {}).get("core") == "v2" else "v1"


def split_by_core(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"v1": [], "v2": []}
    for row in rows:
        out[core_of(row)].append(row)
    return out


def _prev_turn_asked(row: dict[str, Any]) -> bool:
    """Lượt TRƯỚC bot có treo câu hỏi không — hai lõi ghi hai chỗ khác nhau."""

    prev = row.get("prev_payload")
    if not prev:
        return False
    if prev.get("core") == "v2":
        return prev.get("pending_after") is not None
    return bool((prev.get("outcome") or {}).get("has_pending_question"))


def _in_post_pitch(row: dict[str, Any]) -> bool:
    payload = row.get("payload") or {}
    if payload.get("core") == "v2":
        return payload.get("stage_before") in POST_PITCH_STAGES
    return bool((payload.get("gates") or {}).get("in_post_pitch_stage"))


def _dropped_intake_after_catalog(row: dict[str, Any]) -> bool:
    """Sau khi đổ catalog, bot có MẤT luôn ý định hỏi tiếp không.

    Chủ đích mới (quyết định của chủ sản phẩm): đổ catalog + hỏi tiếp một câu
    hồ sơ TRONG CÙNG một tin nhắn là ĐÚNG (không phải lỗi) — chỉ tính là lỗi
    khi bot đổ catalog mà KHÔNG treo câu hỏi tiếp, tức mất luôn ý định thu thập.
    Đọc payload của CHÍNH lượt này (không phải lượt trước như `_prev_turn_asked`).
    """

    payload = row.get("payload") or {}
    if payload.get("core") == "v2":
        return payload.get("pending_after") is None
    return not bool((payload.get("outcome") or {}).get("has_pending_question"))


def metric_1(rows: list[dict[str, Any]]) -> Metric:
    """Khách trả lời loại xe → bot đổ catalog mà KHÔNG hỏi tiếp (mất ý định)."""

    scope = [r for r in rows if RE_VEHICLE_TYPE_ONLY.match((r.get("user_message") or "").strip())]
    hit = sum(1 for r in scope if CATALOG_DUMP_MARKER in _answer(r).casefold() and _dropped_intake_after_catalog(r))
    return Metric(
        number=1,
        name="trả lời loại xe → đổ catalog mà KHÔNG hỏi tiếp",
        hit=hit,
        total=len(scope),
        baseline="175/188 = 93%",
        target="< 5%",
        passed=_under_5_percent(hit, len(scope)),
    )


def metric_2(rows: list[dict[str, Any]]) -> Metric:
    """Bot vừa hỏi xong, khách đáp, bot lại từ chối / gắn OUT_OF_SCOPE."""

    scope = [r for r in rows if _prev_turn_asked(r)]
    hit = 0
    for r in scope:
        head = _answer(r)[:REFUSAL_WINDOW]
        if r.get("scope_label") == "OUT_OF_SCOPE" or any(mark in head for mark in REFUSAL_MARKERS):
            hit += 1
    return Metric(
        number=2,
        name="ngay sau câu bot hỏi mà bot từ chối / OUT_OF_SCOPE",
        hit=hit,
        total=len(scope),
        baseline="36 lượt",
        target="< 5%",
        passed=_under_5_percent(hit, len(scope)),
    )


def metric_3(rows: list[dict[str, Any]]) -> Metric:
    """Sau đề xuất, khách hỏi thêm (không phải chọn) mà bot đọc lại nguyên bài."""

    scope = [r for r in rows if _in_post_pitch(r) and not RE_CHOICE_WORDS.search(r.get("user_message") or "")]
    hit = sum(1 for r in scope if _answer(r).startswith(PITCH_PREFIXES))
    return Metric(
        number=3,
        name="sau đề xuất, khách hỏi thêm mà bot lặp bài đề xuất",
        hit=hit,
        total=len(scope),
        baseline="27 lượt",
        target="< 5%",
        passed=_under_5_percent(hit, len(scope)),
    )


def metric_4(rows: list[dict[str, Any]]) -> Metric:
    """Câu trả lời lộ enum thô / số `.00` / dấu trích `[n]`."""

    scope = [r for r in rows if _answer(r)]
    hit = sum(1 for r in scope if RE_RAW_LEAK.search(_answer(r)))
    return Metric(
        number=4,
        name="câu lộ enum / số thô / [n]",
        hit=hit,
        total=len(scope),
        baseline="80 câu",
        target="0",
        #: Rỗng thì CHƯA đạt — mẫu rỗng không phải bằng chứng thắng.
        passed=len(scope) > 0 and hit == 0,
    )


def metric_5(rows: list[dict[str, Any]]) -> Metric:
    """Lượt có trace nhưng khách không nhận được tin nhắn nào."""

    # LOẠI TRỪ lượt `Silent` khi TVV đang cầm phiên (understand_skipped=handed_off):
    # bot im ở đó là ĐÚNG LUẬT HITL, không phải lỗi. Trước 31/08 metric đếm oan
    # đúng nhóm này (7/7 lượt 'câm' soi tay đều là Silent handed_off) → ❌ giả.
    rows = [
        r for r in rows
        if not ((r.get("payload") or {}).get("action") == "Silent"
                and (r.get("payload") or {}).get("understand_skipped") == "handed_off")
    ]
    hit = sum(1 for r in rows if not _answer(r))
    return Metric(
        number=5,
        name="lượt không có tin nhắn bot",
        hit=hit,
        total=len(rows),
        baseline="21 lượt",
        target="0",
        #: Rỗng thì CHƯA đạt — mẫu rỗng không phải bằng chứng thắng.
        passed=len(rows) > 0 and hit == 0,
    )


def metric_6(v1_report: dict[str, Any] | None, v2_report: dict[str, Any] | None) -> Metric:
    """`scripts/live_probe_eval.py` — v2 không được tụt so với v1.

    Đọc hai file JSON do live_probe_eval ghi ra. Thiếu file thì KHÔNG kết luận
    (`passed=False`) — không có bằng chứng thì không tính là đạt.
    """

    if not v1_report or not v2_report:
        return Metric(6, "live_probe_eval", 0, 0, "—", "không tụt", False)
    v1_pass = int(v1_report.get("turn_pass") or 0)
    v1_total = int(v1_report.get("turn_count") or 0)
    v2_pass = int(v2_report.get("turn_pass") or 0)
    v2_total = int(v2_report.get("turn_count") or 0)
    v1_rate = 0.0 if v1_total == 0 else v1_pass / v1_total
    v2_rate = 0.0 if v2_total == 0 else v2_pass / v2_total
    return Metric(
        number=6,
        name=f"live_probe_eval (v1 {v1_pass}/{v1_total})",
        hit=v2_pass,
        total=v2_total,
        baseline=f"{v1_rate * 100:.0f}%",
        target="không tụt",
        passed=v2_rate >= v1_rate,
    )


def all_metrics(
    rows: list[dict[str, Any]],
    v1_report: dict[str, Any] | None,
    v2_report: dict[str, Any] | None,
) -> list[Metric]:
    return [
        metric_1(rows),
        metric_2(rows),
        metric_3(rows),
        metric_4(rows),
        metric_5(rows),
        metric_6(v1_report, v2_report),
    ]


def render_table(by_core: dict[str, list[Metric]]) -> str:
    cores = [c for c in ("v1", "v2") if c in by_core]
    header = "| # | Chỉ số | " + " | ".join(cores) + " | Nền 25–29/08 | Mục tiêu | Đạt |"
    sep = "|---|---|" + "---|" * len(cores) + "---|---|---|"
    lines = [header, sep]
    for index in range(6):
        first = by_core[cores[0]][index]
        cells = " | ".join(by_core[core][index].cell() for core in cores)
        judge = by_core[cores[-1]][index]
        #: Không có lượt nào thì không có gì để chấm — không mặc định ✅.
        verdict = "—" if judge.total == 0 else ("✅" if judge.passed else "❌")
        lines.append(f"| {first.number} | {first.name} | {cells} | {first.baseline} | {first.target} | {verdict} |")
    return "\n".join(lines)


# --- SQL + CLI (điểm duy nhất chạm Postgres) -------------------------------------

#: MỘT chỗ duy nhất có SQL. Mọi luật đếm ở trên là hàm thuần.
#:
#: - `LAG(payload)` cho biết lượt TRƯỚC cùng phiên đã treo câu hỏi chưa (chỉ số 2).
#: - Cửa sổ tìm câu trả lời khớp đúng luật thuần `_in_answer_window` ở trên:
#:   biên dưới lùi 5 giây so với `created_at` của chính trace này —
#:   `conversation_messages` và `turn_traces` ghi cùng transaction nhưng tin
#:   nhắn có thể được flush trước trace vài chục ms (đo thực tế trên prod lệch
#:   ~22ms), không lùi 5 giây thì chỉ số 5 đếm nhầm các lượt này là "câm". Biên
#:   trên vẫn chặn ở trace kế tiếp (`LEAD(created_at)`) để không mượn nhầm câu
#:   của lượt sau.
#: - QUAN TRỌNG: đối chiếu dữ liệu thật thì các lượt trong một phiên thường
#:   cách nhau CHỈ 1–3 giây (không phải hàng chục giây), nên nếu chọn tin
#:   ASSISTANT sớm nhất trong cửa sổ 5 giây (`ORDER BY cm.created_at`), rất hay
#:   vớ nhầm câu trả lời của LƯỢT TRƯỚC (vẫn nằm trong 5 giây lùi lại). Vì vậy
#:   sắp theo khoảng cách thời gian TUYỆT ĐỐI gần `t.created_at` nhất trước —
#:   câu trả lời thật của lượt này luôn lệch vài chục ms, gần hơn nhiều so với
#:   câu của lượt trước (thường lệch hàng giây).
SQL = """
WITH t AS (
    SELECT
        tr.trace_id,
        tr.session_id,
        tr.created_at,
        tr.user_message,
        tr.scope_label,
        tr.terminal_reason,
        tr.payload::text AS payload_json,
        LAG(tr.payload::text) OVER (PARTITION BY tr.session_id ORDER BY tr.created_at) AS prev_payload_json,
        LEAD(tr.created_at) OVER (PARTITION BY tr.session_id ORDER BY tr.created_at) AS next_created_at
    FROM turn_traces tr
    WHERE tr.created_at >= now() - make_interval(days => :days)
)
SELECT
    t.session_id,
    t.created_at,
    t.user_message,
    t.scope_label,
    t.terminal_reason,
    t.payload_json,
    t.prev_payload_json,
    (
        SELECT cm.content
        FROM conversation_messages cm
        WHERE cm.session_id = t.session_id
          AND cm.role = 'ASSISTANT'
          AND cm.created_at >= t.created_at - interval '5 seconds'
          AND (t.next_created_at IS NULL OR cm.created_at < t.next_created_at)
        ORDER BY abs(extract(epoch FROM (cm.created_at - t.created_at))), cm.turn_index
        LIMIT 1
    ) AS bot_answer
FROM t
ORDER BY t.session_id, t.created_at
"""


async def fetch_rows(dsn: str, days: int) -> list[dict[str, Any]]:
    """Đọc DB — hàm DUY NHẤT trong file này chạm Postgres."""

    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            records = (await conn.execute(text(SQL), {"days": days})).mappings().all()
    finally:
        await engine.dispose()
    return [
        {
            "session_id": str(r["session_id"]),
            "created_at": r["created_at"],
            "user_message": r["user_message"] or "",
            "scope_label": r["scope_label"],
            "terminal_reason": r["terminal_reason"],
            "payload": json.loads(r["payload_json"] or "{}"),
            "prev_payload": json.loads(r["prev_payload_json"]) if r["prev_payload_json"] else None,
            "bot_answer": r["bot_answer"],
        }
        for r in records
    ]


# --------------------------------------------------------------- KPI theo ĐÍCH (đợt 9)
#
# Sáu chỉ số trên đo "bot hiểu đúng không"; KPI theo đích đo "phiên có ĐI TỚI ĐÂU
# không": chọn xe → đặt lái thử, và bao nhiêu phiên rơi sang người. Chỉ tính phiên
# lõi v2 (có ít nhất một vệt `payload.core = 'v2'` trong cửa sổ ngày).
#
# "Có booking" ghép theo KHÁCH + thời điểm (`test_drive_bookings.customer_id`
# = `conversation_sessions.customer_id` và `created_at` >= lúc mở phiên), vì
# bảng booking không có `session_id` và lõi v2 đặt lịch không gắn `run_id`.
# "Rơi vào TVV" = `ownership` khác AI (PENDING_HANDOFF/HUMAN) HOẶC có vệt
# `action = 'Handoff'` — ownership có thể đã được TVV trả lại AI sau đó, vệt thì
# không mất.

#: Chặng "đã chọn xe" — đọc `stage_after` của vệt v2.
CHOSEN_STAGES = frozenset({"CHOSEN", "COSTING", "SCHEDULING", "OFFER_REVIEW"})

GOAL_SQL = """
WITH v2 AS (
    SELECT DISTINCT tr.session_id
    FROM turn_traces tr
    WHERE tr.created_at >= now() - make_interval(days => :days)
      AND tr.payload->>'core' = 'v2'
)
SELECT
    s.session_id,
    s.ownership,
    cs.chosen_vehicle_id,
    EXISTS (
        SELECT 1 FROM test_drive_bookings b
        WHERE b.customer_id = s.customer_id AND b.created_at >= s.started_at
    ) AS has_booking,
    (
        SELECT jsonb_agg(
            jsonb_build_object('action', t.payload->>'action', 'stage_after', t.payload->>'stage_after')
            ORDER BY t.created_at
        )
        FROM turn_traces t WHERE t.session_id = s.session_id
    ) AS turns
FROM conversation_sessions s
JOIN v2 ON v2.session_id = s.session_id
LEFT JOIN conversation_core_state cs ON cs.session_id = s.session_id
ORDER BY s.started_at
"""


async def fetch_goal_sessions(dsn: str, days: int) -> list[dict[str, Any]]:
    """Một hàng/phiên v2 cho KPI theo đích. Chỉ đọc."""

    engine = create_async_engine(dsn)
    try:
        async with engine.connect() as conn:
            records = (await conn.execute(text(GOAL_SQL), {"days": days})).mappings().all()
    finally:
        await engine.dispose()
    sessions = []
    for r in records:
        turns = r["turns"]
        if isinstance(turns, str):
            turns = json.loads(turns)
        sessions.append(
            {
                "session_id": str(r["session_id"]),
                "ownership": r["ownership"] or "AI",
                "chosen_vehicle_id": str(r["chosen_vehicle_id"]) if r["chosen_vehicle_id"] else None,
                "has_booking": bool(r["has_booking"]),
                "turns": list(turns or []),
            }
        )
    return sessions


def turns_to_first_choice(turns: list[dict[str, Any]]) -> int | None:
    """Số lượt (1-based) tới lượt ĐẦU TIÊN chặng sau vào nhóm đã chọn xe; `None` nếu chưa từng."""

    for index, turn in enumerate(turns, start=1):
        if (turn.get("stage_after") or "") in CHOSEN_STAGES:
            return index
    return None


def session_handed_off(session: dict[str, Any]) -> bool:
    if (session.get("ownership") or "AI") != "AI":
        return True
    return any((turn.get("action") or "") == "Handoff" for turn in session.get("turns", ()))


@dataclass(frozen=True)
class GoalKpi:
    name: str
    hit: int
    total: int
    #: Giá trị trung bình (cho "số lượt tới lần chọn xe đầu"); `None` với KPI tỷ lệ.
    average: float | None = None

    def cell(self) -> str:
        if self.total == 0:
            return "—"
        if self.average is not None:
            return f"{self.average:.1f} lượt (n={self.total})"
        return f"{self.hit}/{self.total} = {100.0 * self.hit / self.total:.0f}%"


#: [Agent] Năm chỉ số của đường agent (plan agent-migration Bước 8). Script này
#: CHỈ ĐỌC `turn_traces.payload` — không ghi gì, giữ nguyên tính chất.
def agent_kpis(rows: list[dict[str, Any]]) -> list[GoalKpi]:
    """Năm chỉ số agent từ các vệt v2 trong cửa sổ ngày.

    Lượt không đi agent thì payload không có khoá `agent_*` — mẫu số là TỔNG
    lượt v2 cho tỷ lệ "lượt đi agent", còn bốn chỉ số sau chỉ tính trên lượt
    agent (mẫu số nhỏ hơn, ghi rõ trong cột giá trị).
    """

    agent_rows = [r for r in rows if (r.get("payload") or {}).get("agent_used")]
    total_agent = len(agent_rows)

    def _payload(row: dict[str, Any]) -> dict[str, Any]:
        return row.get("payload") or {}

    answered = [r for r in agent_rows if not _payload(r).get("agent_error")]
    steps = [len(_payload(r).get("agent_steps") or []) for r in agent_rows]
    calls = [int(_payload(r).get("agent_llm_calls") or 0) for r in agent_rows]
    millis = [int(_payload(r).get("agent_ms") or 0) for r in agent_rows]
    return [
        GoalKpi("Lượt đi qua agent", total_agent, len(rows)),
        GoalKpi("Lượt agent trả lời được", len(answered), total_agent),
        GoalKpi(
            "Số lần gọi tool / lượt agent",
            len(steps),
            len(steps),
            average=(sum(steps) / len(steps)) if steps else None,
        ),
        GoalKpi(
            "Số call LLM / lượt agent",
            len(calls),
            len(calls),
            average=(sum(calls) / len(calls)) if calls else None,
        ),
        GoalKpi(
            "Thoi gian agent (ms)",
            len(millis),
            len(millis),
            average=(sum(millis) / len(millis)) if millis else None,
        ),
    ]


def agent_error_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Đếm lý do fallback của đường agent — `payload.agent_error`."""

    counts: dict[str, int] = {}
    for row in rows:
        payload = row.get("payload") or {}
        if not payload.get("agent_used"):
            continue
        reason = str(payload.get("agent_error") or "")
        counts[reason or "(tra loi duoc)"] = counts.get(reason or "(tra loi duoc)", 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def goal_kpis(sessions: list[dict[str, Any]]) -> list[GoalKpi]:
    """Bốn KPI theo đích từ danh sách phiên v2 (thuần — test được bằng dữ liệu bịa)."""

    total = len(sessions)
    chosen = [s for s in sessions if s.get("chosen_vehicle_id")]
    booked = [s for s in sessions if s.get("has_booking")]
    firsts = [n for s in sessions if (n := turns_to_first_choice(s.get("turns", []))) is not None]
    handed = [s for s in sessions if session_handed_off(s)]
    return [
        GoalKpi("Phiên có chọn xe", len(chosen), total),
        GoalKpi("Phiên có đặt lái thử", len(booked), total),
        GoalKpi(
            "Số lượt trung bình tới lần chọn xe đầu",
            len(firsts),
            len(firsts),
            average=(sum(firsts) / len(firsts)) if firsts else None,
        ),
        GoalKpi("Phiên rơi vào TVV", len(handed), total),
    ]


def render_goal_table(kpis: list[GoalKpi]) -> str:
    lines = ["| KPI theo đích (phiên v2) | Giá trị |", "|---|---|"]
    lines.extend(f"| {kpi.name} | {kpi.cell()} |" for kpi in kpis)
    return "\n".join(lines)


def _load_report(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    file = Path(path)
    if not file.is_file():
        print(f"[cảnh báo] không thấy báo cáo live_probe: {file}", file=sys.stderr)
        return None
    return json.loads(file.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Đo 6 chỉ số lõi hội thoại v2 (spec mục 8)")
    parser.add_argument("--days", type=int, default=3, help="Số ngày gần nhất lấy từ turn_traces")
    parser.add_argument("--core", choices=("v1", "v2", "both"), default="both")
    parser.add_argument("--dsn", default="", help="Mặc định đọc AGENT_DATABASE_URL")
    parser.add_argument("--probe-v1", default="", help="JSON live_probe_eval của lõi cũ")
    parser.add_argument("--probe-v2", default="", help="JSON live_probe_eval của lõi mới")
    args = parser.parse_args()

    dsn = args.dsn or os.environ.get("AGENT_DATABASE_URL", "")
    if not dsn:
        print("Thiếu DSN: truyền --dsn hoặc đặt AGENT_DATABASE_URL", file=sys.stderr)
        return 2

    try:
        rows = asyncio.run(fetch_rows(dsn, args.days))
    except Exception:  # noqa: BLE001 — chạy trên prod: in đủ traceback rồi mới thoát
        traceback.print_exc()
        return 1

    by_core_rows = split_by_core(rows)
    wanted = ["v1", "v2"] if args.core == "both" else [args.core]
    v1_report = _load_report(args.probe_v1)
    v2_report = _load_report(args.probe_v2)
    #: Cột v1 tự so v1 với v1 (luôn "không tụt") — cột v2 mới là phép so sánh
    #: thật (v2_report so với v1_report); đọc chỉ số 6 ở cột v2.
    by_core = {
        core: all_metrics(by_core_rows[core], v1_report, v2_report if core == "v2" else v1_report) for core in wanted
    }

    print(f"Lõi hội thoại v2 — 6 chỉ số (spec mục 8) · {args.days} ngày gần nhất")
    counts = " · ".join(f"{core}: {len(by_core_rows[core])} lượt" for core in wanted)
    print(f"Tổng {len(rows)} lượt — {counts}\n")
    print(render_table(by_core))
    print("\nGhi chú: cột 'Đạt' xét theo lõi cuối cùng trong bảng. Chỉ số 6 cần truyền --probe-v1/--probe-v2.")
    if "v2" in wanted:
        agent_rows = by_core_rows["v2"]
        print(f"\nChi so agent - {len(agent_rows)} luot v2 trong {args.days} ngay")
        print(render_goal_table(agent_kpis(agent_rows)))
        errors = agent_error_counts(agent_rows)
        if errors:
            print("| Ly do fallback cua agent | So luot |")
            print("|---|---|")
            for reason, count in errors.items():
                print(f"| {reason} | {count} |")
        try:
            sessions = asyncio.run(fetch_goal_sessions(dsn, args.days))
        except Exception:  # noqa: BLE001 — KPI đích hỏng không được kéo bảng 6 chỉ số đi theo
            traceback.print_exc()
            return 1
        print(f"\nKPI theo đích · {len(sessions)} phiên v2 trong {args.days} ngày")
        print(render_goal_table(goal_kpis(sessions)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
