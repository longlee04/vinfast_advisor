"use client";

import { ExternalLink, GitMerge, Split } from "lucide-react";
import Link from "next/link";

import { StatusBadge } from "@/components/shared/status-badge";
import type { SessionRow, ViewerRole } from "@/types/customer360";

import { SESSION_KIND_LABELS } from "./customer360-labels";


const STATUS_BADGES: Record<SessionRow["status"], { tone: "success" | "warning" | "neutral"; label: string }> = {
  ACTIVE: { tone: "success", label: "Đang hoạt động" },
  WAITING_ADVISOR: { tone: "warning", label: "Chờ Advisor" },
  CLOSED: { tone: "neutral", label: "Đã đóng" },
};

function sessionHref(role: ViewerRole, sessionId: string): string {
  return role === "admin" ? `/admin/chat-sessions/${sessionId}` : `/advisor/conversations/${sessionId}`;
}

function formatWhen(iso: string): string {
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(value);
}

export type SessionListProps = {
  readonly sessions: readonly SessionRow[];
  readonly role: ViewerRole;
  /** Admin xem hồ sơ ở chế độ chỉ đọc: link sang trang trace thay vì phòng chat. */
  readonly readOnly: boolean;
  readonly loading?: boolean;
  /** Cơ hội của khách — để TVV Gộp phiên vào cơ hội khác. */
  readonly opportunities?: readonly { readonly id: string; readonly title: string }[];
  /** TVV Tách (`target=null`) / Gộp phiên. Không truyền → không có nút (Admin, màn dự phòng). */
  readonly onMove?: (sessionId: string, target: string | null) => void;
};

/** Danh sách phiên của MỘT khách — dùng trong hồ sơ khách (dialog, rồi tab "Phiên chat"). */
export function SessionList({ sessions, role, readOnly, loading = false, opportunities = [], onMove }: SessionListProps) {
  if (!loading && sessions.length === 0) {
    return <p className="customer360-empty">Chưa có phiên chat nào từ khách hàng này.</p>;
  }
  return (
    <ul aria-busy={loading} className="customer360-session-list">
      {sessions.map((session) => {
        const badge = STATUS_BADGES[session.status];
        const closed = session.status === "CLOSED";
        return (
          <li key={session.session_id}>
            <div>
              <div className="customer360-session-head">
                <span className="mono-text">#{session.session_id.slice(0, 8)}</span>
                <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
                {session.kind !== "UNASSIGNED" ? <small>{SESSION_KIND_LABELS[session.kind]}</small> : null}
                {session.needs_review ? <StatusBadge tone="warning">Cần xác nhận nhu cầu</StatusBadge> : null}
              </div>
              <p title={session.summary_excerpt ?? undefined}>{session.summary_excerpt || "Phiên hội thoại"}</p>
              <small>{formatWhen(session.last_activity_at)}</small>
            </div>
            <div className="customer360-session-actions">
              {!readOnly && onMove && session.kind === "SALES" ? (
                <>
                  <button className="text-button" onClick={() => onMove(session.session_id, null)} type="button">
                    <Split size={13} /> Tách thành nhu cầu mới
                  </button>
                  {opportunities.some((item) => item.id !== session.opportunity_id) ? (
                    <label className="customer360-merge">
                      <GitMerge size={13} />
                      <span className="sr-only">Gộp vào nhu cầu</span>
                      <select
                        defaultValue=""
                        onChange={(event) => {
                          if (event.target.value) onMove(session.session_id, event.target.value);
                        }}
                      >
                        <option value="">Gộp vào…</option>
                        {opportunities
                          .filter((item) => item.id !== session.opportunity_id)
                          .map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.title}
                            </option>
                          ))}
                      </select>
                    </label>
                  ) : null}
                </>
              ) : null}
              <Link className="secondary-button" href={sessionHref(role, session.session_id)}>
                <ExternalLink size={12} /> {readOnly ? "Xem" : closed ? "Xem lại" : "Mở chat"}
              </Link>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
