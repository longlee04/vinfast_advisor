"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchTurnTraceStats, fetchTurnTraces, type TurnTrace, type TurnTraceStats } from "@/lib/api/agent";

const WINDOWS: ReadonlyArray<{ readonly label: string; readonly hours: number }> = [
  { label: "1 giờ", hours: 1 },
  { label: "24 giờ", hours: 24 },
  { label: "7 ngày", hours: 24 * 7 },
  { label: "30 ngày", hours: 24 * 30 },
];

/**
 * Ngưỡng độ phủ để tô cảnh báo.
 *
 * Đo trên prod 2026-08-26: 26/27 lượt `intent=None`, tức độ phủ ~4%. Dưới mức
 * này thì việc phải làm là mở rộng `entity_catalog`, KHÔNG phải chỉnh
 * `NLU_AUTO_THRESHOLD` — nên màn hình phải nói thẳng ra điều đó thay vì để người
 * đọc tự suy từ một con số trần.
 */
const HEALTHY_COVERAGE_PCT = 30;

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }).format(date);
}

function Histogram({ histogram }: Readonly<{ histogram: Record<string, number> }>): React.JSX.Element {
  const entries = Object.entries(histogram);
  const peak = Math.max(1, ...entries.map(([, count]) => count));
  return (
    <div className="trace-histogram">
      {entries.map(([bucket, count]) => (
        <div className="trace-histogram-col" key={bucket}>
          <span className="trace-histogram-count">{count}</span>
          <div className="trace-histogram-bar" style={{ height: `${Math.round((count / peak) * 100)}%` }} />
          <span className="trace-histogram-label">{bucket}</span>
        </div>
      ))}
    </div>
  );
}

