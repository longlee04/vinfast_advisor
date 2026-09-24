"use client";

import { ArrowUpRight, CheckCircle2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ChatSessionKpis, RecentChatSessions } from "@/components/admin/chat-session-list";
import { HorizontalBarChart } from "@/components/admin/customer360-charts";
import { bottleneckLabel } from "@/components/advisor/offer-state-labels";
import { HEAT_BAND_BADGES, SALES_STAGE_LABELS, SALES_STAGE_ORDER } from "@/components/customer360/customer360-labels";
import { MetricCard } from "@/components/shared/metric-card";
import { type Customer360Metrics, fetchCustomer360Metrics } from "@/lib/api/agent";
import { type DashboardMetrics, fetchAdminDashboardMetrics } from "@/lib/api/assignments";
import type { HeatBand } from "@/types/customer360";

const HEAT_ORDER: readonly HeatBand[] = ["HOT", "WARM", "COLD"];

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : value.toLocaleString("vi-VN");
}

/**
 * Admin Dashboard — MỌI con số từ backend (plan Customer 360 Phase 4). Bản cũ hiện số viết
 * cứng (2.480, 2.068, 74%…) khi API chưa trả hoặc lỗi; giờ chưa có thì hiện "—".
 */
export function AdminDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [c360, setC360] = useState<Customer360Metrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    const [base, customer] = await Promise.allSettled([fetchAdminDashboardMetrics(), fetchCustomer360Metrics(30)]);
    setMetrics(base.status === "fulfilled" ? base.value : null);
    setC360(customer.status === "fulfilled" ? customer.value : null);
    setFailed(base.status === "rejected");
    setLoading(false);
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const cards = [
    { label: "Hội thoại", value: formatCount(metrics?.total_conversations), note: "Toàn hệ thống" },
    { label: "Hồ sơ khách", value: formatCount(metrics?.completed_profiles), note: "Khách có hồ sơ liên hệ" },
    {
      label: "Đề xuất đã duyệt",
      value: formatCount(metrics?.approved_reviews),
      note: metrics ? `${metrics.quality_stats.approved_original_pct}% nguyên trạng` : "—",
    },
    { label: "Yêu cầu lái thử", value: formatCount(metrics?.total_bookings), note: "Lịch hẹn showroom" },
  ];
  const quality = metrics?.quality_stats;

  return (
    <>
      <div className="flex justify-end mb-2">
        <button
          className="text-xs text-slate-500 hover:text-slate-700 flex items-center gap-1"
          onClick={() => void loadData()}
          type="button"
        >
          <RefreshCw className={loading ? "animate-spin" : ""} size={13} />
          {loading ? "Đang đồng bộ..." : "Cập nhật số liệu"}
        </button>
      </div>
      {failed ? (
        <p className="inline-warning" role="alert">
          Không tải được số liệu vận hành. Các ô hiện dấu gạch cho tới khi tải lại được.
        </p>
      ) : null}

      <div className="metric-grid">
        {cards.map((metric) => (
          <MetricCard key={metric.label} label={metric.label} note={metric.note} value={metric.value} />
        ))}
      </div>

      <section className="ops-panel chat-dashboard-panel">
        <div className="ops-panel-heading">
          <div>
            <h2>Quản lý phiên chat & Phân công</h2>
            <p>Theo dõi các phiên tư vấn Customer, gán Advisor và AI trace.</p>
          </div>
          <div className="flex items-center gap-3">
            <Link className="text-button" href="/admin/assignments">
              Khách hàng & phân công <ArrowUpRight size={15} />
            </Link>
            <Link className="text-button" href="/admin/chat-sessions">
              Xem phiên chat <ArrowUpRight size={15} />
            </Link>
            <Link className="text-button" href="/admin/turn-traces">
              Vì sao agent đáp <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
        <ChatSessionKpis />
        <RecentChatSessions />
      </section>

      {c360 ? (
        <section className="ops-panel c360-dashboard" aria-label="Khách hàng 360">
          <div className="ops-panel-heading">
            <div>
              <h2>Khách hàng 360</h2>
              <p>
                {formatCount(c360.totals.open_opportunities)} cơ hội đang mở · {formatCount(c360.totals.needs_review)} phiên
                chờ TVV xác nhận nhu cầu
              </p>
            </div>
          </div>
          <div className="c360-dashboard-grid">
            <HorizontalBarChart
              data={SALES_STAGE_ORDER.map((stage) => ({ label: SALES_STAGE_LABELS[stage], value: c360.stages[stage] ?? 0 }))}
              title="Phễu 5 giai đoạn (số cơ hội)"
            />
            <HorizontalBarChart
              data={HEAT_ORDER.map((band) => ({ label: HEAT_BAND_BADGES[band].label, value: c360.heat[band] ?? 0 }))}
              title="Phân bố độ nóng (cơ hội đang mở)"
            />
            <HorizontalBarChart
              data={c360.barriers.map((item) => ({ label: bottleneckLabel(item.code), value: item.count }))}
              title="Rào cản nhiều nhất (30 ngày)"
            />
          </div>
          <table className="chat-table c360-workload">
            <caption>Khối lượng việc theo tư vấn viên</caption>
            <thead>
              <tr>
                <th scope="col">Tư vấn viên</th>
                <th scope="col">Khách phụ trách</th>
                <th scope="col">Khách nóng</th>
                <th scope="col">Phiên chờ</th>
              </tr>
            </thead>
            <tbody>
              {c360.workload.length ? (
                c360.workload.map((row) => (
                  <tr key={row.advisor_id}>
                    <td data-label="Tư vấn viên">{row.advisor_id}</td>
                    <td data-label="Khách phụ trách">{row.customers}</td>
                    <td data-label="Khách nóng">{row.hot_customers}</td>
                    <td data-label="Phiên chờ">{row.waiting_sessions}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={4}>Chưa có phân công nào.</td>
                </tr>
              )}
            </tbody>
          </table>
        </section>
      ) : null}

      <div className="admin-dashboard-grid">
        <section className="ops-panel funnel-panel">
          <div className="ops-panel-heading">
            <div>
              <h2>Phễu chuyển đổi vận hành</h2>
              <p>Thống kê thực tế từ hệ thống AI Sales Advisor</p>
            </div>
          </div>
          {metrics?.funnel.length ? (
            <div className="funnel-chart">
              {metrics.funnel.map((step) => (
                <div key={step.label}>
                  <div className="funnel-bar" style={{ width: `${Math.max(step.percent, 24)}%` }}>
                    <span>{step.label}</span>
                    <strong>{step.value.toLocaleString("vi-VN")}</strong>
                  </div>
                  <small>{step.percent}%</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="customer360-empty">{loading ? "Đang tải…" : "Chưa có dữ liệu phễu."}</p>
          )}
        </section>

        <aside className="ops-panel quality-panel">
          <div className="ops-panel-heading">
            <div>
              <h2>Chất lượng vận hành</h2>
              <p>Tỷ lệ kiểm soát rủi ro HITL</p>
            </div>
          </div>
          {quality ? (
            <ul>
              <li>
                <CheckCircle2 size={18} />
                <span>
                  <strong>{quality.approved_original_pct}% duyệt nguyên trạng</strong>
                  <small>Đề xuất được duyệt không sửa</small>
                </span>
              </li>
              <li>
                <CheckCircle2 size={18} />
                <span>
                  <strong>{quality.edited_pct}% chỉnh sửa</strong>
                  <small>Tư vấn viên sửa trước khi gửi</small>
                </span>
              </li>
              <li>
                <CheckCircle2 size={18} />
                <span>
                  <strong>{quality.rejected_pct}% từ chối</strong>
                  <small>Bản nháp bị loại</small>
                </span>
              </li>
            </ul>
          ) : (
            <p className="customer360-empty">{loading ? "Đang tải…" : "Chưa có dữ liệu."}</p>
          )}
        </aside>
      </div>
    </>
  );
}
