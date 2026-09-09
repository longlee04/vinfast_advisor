"use client";

import { ChevronRight, MessageSquare, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { listAdvisorConversations, type AdvisorConversationDetail } from "@/lib/api/agent";
import { chatSessionStatusLabels, chatSessionStatusTones } from "@/lib/chat-session-labels";
import { getLiveChatSession, subscribeLiveChatSession } from "@/lib/live-chat-session";
import { useAuth } from "@/store/auth-store";
import type { ChatSession, ChatSessionStatus } from "@/types/chat-observability";

type DayRange = "ALL" | "TODAY" | "WEEK" | "MONTH";
const DEMO_TODAY = new Date(2026, 7, 8);

const dayRangeLabels: Record<DayRange, string> = { ALL: "Tất cả", TODAY: "Hôm nay", WEEK: "7 ngày", MONTH: "30 ngày" };

function formatIsoTime(iso?: string): string {
  if (!iso) return "Trực tiếp";
  try {
    const d = new Date(iso);
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  } catch {
    return "Trực tiếp";
  }
}

function formatIsoDate(iso?: string): string {
  if (!iso) return "Đang diễn ra";
  try {
    const d = new Date(iso);
    const time = `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
    const date = `${d.getDate().toString().padStart(2, "0")}/${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getFullYear()}`;
    return `${time} · ${date}`;
  } catch {
    return "Đang diễn ra";
  }
}

function mapBackendListItem(item: AdvisorConversationDetail): ChatSession {
  const messages = item.messages || [];
  const msgCount = messages.length || 1;
  const aiTurnCount = messages.length > 0
    ? messages.filter((m) => m.sender_type === "AGENT" || (m as unknown as { role?: string }).role === "ASSISTANT").length
    : Math.max(1, Math.floor(msgCount / 2));
  const traceCount = aiTurnCount;

  const isAnonymous = item.customer_id.startsWith("anon-");
  const isEmail = item.customer_id.includes("@");

  return {
    id: item.conversation_id,
    customer: {
      id: item.customer_id,
      name: item.customer_display || (isAnonymous ? "Khách vãng lai" : "Khách hàng"),
      email: isEmail ? item.customer_id : isAnonymous ? "Khách vãng lai" : item.customer_id,
      initials: "KH",
    },
    advisor: item.assigned_advisor_id
      ? {
          id: item.assigned_advisor_id,
          name: item.assigned_advisor_id.includes("@") ? item.assigned_advisor_id : "Tư vấn viên",
          email: item.assigned_advisor_id.includes("@") ? item.assigned_advisor_id : "advisor@vinfast.vn",
          initials: item.assigned_advisor_id.slice(0, 2).toUpperCase(),
        }
      : undefined,
    status:
      item.status === "WAITING_ADVISOR"
        ? "WAITING_ADVISOR"
        : item.status === "COMPLETED" || item.status === "CLOSED"
        ? "CLOSED"
        : "ACTIVE",
    messageCount: msgCount,
    aiTurnCount,
    traceCount,
    startedAt: formatIsoDate(item.last_activity_at),
    lastActivityAt: formatIsoTime(item.last_activity_at),
    messages: [],
    traces: [],
  };
}

function startedDate(session: ChatSession): Date {
  if (!session.startedAt.includes(" · ")) return new Date();
  const [, datePart] = session.startedAt.split(" · ");
  const [day, month, year] = datePart.split("/").map(Number);
  return new Date(year, month - 1, day);
}

/** Phiên customer đang hoạt động (cùng tab hoặc tab khác qua storage event). */
function useLiveChatSession(): ChatSession | null {
  const { user } = useAuth();
  return useSyncExternalStore(subscribeLiveChatSession, () => getLiveChatSession(user?.email), () => null);
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

export function ChatSessionList() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ChatSessionStatus | "ALL">("ALL");
  const [advisor, setAdvisor] = useState("ALL");
  const [dayRange, setDayRange] = useState<DayRange>("ALL");
  const [backendSessions, setBackendSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    let active = true;
    listAdvisorConversations()
      .then((res) => {
        if (!active) return;
        const mapped = (res.items || []).map(mapBackendListItem);
        setBackendSessions(mapped);
      })
      .catch(() => {
        // ignore if staff not logged in yet
      });
    return () => {
      active = false;
    };
  }, []);

  const liveSession = useLiveChatSession();

  // Merge và deduplicate: backend trước, liveSession ghi đè nếu trùng ID (không duplicate)
  const allSessions = useMemo(() => {
    const sessionMap = new Map<string, ChatSession>();
    for (const session of backendSessions) {
      sessionMap.set(session.id, session);
    }
    if (liveSession) {
      sessionMap.set(liveSession.id, liveSession);
    }
    return Array.from(sessionMap.values());
  }, [backendSessions, liveSession]);

  // KPI tính trên TOÀN BỘ phiên (allSessions) trước khi search / filter
  const totalSessions = allSessions.length;
  const activeSessions = allSessions.filter((s) => s.status === "ACTIVE").length;
  const waitingAdvisorSessions = allSessions.filter((s) => s.status === "WAITING_ADVISOR").length;

  const advisors = allSessions.flatMap((session) => (session.advisor ? [session.advisor] : []));
  const uniqueAdvisors = advisors.filter((item, index) => advisors.findIndex((other) => other.id === item.id) === index);

  const filtered = useMemo(() => {
    return allSessions.filter((session) => {
      const needle = query.trim().toLowerCase();
      const matchesQuery =
        !needle ||
        [session.id, session.customer.name, session.customer.email, session.advisor?.email ?? ""].some((value) =>
          value.toLowerCase().includes(needle),
        );
      const matchesRange =
        dayRange === "ALL" ||
        (() => {
          const diffDays = Math.round((DEMO_TODAY.getTime() - startedDate(session).getTime()) / 86_400_000);
          return dayRange === "TODAY" ? diffDays === 0 : dayRange === "WEEK" ? diffDays <= 7 : diffDays <= 30;
        })();
      return (
        matchesQuery &&
        matchesRange &&
        (status === "ALL" || session.status === status) &&
        (advisor === "ALL" || session.advisor?.id === advisor)
      );
    });
  }, [allSessions, query, dayRange, status, advisor]);

  return (
    <>
      <ChatSessionKpis
        total={totalSessions}
        active={activeSessions}
        waitingAdvisor={waitingAdvisorSessions}
      />
      <section className="chat-session-list ops-panel">
        <div className="chat-session-toolbar">
          <label className="ops-search">
            <Search size={16} />
            <span className="sr-only">Tìm phiên chat</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm customer / session / trace..."
            />
          </label>
          <div className="chat-session-selects">
            <label>
              <span>Trạng thái</span>
              <select value={status} onChange={(event) => setStatus(event.target.value as ChatSessionStatus | "ALL")}>
                <option value="ALL">Tất cả</option>
                {Object.entries(chatSessionStatusLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Advisor</span>
              <select value={advisor} onChange={(event) => setAdvisor(event.target.value)}>
                <option value="ALL">Tất cả</option>
                {uniqueAdvisors.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Khoảng ngày</span>
              <select value={dayRange} onChange={(event) => setDayRange(event.target.value as DayRange)}>
                {Object.entries(dayRangeLabels).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        </div>
        <div className="chat-session-result">
          <span>
            <strong>{filtered.length}</strong> phiên hiển thị
          </span>
          <span>{allSessions.length ? "Bao gồm phiên thực tế từ hệ thống" : "Chưa có phiên chat nào"}</span>
        </div>
        {filtered.length ? (
          <div className="chat-table-wrap">
            <table className="chat-table">
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Customer</th>
                  <th>Advisor</th>
                  <th>Status</th>
                  <th>Hoạt động</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {filtered.map((session) => {
                  const isLiveOrBackend = session.id === liveSession?.id || backendSessions.some((b) => b.id === session.id);
                  return (
                    <tr key={session.id} className={isLiveOrBackend ? "is-live" : ""}>
                      <td data-label="Session">
                        <div className="session-id-row">
                          <strong className="mono-text">{session.id}</strong>
                          {isLiveOrBackend ? <span className="live-pill">Trực tiếp</span> : null}
                        </div>
                        <small>
                          {session.messageCount} tin nhắn · {session.traceCount} trace
                        </small>
                      </td>
                      <td data-label="Customer">
                        <strong>{session.customer.name}</strong>
                        <small>{session.customer.email}</small>
                      </td>
                      <td data-label="Advisor">
                        {session.advisor ? (
                          <>
                            <strong>{session.advisor.name}</strong>
                            <small>{session.advisor.email}</small>
                          </>
                        ) : (
                          <small>Chưa phân công</small>
                        )}
                      </td>
                      <td data-label="Status">
                        <StatusBadge tone={chatSessionStatusTones[session.status]}>
                          {chatSessionStatusLabels[session.status]}
                        </StatusBadge>
                      </td>
                      <td data-label="Hoạt động">
                        <strong>{session.lastActivityAt}</strong>
                        <small>{session.startedAt}</small>
                      </td>
                      <td>
                        <Link className="table-action" href={`/admin/chat-sessions/${session.id}`}>
                          Xem <ChevronRight size={14} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="ops-state">
            <MessageSquare size={28} />
            <h2>Không tìm thấy phiên chat</h2>
            <p>Thử điều chỉnh từ khóa hoặc bộ lọc.</p>
          </div>
        )}
      </section>
    </>
  );
}

export function RecentChatSessions() {
  const liveSession = useLiveChatSession();
  const [backendSessions, setBackendSessions] = useState<ChatSession[]>([]);

  useEffect(() => {
    let active = true;
    listAdvisorConversations()
      .then((res) => {
        if (!active) return;
        setBackendSessions((res.items || []).map(mapBackendListItem));
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  const allSessions = useMemo(() => {
    const sessionMap = new Map<string, ChatSession>();
    for (const session of backendSessions) {
      sessionMap.set(session.id, session);
    }
    if (liveSession) {
      sessionMap.set(liveSession.id, liveSession);
    }
    return Array.from(sessionMap.values());
  }, [backendSessions, liveSession]);

  const recent = allSessions.slice(0, 3);
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
      {recent.map((session) => (
        <Link href={`/admin/chat-sessions/${session.id}`} key={session.id}>
          <span className="chat-avatar">{session.customer.initials}</span>
          <span className="recent-chat-copy">
            <strong>
              {session.customer.email}
              {session.id === liveSession?.id ? <span className="live-pill">Trực tiếp</span> : null}
            </strong>
            <small>
              {session.advisor?.name ?? (session.id === liveSession?.id ? "Đang tư vấn với AI" : "Chưa phân công")}
            </small>
          </span>
          <StatusBadge tone={chatSessionStatusTones[session.status]}>
            {chatSessionStatusLabels[session.status]}
          </StatusBadge>
          <span className="recent-chat-time">{session.lastActivityAt}</span>
          <ChevronRight size={15} />
        </Link>
      ))}
    </div>
  );
}