function ReasonTrail({ trace }: Readonly<{ trace: TurnTrace }>): React.JSX.Element {
  const nlu = trace.payload?.nlu ?? {};
  const llm = trace.payload?.llm ?? {};
  const gates = trace.payload?.gates ?? {};
  const outcome = trace.payload?.outcome ?? {};
  const activeGates = Object.entries(gates).filter(([, on]) => on);
  // [Tool-calling] Vệt LLM gọi tool trong lượt (`tinh_chi_phi`, `tim_diem_dich_vu`).
  // Ba tầng known/returned/used là để đọc được QUÁ TRÌNH: hệ đã biết gì, LLM
  // trả gì, và sau lớp kiểm thì cái gì được dùng thật (Sếp 2026-08-31).
  const toolCalls: ReadonlyArray<{ tool: string; known: unknown; returned: unknown; used: unknown }> =
    Array.isArray(trace.payload?.tool_calls) ? trace.payload.tool_calls : [];
  // `payload` là JSON tự do từ backend nên phải tự chốt hình dạng ở biên này.
  const candidates: ReadonlyArray<{ intent: string; score: number }> = Array.isArray(nlu.candidates) ? nlu.candidates : [];
  const entities: ReadonlyArray<{ category: string; canonical: string; score: number; matched_on: string; is_weak?: boolean }> =
    Array.isArray(nlu.entities) ? nlu.entities : [];
  const toolSection = (
        <section>
          <h4>Tool đã gọi</h4>
          {toolCalls.length > 0 ? (
            <ul className="trace-list">
              {toolCalls.map((call, index) => (
                <li key={`${String(call.tool)}-${index}`}>
                  <strong><code>{String(call.tool)}</code></strong>
                  <br />Đã biết: <code>{JSON.stringify(call.known)}</code>
                  <br />LLM trả: <code>{JSON.stringify(call.returned)}</code>
                  <br />Được dùng: <code>{JSON.stringify(call.used)}</code>
                </li>
              ))}
            </ul>
          ) : (
            <p className="trace-empty">Lượt này không gọi tool nào.</p>
          )}
        </section>
  );
  // Vệt lõi v2 ghi payload theo hình KHÁC hẳn lõi cũ (`core: "v2"`, xem
  // `run_turn.trace_payload`): understanding/stage/action thay cho nlu/llm/
  // gates/outcome. Trước đây panel chỉ biết hình cũ nên lượt v2 vẽ toàn "—"
  // — Sếp tưởng màn hỏng (2026-08-31). Rẽ nhánh theo `core`, không đoán.
  if (trace.payload?.core === "v2") {
    const understanding = (trace.payload.understanding ?? {}) as Record<string, unknown>;
    const slots = (trace.payload.validated_slots ?? {}) as Record<string, unknown>;
    const pending = trace.payload.pending_after as { kind?: string; key?: string; asked_at_turn?: number } | null;
    const askCounts = (trace.payload.ask_counts ?? {}) as Record<string, number>;
    return (
      <div className="trace-detail">
        <section>
          <h4>Lõi v2 · máy hiểu gì</h4>
          <ul className="trace-list">
            <li>Kiểu lượt: <strong>{String(understanding.dialogue_act ?? "—")}</strong></li>
            <li>Ý định: <strong>{String(understanding.intent ?? "—")}</strong> — tin cậy {Number(understanding.confidence ?? 0).toFixed(2)}</li>
            <li>Slot chốt được: {Object.keys(slots).length > 0 ? <code>{JSON.stringify(slots)}</code> : "—"}</li>
            {understanding.question ? <li>Câu hỏi khách: “{String(understanding.question)}”</li> : null}
          </ul>
          {trace.payload.understand_error ? (
            <p className="trace-note">LLM hiểu ý lỗi: <code>{String(trace.payload.understand_error)}</code> — lượt chạy tiếp bằng đường tất định.</p>
          ) : null}
          {trace.payload.understand_skipped ? (
            <p className="trace-note">Bỏ qua bước hiểu ý: <code>{String(trace.payload.understand_skipped)}</code></p>
          ) : null}
        </section>
        <section>
          <h4>Hành trình trạng thái</h4>
          <ul className="trace-list">
            <li>Giai đoạn: <strong>{String(trace.payload.stage_before ?? "?")}</strong> → <strong>{String(trace.payload.stage_after ?? "?")}</strong></li>
            <li>Việc đã làm: <code>{String(trace.payload.action ?? "—")}</code>{trace.payload.resume_pending ? " (quay lại câu đang treo)" : ""}</li>
            <li>
              Cuối lượt còn treo câu hỏi:{" "}
              {pending ? <code>{`${String(pending.kind ?? "?")} · ${String(pending.key ?? "?")} (hỏi ở lượt ${String(pending.asked_at_turn ?? "?")})`}</code> : "không"}
            </li>
            {Object.keys(askCounts).length > 0 ? <li>Số lần đã hỏi: <code>{JSON.stringify(askCounts)}</code></li> : null}
          </ul>
        </section>
        {toolSection}
        <section>
          <h4>Kết cục</h4>
          <ul className="trace-list">
            <li>Lý do dừng: {String(trace.terminal_reason ?? "chạy trọn lượt")}</li>
          </ul>
        </section>
      </div>
    );
  }
  return (
    <div className="trace-detail">
      <section>
        <h4>Lớp 1–4 · máy chấm điểm thế nào</h4>
        {nlu.rewrite_text && nlu.rewrite_text !== trace.user_message ? (
          <p className="trace-note">Câu dùng để khớp: <code>{String(nlu.rewrite_text)}</code> (tin cậy {String(nlu.rewrite_trust ?? "?")})</p>
        ) : null}
        {candidates.length > 0 ? (
          <ul className="trace-list">
            {candidates.map((item) => (
              <li key={String(item.intent)}><strong>{String(item.intent)}</strong> — điểm {Number(item.score).toFixed(2)}</li>
            ))}
          </ul>
        ) : (
          <p className="trace-empty">Không ý định nào đủ căn cứ. Đây là lý do lượt đi thẳng, không phải vì ngưỡng.</p>
        )}
        {entities.length > 0 ? (
          <ul className="trace-list">
            {entities.map((item, index) => (
              <li key={`${String(item.canonical)}-${index}`}>
                {String(item.category)} · <strong>{String(item.canonical)}</strong> — khớp {Number(item.score).toFixed(0)}
                {item.is_weak ? " (yếu)" : ""} · từ {String(item.matched_on)}
              </li>
            ))}
          </ul>
        ) : (
          <p className="trace-empty">Không khớp được entity nào trong danh mục.</p>
        )}
      </section>
      <section>
        <h4>LLM gắn nhãn gì</h4>
        <ul className="trace-list">
          <li>Phạm vi: <strong>{String(llm.scope_label ?? "—")}</strong></li>
          <li>Ý định: {(llm.intents as string[] | undefined)?.join(", ") || "—"}</li>
          <li>Slot thu được lượt này: {Object.keys((llm.slots_gained as object) ?? {}).length > 0 ? JSON.stringify(llm.slots_gained) : "—"}</li>
        </ul>
      </section>
      <section>
        <h4>Cửa tất định đã bật</h4>
        {activeGates.length > 0 ? (
          <ul className="trace-list">{activeGates.map(([name]) => <li key={name}><code>{name}</code></li>)}</ul>
        ) : (
          <p className="trace-empty">Không cửa nào — lượt chạy theo nhãn LLM.</p>
        )}
      </section>
      {toolSection}
      <section>
        <h4>Kết cục</h4>
        <ul className="trace-list">
          <li>Lý do dừng: {String(outcome.terminal_reason ?? "—")}</li>
          <li>Số xe đề xuất: {Number(outcome.recommendation_count ?? 0)}</li>
          <li>Chờ duyệt: {outcome.awaiting_review ? "có" : "không"}</li>
          {outcome.answer_preview ? <li className="trace-preview">“{String(outcome.answer_preview)}”</li> : null}
        </ul>
      </section>
    </div>
  );
}

