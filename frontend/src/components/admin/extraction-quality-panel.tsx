"use client";

import { useEffect, useState } from "react";

import { HorizontalBarChart } from "@/components/admin/customer360-charts";
import { TurnTracePanel } from "@/components/admin/turn-trace-panel";
import { INSIGHT_FIELD_LABELS } from "@/components/customer360/customer360-labels";
import { type ExtractionQuality, fetchExtractionQuality } from "@/lib/api/agent";

function pct(part: number, whole: number): string {
  return whole ? `${Math.round((part / whole) * 100)}%` : "—";
}

/**
 * Tab "Chất lượng trích xuất" (plan Customer 360, Phase 6): insight bị TVV báo sai theo field,
 * và các lần gắn phiên → cơ hội bị TVV sửa (Tách/Gộp) theo người đã quyết (luật hay LLM).
 * Dùng để chỉnh prompt extractor và ngưỡng tin LLM — bằng chứng mẫu đã che liên hệ ở backend.
 */
export function ExtractionQualityPanel() {
  const [data, setData] = useState<ExtractionQuality | null>(null);
  const [error, setError] = useState(false);
  const [windowDays, setWindowDays] = useState(30);

  useEffect(() => {
    let active = true;
    fetchExtractionQuality(windowDays)
      .then((result) => {
        if (active) {
          setData(result);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [windowDays]);

  if (error) {
    return (
      <p className="inline-warning" role="alert">
        Không tải được số liệu chất lượng trích xuất.
      </p>
    );
  }
  if (!data) return null;

  const decisions = Object.entries(data.attach_by_decider);
  return (
    <section className="ops-panel c360-dashboard" aria-label="Chất lượng trích xuất">
      <div className="ops-panel-heading">
        <div>
          <h2>Chất lượng trích xuất</h2>
          <p>
            {data.insights_reported_wrong}/{data.insights_total} thông tin bị báo sai ({pct(data.insights_reported_wrong, data.insights_total)}) ·{" "}
            {Object.values(data.corrected_by_decider).reduce((sum, value) => sum + value, 0)}/{data.attach_total} lần gắn phiên bị TVV sửa
          </p>
        </div>
        <select aria-label="Khoảng thời gian" onChange={(event) => setWindowDays(Number(event.target.value))} value={windowDays}>
          <option value={7}>7 ngày</option>
          <option value={30}>30 ngày</option>
          <option value={90}>90 ngày</option>
        </select>
      </div>
      <div className="c360-dashboard-grid">
        <HorizontalBarChart
          data={data.by_field.map((row) => ({ label: INSIGHT_FIELD_LABELS[row.field] ?? row.field, value: row.wrong }))}
          emptyText="Chưa có thông tin nào bị báo sai."
          title="Thông tin bị báo sai theo loại"
        />
        <table className="chat-table">
          <caption>Gắn phiên → nhu cầu theo người quyết</caption>
          <thead>
            <tr>
              <th scope="col">Người quyết</th>
              <th scope="col">Số lần</th>
              <th scope="col">Bị TVV sửa</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length ? (
              decisions.map(([decider, total]) => (
                <tr key={decider}>
                  <td>{decider === "RULE" ? "Luật" : decider === "LLM" ? "LLM" : "Tư vấn viên"}</td>
                  <td>{total}</td>
                  <td>
                    {data.corrected_by_decider[decider] ?? 0} ({pct(data.corrected_by_decider[decider] ?? 0, total)})
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={3}>Chưa có phiên nào được gắn.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {data.samples.length ? (
        <div className="eligible-offers">
          <h3>Mẫu bị báo sai gần đây</h3>
          <ul>
            {data.samples.map((sample) => (
              <li key={`${sample.insight_id}-${sample.created_at}`}>
                <div>
                  <strong>
                    {INSIGHT_FIELD_LABELS[sample.field] ?? sample.field}: {sample.value}
                  </strong>
                  <small>“{sample.evidence_quote}”</small>
                  {sample.note ? <small>Ghi chú TVV: {sample.note}</small> : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/** Trang `/admin/turn-traces`: hai tab — vệt quyết định (có sẵn) và chất lượng trích xuất (Phase 6). */
export function TurnTraceTabs() {
  const [tab, setTab] = useState<"traces" | "quality">("traces");
  return (
    <div className="customer360-page">
      <div aria-label="Mục quan sát" className="customer360-tabs" role="tablist">
        <button aria-selected={tab === "traces"} onClick={() => setTab("traces")} role="tab" type="button">
          Vệt quyết định
        </button>
        <button aria-selected={tab === "quality"} onClick={() => setTab("quality")} role="tab" type="button">
          Chất lượng trích xuất
        </button>
      </div>
      <div role="tabpanel">{tab === "traces" ? <TurnTracePanel /> : <ExtractionQualityPanel />}</div>
    </div>
  );
}
