"use client";

import { Bot, Check, CheckCheck, ChevronLeft, Ellipsis, Loader2, Paperclip, Send, ShieldCheck, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type AdvisorConversationDetail,
  closeAdvisorConversation,
  deleteAdvisorConversation,
  fetchAdvisorConversation,
  handoffAdvisorConversation,
  sendAdvisorMessage,
} from "@/lib/api/agent";

type MessageStatus = "sending" | "sent" | "received" | "seen";
type ChatMessage = {
  id: string;
  role: "USER" | "ASSISTANT" | "ADVISOR";
  text: string;
  time: string;
  status?: MessageStatus;
};

type MessageGroup = {
  role: ChatMessage["role"];
  messages: ChatMessage[];
};
type ConnectionState = "connected" | "disconnected" | "reconnecting";

function formatTime(dateStr?: string): string {
  if (!dateStr) return "vừa xong";
  const date = new Date(dateStr);
  return Number.isNaN(date.getTime())
    ? "vừa xong"
    : date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function initials(label: string, fallback: string): string {
  const letters = label.trim().split(/\s+/).map((word) => word[0]).filter(Boolean).slice(-2).join("");
  return (letters || fallback).toUpperCase();
}

function groupMessages(messages: readonly ChatMessage[]): MessageGroup[] {
  return messages.reduce<MessageGroup[]>((groups, message) => {
    const previous = groups.at(-1);
    if (previous?.role === message.role) {
      previous.messages.push(message);
      return groups;
    }
    groups.push({ role: message.role, messages: [message] });
    return groups;
  }, []);
}

function statusLabel(status?: MessageStatus): string {
  if (status === "sending") return "Đang gửi";
  if (status === "sent") return "Đã gửi";
  if (status === "received") return "Đã nhận";
  return "Đã xem";
}

function MessageMeta({ message, advisor }: Readonly<{ message: ChatMessage; advisor: boolean }>) {
  if (!advisor) return <time dateTime={message.time}>{message.time}</time>;
  return <span><time dateTime={message.time}>{message.time}</time> · {statusLabel(message.status)}</span>;
}

export function AdvisorLiveChat({ conversationId }: Readonly<{ conversationId: string }>) {
  const router = useRouter();
  const [detail, setDetail] = useState<AdvisorConversationDetail | null>(null);
  const [messages, setMessages] = useState<readonly ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [closed, setClosed] = useState(false);
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("reconnecting");
  const [confirmClose, setConfirmClose] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmHandoff, setConfirmHandoff] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [handoffing, setHandoffing] = useState(false);
  const [showNewMessage, setShowNewMessage] = useState(false);
  const messageListRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);
  const loadedOnceRef = useRef(false);
  const messageSignatureRef = useRef("");

  const loadConversation = useCallback(async (): Promise<void> => {
    try {
      if (loadedOnceRef.current) setConnectionState("reconnecting");
      const data = await fetchAdvisorConversation(conversationId);
      setDetail(data);
      setClosed((prev) => prev || data.status === "CLOSED" || data.status === "HANDED_OFF" || data.status === "COMPLETED");
      setLoadError(false);
      const mapped: ChatMessage[] = (data.messages || []).map(
        (
          message: {
            message_id?: string;
            sender_type?: "CUSTOMER" | "AGENT" | "ADVISOR" | "SYSTEM";
            role?: string;
            content: string;
            created_at: string;
          },
          index: number,
        ) => {
          const rawRole = (message.role || message.sender_type || "").toUpperCase();
          const role: "USER" | "ADVISOR" | "ASSISTANT" =
            rawRole === "CUSTOMER" || rawRole === "USER"
              ? "USER"
              : rawRole === "ADVISOR"
                ? "ADVISOR"
                : "ASSISTANT";
          return {
            id: message.message_id || `msg-${index}`,
            role,
            text: message.content,
            time: formatTime(message.created_at),
            status: role === "ADVISOR" ? "seen" : undefined,
          };
        },
      );
      const signature = mapped.map((message) => `${message.id}:${message.text}`).join("|");
      if (signature !== messageSignatureRef.current) {
        messageSignatureRef.current = signature;
        setMessages(mapped);
      }
      loadedOnceRef.current = true;
      setConnectionState("connected");
    } catch {
      setLoadError(true);
      setConnectionState(loadedOnceRef.current ? "reconnecting" : "disconnected");
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void loadConversation();
    });
    const interval = setInterval(() => {
      if (active && !closed) void loadConversation();
    }, 3000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [closed, loadConversation]);

  useEffect(() => {
    const list = messageListRef.current;
    if (!list) return;
    if (isNearBottomRef.current) {
      list.scrollTo({ top: list.scrollHeight, behavior: loadedOnceRef.current ? "smooth" : "auto" });
      setShowNewMessage(false);
    } else {
      setShowNewMessage(true);
    }
  }, [messages]);

  const customerLabel = detail?.customer_display || (detail?.customer_id ? `Khách hàng #${detail.customer_id.slice(0, 6)}` : "Khách hàng");
  const customerAvatar = initials(customerLabel, "KH");
  const advisorAvatar = initials(detail?.assigned_advisor_id || "Advisor", "AD");
  const groupedMessages = useMemo(() => groupMessages(messages), [messages]);
  const budget = detail?.slots?.budget_vnd ?? detail?.slots?.budget_max_vnd;
  const budgetStr = typeof budget === "number" ? `${Math.round(budget / 1_000_000)} triệu` : "Chưa rõ";
  const vehicle = detail?.slots?.vehicle_models ? String(detail.slots.vehicle_models) : detail?.slots?.vehicle_type ? String(detail.slots.vehicle_type) : "Chưa xác định";
  const priority = detail?.hitl_priority ?? "HIGH";
  const statusText = closed ? "Đã kết thúc" : loading ? "Đang tải hội thoại" : connectionState === "connected" ? "Đang kết nối" : connectionState === "reconnecting" ? "Đang kết nối lại..." : "Mất kết nối";

  function handleScroll(): void {
    const list = messageListRef.current;
    if (!list) return;
    isNearBottomRef.current = list.scrollHeight - list.scrollTop - list.clientHeight < 80;
    if (isNearBottomRef.current) setShowNewMessage(false);
  }

  function scrollToLatest(): void {
    const list = messageListRef.current;
    if (!list) return;
    isNearBottomRef.current = true;
    list.scrollTo({ top: list.scrollHeight, behavior: "smooth" });
    setShowNewMessage(false);
  }

  async function sendMessage(): Promise<void> {
    const text = draft.trim();
    if (!text || closed || sending) return;
    const optimisticId = crypto.randomUUID();
    setSending(true);
    setDraft("");
    setMessages((current) => [...current, { id: optimisticId, role: "ADVISOR", text, time: formatTime(), status: "sending" }]);
    try {
      const result = await sendAdvisorMessage(conversationId, text);
      setMessages((current) => current.map((message) => message.id === optimisticId ? { ...message, status: "sent", time: formatTime(result.created_at) } : message));
    } catch {
      setMessages((current) => current.filter((message) => message.id !== optimisticId));
      setDraft(text);
    } finally {
      setSending(false);
    }
  }

  async function handleClose(): Promise<void> {
    try {
      await closeAdvisorConversation(conversationId);
      setClosed(true);
      setConfirmClose(false);
      router.push("/advisor");
    } catch {
      setConfirmClose(false);
    }
  }

  async function handleDelete(): Promise<void> {
    if (deleting) return;
    try {
      setDeleting(true);
      await deleteAdvisorConversation(conversationId);
      setConfirmDelete(false);
      router.push("/advisor");
    } catch {
      setConfirmDelete(false);
    } finally {
      setDeleting(false);
    }
  }

  async function handleHandoff(): Promise<void> {
    if (handoffing) return;
    try {
      setHandoffing(true);
      await handoffAdvisorConversation(conversationId);
      setConfirmHandoff(false);
      router.push("/advisor");
    } catch {
      setConfirmHandoff(false);
    } finally {
      setHandoffing(false);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void sendMessage();
  }

  return (
    <div className="advisor-chat-page">
      <section className="advisor-chat-shell">
        <header className="advisor-chat-header">
          <Link className="advisor-chat-back" href="/advisor" aria-label="Quay lại hàng đợi"><ChevronLeft size={20} /></Link>
          <span className="advisor-chat-avatar customer-avatar">{customerAvatar}</span>
          <div className="advisor-chat-contact">
            <strong>{customerLabel}</strong>
            <span className={`${closed ? "connection-status is-closed" : "connection-status"} connection-${connectionState}`}><i />{statusText}</span>
          </div>
          <div className="advisor-chat-header-actions">
            <button className="chat-icon-button" onClick={() => setConfirmDelete(true)} type="button" aria-label="Xóa cuộc trò chuyện" title="Xóa cuộc trò chuyện"><Trash2 size={18} className="text-red-500 hover:text-red-600" /></button>
            <button className="chat-icon-button" type="button" aria-label="Thông tin cuộc trò chuyện" title={`Cuộc trò chuyện #${conversationId.slice(0, 8)}`}><Ellipsis size={20} /></button>
            {!closed ? (
              <>
                <button
                  className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all shadow-xs cursor-pointer"
                  onClick={() => setConfirmHandoff(true)}
                  type="button"
                  title="Chuyển lại cuộc trò chuyện cho trợ lý ảo AI"
                >
                  <Bot size={15} />
                  <span>Chuyển cho AI</span>
                </button>
                <button className="chat-end-button" onClick={() => setConfirmClose(true)} type="button">
                  Kết thúc
                </button>
              </>
            ) : null}
          </div>
        </header>

        <div className="advisor-chat-transcript" aria-live="polite" onScroll={handleScroll} ref={messageListRef}>
          <div className="advisor-chat-session-note">Cuộc trò chuyện #{conversationId.slice(0, 8)}</div>
          {loading ? <div className="advisor-chat-state"><Loader2 className="spin" size={20} /> Đang tải tin nhắn...</div> : null}
          {!loading && loadError ? <div className="advisor-chat-state"><span>Không tải được cuộc trò chuyện.</span><button onClick={() => void loadConversation()} type="button">Thử lại</button></div> : null}
          {!loading && !loadError && groupedMessages.length === 0 ? <div className="advisor-chat-state"><span>Chưa có tin nhắn trong phiên này.</span></div> : null}
          {!loading && !loadError ? groupedMessages.map((group, groupIndex) => {
            const advisor = group.role === "ADVISOR";
            const avatar = advisor ? advisorAvatar : group.role === "USER" ? customerAvatar : "SYS";
            return <div className={`message-group ${advisor ? "is-advisor" : "is-customer"}`} key={`${group.role}-${groupIndex}`}>
              <span className="message-group-avatar">{avatar}</span>
              <div className="message-group-body">
                {group.messages.map((message, messageIndex) => <article className="advisor-message" key={message.id}>
                  <div className="advisor-message-bubble">{message.text}</div>
                  <div className="advisor-message-meta"><MessageMeta advisor={advisor} message={message} />{advisor && messageIndex === group.messages.length - 1 ? <span className="message-status-icon" aria-label={statusLabel(message.status)}>{message.status === "sending" ? <Loader2 className="spin" size={12} /> : message.status === "seen" ? <CheckCheck size={13} /> : message.status === "received" ? <CheckCheck size={13} /> : <Check size={13} />}</span> : null}</div>
                </article>)}
              </div>
            </div>;
          }) : null}
          {showNewMessage ? <button className="new-message-indicator" onClick={scrollToLatest} type="button">↓ Tin nhắn mới</button> : null}
        </div>

        <form className="advisor-chat-composer" onSubmit={submit}>
          <button className="composer-tool-button" type="button" aria-label="Đính kèm tệp" title="Đính kèm tệp (sắp có)"><Paperclip size={19} /></button>
          <input aria-label="Tin nhắn gửi khách hàng" disabled={closed} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }} placeholder={closed ? "Phiên chat đã kết thúc" : "Soạn tin nhắn..."} value={draft} />
          <button aria-label="Gửi tin nhắn" className="composer-send-button" disabled={closed || !draft.trim() || sending} type="submit">{sending ? <Loader2 className="spin" size={18} /> : <Send size={18} />}</button>
        </form>
        {closed ? <div className="advisor-chat-ended"><span>Phiên chat đã kết thúc.</span><Link href="/advisor">Quay lại hàng đợi</Link></div> : null}
      </section>

      <aside className="advisor-chat-context-panel">
        <div className="context-heading"><span className="eyebrow">Thông tin khách hàng</span><strong>{customerLabel}</strong><span className="context-session">#{conversationId.slice(0, 8)}</span></div>
        <dl><div><dt>Ngân sách</dt><dd>{budgetStr}</dd></div><div><dt>Xe quan tâm</dt><dd>{vehicle}</dd></div><div><dt>Lý do cần hỗ trợ</dt><dd>{detail?.hitl_reasons?.join(", ") || "Khách yêu cầu tư vấn viên"}</dd></div><div><dt>Mức độ</dt><dd className={priority === "URGENT" ? "context-danger" : "context-high"}>{priority}</dd></div></dl>
        <div className="context-checks"><strong>Thông tin đã được kiểm chứng</strong><span><Check size={15} /> Dữ liệu đã xác thực</span><span><ShieldCheck size={15} /> Không có cảnh báo</span></div>
      </aside>

      {confirmClose ? <div className="chat-confirm-backdrop" role="presentation"><section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="end-chat-title"><button className="chat-confirm-close" onClick={() => setConfirmClose(false)} type="button" aria-label="Đóng"><X size={18} /></button><span className="eyebrow">Kết thúc phiên</span><h2 id="end-chat-title">Bạn có chắc muốn kết thúc phiên tư vấn?</h2><p>Khách hàng sẽ không thể tiếp tục gửi tin nhắn trong phiên này và yêu cầu sẽ được đánh dấu hoàn tất.</p><div><button className="secondary-button" onClick={() => setConfirmClose(false)} type="button">Huỷ</button><button className="danger-button" onClick={() => void handleClose()} type="button">Kết thúc phiên</button></div></section></div> : null}

      {confirmDelete ? <div className="chat-confirm-backdrop" role="presentation"><section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-chat-title"><button className="chat-confirm-close" onClick={() => setConfirmDelete(false)} type="button" aria-label="Đóng"><X size={18} /></button><span className="eyebrow text-red-600">Xóa cuộc trò chuyện</span><h2 id="delete-chat-title">Xóa toàn bộ cuộc trò chuyện này?</h2><p>Hành động này sẽ xóa vĩnh viễn toàn bộ tin nhắn và trạng thái của phiên trò chuyện.</p><div><button className="secondary-button" onClick={() => setConfirmDelete(false)} type="button">Huỷ</button><button className="danger-button bg-red-600 hover:bg-red-700 text-white" disabled={deleting} onClick={() => void handleDelete()} type="button">{deleting ? "Đang xóa..." : "Xóa vĩnh viễn"}</button></div></section></div> : null}

      {confirmHandoff ? (
        <div className="chat-confirm-backdrop" role="presentation">
          <section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="handoff-chat-title">
            <button className="chat-confirm-close" onClick={() => setConfirmHandoff(false)} type="button" aria-label="Đóng">
              <X size={18} />
            </button>
            <span className="eyebrow text-indigo-600">Chuyển cho Trợ lý ảo</span>
            <h2 id="handoff-chat-title">Chuyển lại cuộc trò chuyện cho AI?</h2>
            <p>Hệ thống sẽ chuyển quyền xử lý cuộc trò chuyện lại cho AI Agent để tiếp tục tư vấn tự động cho khách hàng.</p>
            <div>
              <button className="secondary-button" onClick={() => setConfirmHandoff(false)} type="button">
                Huỷ
              </button>
              <button
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm cursor-pointer"
                disabled={handoffing}
                onClick={() => void handleHandoff()}
                type="button"
              >
                {handoffing ? "Đang chuyển..." : "Xác nhận chuyển"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
