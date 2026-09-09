import { buildTracesForMessages } from "@/lib/chat-trace-generator";
import { readStoredSession, type AgentSessionState } from "@/store/agent-session";
import type { ChatMessage, ChatSession, UserSummary } from "@/types/chat-observability";

const fallbackEmail = "khach@demo.vinfast.vn";

function customerSummary(email: string | undefined): UserSummary {
  const resolved = email?.trim() || fallbackEmail;
  return { id: "live-customer", name: "Khách đang tư vấn", email: resolved, initials: "KH" };
}

function buildLiveSession(stored: AgentSessionState, email: string | undefined): ChatSession {
  const rawMessages: ChatMessage[] = stored.messages.map((message, index) => ({
    id: `${stored.sessionId}-msg-${index}`,
    role: message.role === "user" ? "customer" : "ai",
    content: message.text,
    timestamp: "Trực tiếp",
  }));

  const { messages, traces } = buildTracesForMessages(stored.sessionId, rawMessages);
  const aiTurnCount = messages.filter((message) => message.role === "ai").length;

  return {
    id: stored.sessionId,
    customer: customerSummary(email),
    status: "ACTIVE",
    messageCount: messages.length,
    aiTurnCount,
    traceCount: traces.length,
    startedAt: "Đang diễn ra",
    lastActivityAt: "Trực tiếp",
    messages,
    traces,
  };
}

/**
 * Phiên hội thoại CUSTOMER đang hoạt động trong trình duyệt này, đọc từ
 * sessionStorage của `AgentSessionProvider` (`/consultation` ghi vào).
 *
 * `subscribeLiveChatSession` lắng nghe sự kiện `storage` để phiên chạy ở TAB
 * khác (customer đang chat) xuất hiện ngay trên trang admin. `getLiveChatSession`
 * trả snapshot đã cache theo (email, session_id, số tin nhắn) nên tham chiếu ổn
 * định giữa các lần render — dùng được với `useSyncExternalStore`.
 */

let cached: { key: string; value: ChatSession | null } | null = null;

export function getLiveChatSession(email: string | undefined): ChatSession | null {
  const stored = readStoredSession();
  const key = `${email ?? ""}|${stored?.sessionId ?? ""}|${stored?.messages.length ?? 0}`;
  if (cached && cached.key === key) return cached.value;
  const value = stored && stored.messages.length > 0 ? buildLiveSession(stored, email) : null;
  cached = { key, value };
  return value;
}

export function getLiveChatSessionById(id: string, email: string | undefined): ChatSession | null {
  const session = getLiveChatSession(email);
  return session?.id === id ? session : null;
}

export function subscribeLiveChatSession(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}