export function TurnTracePanel(): React.JSX.Element {
  const [hours, setHours] = useState(24);
  const [stats, setStats] = useState<TurnTraceStats | null>(null);
  const [items, setItems] = useState<readonly TurnTrace[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextStats, nextItems] = await Promise.all([fetchTurnTraceStats(hours), fetchTurnTraces({ hours, limit: 50 })]);
      setStats(nextStats);
      setItems(nextItems.items);
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [hours]);

  useEffect(() => {
    void load();
  }, [load]);

  const coverageLow = stats !== null && stats.total > 0 && stats.coverage_pct < HEALTHY_COVERAGE_PCT;

  return (
    <div className="trace-panel">
      <div className="trace-toolbar">
        {WINDOWS.map((option) => (
          <button
            className={`trace-window ${option.hours === hours ? "is-active" : ""}`}
            key={option.hours}
            onClick={() => setHours(option.hours)}
            type="button"
          >
            {option.label}
          </button>
        ))}
        <button className="trace-window" onClick={() => void load()} type="button">Tải lại</button>
      </div>

      {loading ? <p className="trace-empty">Đang tải…</p> : null}
      {!loading && error ? <p className="trace-empty">Không tải được dữ liệu.</p> : null}

      {!loading && !error && stats !== null ? (
        <>
          <div className="trace-kpis">
            <div className={`trace-kpi ${coverageLow ? "is-warning" : ""}`}>
              <span className="trace-kpi-value">{stats.coverage_pct}%</span>
              <span className="trace-kpi-label">lượt máy nhận ra được ý định</span>
            </div>
            <div className="trace-kpi">
              <span className="trace-kpi-value">{stats.total}</span>
              <span className="trace-kpi-label">tổng số lượt</span>
            </div>
            {Object.entries(stats.tier_counts).map(([tier, count]) => (
              <div className="trace-kpi" key={tier}>
                <span className="trace-kpi-value">{count}</span>
                <span className="trace-kpi-label">mức {tier}</span>
              </div>
            ))}
          </div>

          {coverageLow ? (
            <p className="trace-warning">
              Độ phủ dưới {HEALTHY_COVERAGE_PCT}%: phần lớn lượt máy <strong>không nhận ra ý định nào</strong>, nên
              chỉnh ngưỡng tin cậy sẽ không đổi được gì. Việc cần làm là mở rộng danh mục entity để Lớp 2 nhận ra
              nhiều hơn.
            </p>
          ) : null}

          <h3 className="trace-section-title">Phân bố độ tin cậy</h3>
          <Histogram histogram={stats.histogram} />

          <h3 className="trace-section-title">Lượt gần đây — bấm để xem vì sao</h3>
          <div className="trace-rows">
            {items.length === 0 ? <p className="trace-empty">Chưa có lượt nào trong khung thời gian này.</p> : null}
            {items.map((trace) => {
              const open = openId === trace.trace_id;
              return (
                <div className={`trace-row ${open ? "is-open" : ""}`} key={trace.trace_id}>
                  <button className="trace-row-head" onClick={() => setOpenId(open ? null : trace.trace_id)} type="button">
                    {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                    <span className="trace-row-time">{formatTime(trace.created_at)}</span>
                    <span className="trace-row-message">{trace.user_message || "(rỗng)"}</span>
                    <span className="trace-row-intent">{trace.intent_hint ?? "không rõ ý định"}</span>
                    <span className="trace-row-score">{trace.confidence === null ? "—" : trace.confidence.toFixed(2)}</span>
                    <span className={`trace-row-tier tier-${(trace.tier ?? "none").toLowerCase()}`}>{trace.tier ?? "—"}</span>
                  </button>
                  {open ? <ReasonTrail trace={trace} /> : null}
                </div>
              );
            })}
          </div>
        </>
      ) : null}
    </div>
  );
}
