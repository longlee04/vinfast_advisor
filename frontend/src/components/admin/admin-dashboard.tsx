"use client";

import { ArrowUpRight, CheckCircle2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ChatSessionKpis, RecentChatSessions } from "@/components/admin/chat-session-list";
import { MetricCard } from "@/components/shared/metric-card";
import { type DashboardMetrics, fetchAdminDashboardMetrics } from "@/lib/api/assignments";

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : value.toLocaleString("vi-VN");
}

/**
 * Admin Dashboard — MỌI con số từ backend (plan Customer 360 Phase 4). Bản cũ hiện số viết
 * cứng (2.480, 2.068, 74%…) khi API chưa trả hoặc lỗi; giờ chưa có thì hiện "—".
 *
 * Admin lo KỸ THUẬT (plan §15): chỉ số vận hành, phiên chat, trace. Số bán hàng (phễu, độ
 * nóng, rào cản) nằm ở trang Tổng quan của tư vấn viên — người chịu trách nhiệm với khách.
 */
export function AdminDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      setMetrics(await fetchAdminDashboardMetrics());
      setFailed(false);
    } catch {
      setMetrics(null);
      setFailed(true);
    }
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
            <h2>Quản lý phiên chat</h2>
            <p>Theo dõi các phiên tư vấn và AI trace. Khách do tư vấn viên tự nhận, không cần phân công.</p>
          </div>
          <div className="flex items-center gap-3">
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
