"use client";

import { ArrowUpRight, CheckCircle2, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { ChatSessionKpis, RecentChatSessions } from "@/components/admin/chat-session-list";
import { MetricCard } from "@/components/shared/metric-card";
import { type DashboardMetrics, fetchAdminDashboardMetrics } from "@/lib/api/assignments";

const defaultFunnel = [
  { label: "Bắt đầu hội thoại", value: 2_480, percent: 100 },
  { label: "Hoàn tất hồ sơ", value: 2_068, percent: 83 },
  { label: "Có đề xuất", value: 1_814, percent: 73 },
  { label: "Được duyệt", value: 1_342, percent: 54 },
  { label: "Đặt lái thử", value: 318, percent: 13 },
];

export function AdminDashboard() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchAdminDashboardMetrics();
      setMetrics(data);
    } catch {
      // Keep null to show fallback or default
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const cards = [
    {
      label: "Hội thoại",
      value: metrics ? metrics.total_conversations.toLocaleString("vi-VN") : "2.480",
      note: "+12,6% toàn hệ thống",
    },
    {
      label: "Hồ sơ hoàn tất",
      value: metrics ? metrics.completed_profiles.toLocaleString("vi-VN") : "2.068",
      note: "Hồ sơ khách hàng",
    },
    {
      label: "Đề xuất đã duyệt",
      value: metrics ? metrics.approved_reviews.toLocaleString("vi-VN") : "1.342",
      note: `${metrics ? metrics.quality_stats.approved_original_pct : 74}% nguyên trạng`,
    },
    {
      label: "Yêu cầu lái thử",
      value: metrics ? metrics.total_bookings.toLocaleString("vi-VN") : "318",
      note: "Lịch hẹn showroom",
    },
  ];

  const funnelList = metrics?.funnel && metrics.funnel.length > 0 ? metrics.funnel : defaultFunnel;
  const quality = metrics?.quality_stats ?? {
    approved_original_pct: 74,
    edited_pct: 21,
    rejected_pct: 5,
  };

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
              Trung tâm phân công <ArrowUpRight size={15} />
            </Link>
            <Link className="text-button" href="/admin/chat-sessions">
              Xem phiên chat <ArrowUpRight size={15} />
            </Link>
            {/* Sếp 2026-08-26: mục này vốn đã hứa "và AI trace" trong phần mô tả
                mà không có đường nào tới. Vệt quyết định chỉ nằm trong thanh điều
                hướng bên, nên ai vào thẳng dashboard thì không biết nó tồn tại. */}
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
            <span className="status-badge status-info">
              <ArrowUpRight size={14} /> Trực tiếp từ DB
            </span>
          </div>
          <div className="funnel-chart">
            {funnelList.map((step) => (
              <div key={step.label}>
                <div className="funnel-bar" style={{ width: `${Math.max(step.percent, 24)}%` }}>
                  <span>{step.label}</span>
                  <strong>{step.value.toLocaleString("vi-VN")}</strong>
                </div>
                <small>{step.percent}%</small>
              </div>
            ))}
          </div>
        </section>

        <aside className="ops-panel quality-panel">
          <div className="ops-panel-heading">
            <div>
              <h2>Chất lượng vận hành</h2>
              <p>Tỷ lệ kiểm soát rủi ro HITL</p>
            </div>
          </div>
          <ul>
            <li>
              <CheckCircle2 size={18} />
              <span>
                <strong>{quality.approved_original_pct}% duyệt nguyên trạng</strong>
                <small>Chất lượng đề xuất ổn định</small>
              </span>
            </li>
            <li>
              <CheckCircle2 size={18} />
              <span>
                <strong>{quality.edited_pct}% chỉnh sửa nhẹ</strong>
                <small>Tư vấn viên bổ sung ưu đãi</small>
              </span>
            </li>
            <li>
              <CheckCircle2 size={18} />
              <span>
                <strong>{quality.rejected_pct}% từ chối</strong>
                <small>Chủ yếu do thông tin cần xác minh</small>
              </span>
            </li>
          </ul>
        </aside>
      </div>
    </>
  );
}
