"use client";

import { Loader2, MessageSquare } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";

import { ChatSessionDetail } from "@/components/admin/chat-session-detail";
import { fetchAdvisorConversation, type AdvisorConversationDetail } from "@/lib/api/agent";
import { buildTracesForMessages } from "@/lib/chat-trace-generator";
import { getLiveChatSessionById, subscribeLiveChatSession } from "@/lib/live-chat-session";
import { useAuth } from "@/store/auth-store";
import type { ChatMessage, ChatSession } from "@/types/chat-observability";

function formatIsoTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  } catch {
    return "Vừa xong";
  }
}

function formatIsoDate(iso: string): string {
  try {
    const d = new Date(iso);
    const time = `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
    const date = `${d.getDate().toString().padStart(2, "0")}/${(d.getMonth() + 1).toString().padStart(2, "0")}/${d.getFullYear()}`;
    return `${time} · ${date}`;
  } catch {
    return "Hôm nay";
  }
}

function mapBackendToChatSession(detail: AdvisorConversationDetail): ChatSession {
  const rawMessages: ChatMessage[] = (detail.messages || []).map((msg, index) => ({
    id: msg.message_id || `msg-${index}`,
    role: msg.sender_type === "CUSTOMER" ? "customer" : msg.sender_type === "ADVISOR" ? "advisor" : "ai",
    content: msg.content,
    timestamp: formatIsoTime(msg.created_at),
  }));

  const { messages, traces } = buildTracesForMessages(detail.conversation_id, rawMessages);
  const aiTurnCount = messages.filter((m) => m.role === "ai").length;
  const isAnonymous = detail.customer_id.startsWith("anon-");
  const isEmail = detail.customer_id.includes("@");

  return {
    id: detail.conversation_id,
    customer: {
      id: detail.customer_id,
      name: detail.customer_display || (isAnonymous ? "Khách vãng lai" : "Khách hàng"),
      email: isEmail ? detail.customer_id : isAnonymous ? "Khách vãng lai" : detail.customer_id,
      initials: "KH",
    },
    advisor: detail.assigned_advisor_id
      ? {
          id: detail.assigned_advisor_id,
          name: detail.assigned_advisor_id.includes("@") ? detail.assigned_advisor_id : "Tư vấn viên",
          email: detail.assigned_advisor_id.includes("@") ? detail.assigned_advisor_id : "advisor@vinfast.vn",
          initials: detail.assigned_advisor_id.slice(0, 2).toUpperCase(),
        }
      : undefined,
    status:
      detail.status === "WAITING_ADVISOR"
        ? "WAITING_ADVISOR"
        : detail.status === "COMPLETED" || detail.status === "CLOSED"
        ? "CLOSED"
        : "ACTIVE",
    messageCount: messages.length,
    aiTurnCount,
    traceCount: traces.length,
    startedAt: formatIsoDate(detail.last_activity_at),
    lastActivityAt: formatIsoTime(detail.last_activity_at),
    messages,
    traces,
  };
}

/**
 * Resolver cho phiên KHÔNG nằm trong mock: đọc phiên customer đang hoạt động
 * trong trình duyệt này (sessionStorage / localStorage) hoặc query trực tiếp từ Backend API.
 */
export function LiveChatSessionDetail({ id }: Readonly<{ id: string }>) {
  const { user } = useAuth();
  const localSession: ChatSession | null = useSyncExternalStore(
    subscribeLiveChatSession,
    () => getLiveChatSessionById(id, user?.email),
    () => null,
  );

  const [backendSession, setBackendSession] = useState<ChatSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (localSession) {
      setLoading(false);
      return;
    }

    let active = true;
    setLoading(true);
    fetchAdvisorConversation(id)
      .then((detail) => {
        if (!active) return;
        setBackendSession(mapBackendToChatSession(detail));
      })
      .catch(() => {
        if (active) setBackendSession(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [id, localSession]);

  const session = localSession || backendSession;

  if (loading) {
    return (
      <div className="ops-state">
        <Loader2 className="spin" size={28} />
        <h2>Đang tải phiên chat...</h2>
        <p>Đang đồng bộ hóa nội dung hội thoại từ máy chủ.</p>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="ops-state">
        <MessageSquare size={28} />
        <h2>Không tìm thấy phiên</h2>
        <p>Phiên này không tồn tại hoặc đã bị xóa khỏi hệ thống.</p>
      </div>
    );
  }

  return <ChatSessionDetail session={session} />;
}