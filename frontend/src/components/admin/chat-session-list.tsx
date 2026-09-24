"use client";

import { ChevronRight, MessageSquare } from "lucide-react";
import Link from "next/link";

import { ChatSessionTable, useChatSessionRows } from "@/components/shared/chat-session-table";
import { StatusBadge } from "@/components/shared/status-badge";

/** Màn Admin `/admin/chat-sessions` — bảng dùng chung ở chế độ xem toàn hệ thống. */
export function ChatSessionList() {
  return <ChatSessionTable scope="all" />;
}

export function ChatSessionKpis({
  total = 0,
  active = 0,
  waitingAdvisor = 0,
}: Readonly<{ total?: number; active?: number; waitingAdvisor?: number }>) {
  return (
    <div className="metric-grid chat-kpi-grid">
      <article className="metric-card">
        <span>Tổng phiên</span>
        <strong>{total.toLocaleString("vi-VN")}</strong>
        <small>Phiên hệ thống</small>
      </article>
      <article className="metric-card">
        <span>Đang hoạt động</span>
        <strong>{active.toLocaleString("vi-VN")}</strong>
        <small>Live sessions</small>
      </article>
      <article className="metric-card">
        <span>Chờ Advisor</span>
        <strong>{waitingAdvisor.toLocaleString("vi-VN")}</strong>
        <small>Cần tiếp nhận</small>
      </article>
    </div>
  );
}

const RECENT_STATUS: Record<string, { tone: "info" | "warning" | "success"; label: string }> = {
  ACTIVE: { tone: "info", label: "Đang hoạt động" },
  WAITING_ADVISOR: { tone: "warning", label: "Chờ Advisor" },
  CLOSED: { tone: "success", label: "Đã đóng" },
};

/** Ba phiên gần nhất cho Admin Dashboard — cùng nguồn dữ liệu với bảng đầy đủ. */
export function RecentChatSessions() {
  const { rows } = useChatSessionRows("all");
  const recent = rows.slice(0, 3);
  if (recent.length === 0) {
    return (
      <div className="ops-state ops-state-compact">
        <MessageSquare size={20} />
        <p>Chưa có phiên chat nào.</p>
      </div>
    );
  }

  return (
    <div className="recent-chat-list">
      {recent.map((row) => {
        const status = RECENT_STATUS[row.status];
        return (
          <Link href={`/admin/chat-sessions/${row.id}`} key={row.id}>
            <span className="chat-avatar">KH</span>
            <span className="recent-chat-copy">
              <strong>
                {row.customerSub}
                {row.isLive ? <span className="live-pill">Trực tiếp</span> : null}
              </strong>
              <small>{row.advisorId ?? (row.isLive ? "Đang tư vấn với AI" : "Chưa phân công")}</small>
            </span>
            <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
            <ChevronRight size={15} />
          </Link>
        );
      })}
    </div>
  );
}
