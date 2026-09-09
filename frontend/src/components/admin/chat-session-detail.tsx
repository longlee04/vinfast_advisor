"use client";

import { AlertTriangle, Bot, ChevronDown, ChevronLeft, Clock3, Database, GitBranch, KeyRound, Loader2, MessageSquare, Search, ShieldCheck, Sparkles, Terminal, Wrench, XCircle } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { chatSessionStatusLabels, chatSessionStatusTones } from "@/lib/chat-session-labels";
import type { AITrace, ChatMessage, ChatSession, ObservationKind, TraceObservation } from "@/types/chat-observability";

const observationIcons: Record<ObservationKind, typeof GitBranch> = { route: GitBranch, slots: Sparkles, retrieval: Database, reranking: Search, tool: Wrench, llm: Bot };
const observationLabels: Record<ObservationKind, string> = { route: "Agent route", slots: "Slot extraction", retrieval: "Retrieval", reranking: "Reranking", tool: "Tool call", llm: "Model" };
const traceStatusLabels: Record<AITrace["status"], string> = { completed: "Completed", failed: "Failed", warning: "Warning", running: "Running" };

function formatLatency(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`;
}
function traceTone(status: AITrace["status"]): "success" | "danger" | "warning" | "info" {
  return status === "completed" ? "success" : status === "failed" ? "danger" : status === "warning" ? "warning" : "info";
}

function ObservationRow({ observation }: Readonly<{ observation: TraceObservation }>) {
  const [expanded, setExpanded] = useState(observation.kind === "llm" || observation.kind === "retrieval");
  const Icon = observationIcons[observation.kind];
  return <div className={`trace-observation is-${observation.status}`}>
    <button className="trace-observation-trigger" type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}>
      <span className="trace-status-icon">{observation.status === "failed" ? <XCircle size={15} /> : observation.status === "warning" ? <AlertTriangle size={15} /> : observation.status === "running" ? <Loader2 className="spin" size={15} /> : <ShieldCheck size={15} />}</span>
      <span className="trace-observation-icon"><Icon size={15} /></span>
      <span className="trace-observation-name"><strong>{observation.name}</strong><small>{observationLabels[observation.kind]} · {observation.summary}</small></span>
      <span className="trace-observation-time">{formatLatency(observation.latencyMs)}</span>
      <ChevronDown className={expanded ? "is-expanded" : ""} size={16} />
    </button>
    {expanded ? <div className="trace-observation-details">{Object.entries(observation.details).map(([key, value]) => <div key={key}><span>{key}</span><strong>{Array.isArray(value) ? value.join(" · ") : String(value)}</strong></div>)}</div> : null}
  </div>;
}

function TracePanel({
  trace,
  onBackToConversation,
}: Readonly<{
  trace?: AITrace;
  onBackToConversation?: () => void;
}>) {
  if (!trace) {
    return (
      <div className="trace-empty">
        {onBackToConversation ? (
          <button
            type="button"
            className="trace-link"
            style={{ alignSelf: "flex-start", marginBottom: 12, cursor: "pointer" }}
            onClick={onBackToConversation}
          >
            <ChevronLeft size={14} /> Quay lại hội thoại
          </button>
        ) : null}
        <Bot size={30} />
        <h2>Chưa có AI trace</h2>
        <p>Phiên chat này chưa có lượt xử lý AI tương ứng hoặc chưa có dữ liệu trace.</p>
      </div>
    );
  }
  return (
    <div className="trace-panel-inner">
      <div className="trace-panel-heading">
        <div>
          {onBackToConversation ? (
            <button
              type="button"
              className="trace-link"
              style={{ marginBottom: 8, cursor: "pointer" }}
              onClick={onBackToConversation}
            >
              <ChevronLeft size={14} /> Quay lại hội thoại
            </button>
          ) : null}
          <span className="eyebrow">AI trace</span>
          <h2 className="mono-text">{trace.id}</h2>
        </div>
        <StatusBadge tone={traceTone(trace.status)}>{traceStatusLabels[trace.status]}</StatusBadge>
      </div>
      <div className="trace-summary-cards">
        <div>
          <Clock3 size={15} />
          <strong>{formatLatency(trace.latencyMs)}</strong>
          <span>Latency</span>
        </div>
        <div>
          <Sparkles size={15} />
          <strong>{trace.usage?.totalTokens?.toLocaleString("vi-VN") ?? "N/A"}</strong>
          <span>Tokens</span>
        </div>
        <div>
          <Terminal size={15} />
          <strong>{trace.observations.length}</strong>
          <span>Operations</span>
        </div>
        <div>
          <KeyRound size={15} />
          <strong>{trace.costUsd ? `$${trace.costUsd.toFixed(4)}` : "N/A"}</strong>
          <span>Cost</span>
        </div>
      </div>
      {trace.model ? (
        <div className="trace-model-strip">
          <Bot size={17} />
          <span>
            <small>Model / Provider</small>
            <strong>{trace.model.name}</strong>
            <em>{trace.model.provider}</em>
          </span>
          <span className="trace-model-metrics">
            {trace.usage?.inputTokens?.toLocaleString("vi-VN") ?? "N/A"} in · {trace.usage?.outputTokens?.toLocaleString("vi-VN") ?? "N/A"} out
          </span>
        </div>
      ) : null}
      <div className="trace-section">
        <div className="trace-section-heading">
          <div>
            <span className="eyebrow">Timeline</span>
            <h3>Observations</h3>
          </div>
          <small>{trace.observations.length} bước xử lý</small>
        </div>
        <div className="trace-timeline">
          {trace.observations.map((observation) => (
            <ObservationRow key={observation.id} observation={observation} />
          ))}
        </div>
      </div>
      {trace.decision ? (
        <div className="trace-detail-grid">
          <section>
            <div className="trace-section-heading">
              <div>
                <span className="eyebrow">Decision metadata</span>
                <h3>Decision summary</h3>
              </div>
            </div>
            <dl className="trace-definition-list">
              <div>
                <dt>Intent</dt>
                <dd className="mono-text">{trace.decision.intent ?? "N/A"}</dd>
              </div>
              <div>
                <dt>Selected route</dt>
                <dd>{trace.decision.route ?? "N/A"}</dd>
              </div>
              <div>
                <dt>Reason</dt>
                <dd>{trace.decision.summary ?? "N/A"}</dd>
              </div>
              <div>
                <dt>Constraints</dt>
                <dd>
                  {trace.decision.extractedConstraints?.map((item) => (
                    <span className="trace-chip" key={item}>
                      {item}
                    </span>
                  )) ?? "N/A"}
                </dd>
              </div>
              <div>
                <dt>Data sources</dt>
                <dd>{trace.decision.dataSources?.join(" · ") ?? "N/A"}</dd>
              </div>
            </dl>
          </section>
          <section>
            <div className="trace-section-heading">
              <div>
                <span className="eyebrow">Prompt boundary</span>
                <h3>Input & output</h3>
              </div>
              <ShieldCheck size={17} />
            </div>
            <div className="trace-io-block">
              <span>User message</span>
              <p>{trace.input?.userMessage ?? "N/A"}</p>
              <span>Context</span>
              <p>{trace.input?.context ?? "N/A"}</p>
              <span>Final output</span>
              <p>{trace.output ?? "N/A"}</p>
            </div>
            <small className="privacy-note">
              <ShieldCheck size={13} /> Hidden chain-of-thought và secret không được hiển thị.
            </small>
          </section>
        </div>
      ) : null}
      {trace.error ? (
        <div className="trace-error">
          <AlertTriangle size={18} />
          <div>
            <strong>{trace.error.title}</strong>
            <p>{trace.error.detail}</p>
            {trace.error.retry ? <small>Retry: {trace.error.retry}</small> : null}
            {trace.error.fallback ? <small>Fallback: {trace.error.fallback}</small> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ConversationPanel({ session, selectedMessageId, onSelect }: Readonly<{ session: ChatSession; selectedMessageId: string | undefined; onSelect: (message: ChatMessage) => void }>) {
  return <div className="conversation-panel"><div className="conversation-panel-heading"><div><span className="eyebrow">Session transcript</span><h2>Conversation</h2></div><span>{session.messageCount} tin nhắn</span></div>{session.messages.length ? <div className="admin-message-list">{session.messages.map((message) => <article className={`admin-message is-${message.role} ${selectedMessageId === message.id ? "is-selected" : ""}`} key={message.id}><div className="admin-message-meta"><span className="chat-avatar">{message.role === "customer" ? session.customer.initials : message.role === "advisor" ? session.advisor?.initials ?? "AD" : "AI"}</span><span><strong>{message.role === "customer" ? "Customer" : message.role === "advisor" ? "Advisor" : "AI"}</strong><small>{message.timestamp}</small></span>{message.traceId ? <button className="trace-link" type="button" onClick={() => onSelect(message)}><Bot size={13} /> Xem trace</button> : null}</div><div className="admin-message-bubble">{message.content}</div></article>)}</div> : <div className="trace-empty conversation-empty"><MessageSquare size={28} /><h2>Chưa có transcript</h2><p>Phiên này chưa có nội dung hội thoại.</p></div>}</div>;
}

export function ChatSessionDetail({ session }: Readonly<{ session: ChatSession }>) {
  const firstTraceMessage = session.messages.find((message) => message.traceId) || session.messages.find((m) => m.role === "ai");
  const [selectedMessageId, setSelectedMessageId] = useState(firstTraceMessage?.id);
  const [mobileTab, setMobileTab] = useState<"conversation" | "trace">("conversation");
  const selectedMessage = useMemo(() => session.messages.find((message) => message.id === selectedMessageId), [selectedMessageId, session.messages]);
  const selectedTrace = useMemo(() => {
    if (!selectedMessage) return undefined;
    if (selectedMessage.traceId) {
      const byTraceId = session.traces.find((t) => t.id === selectedMessage.traceId);
      if (byTraceId) return byTraceId;
    }
    return session.traces.find((t) => t.messageId === selectedMessage.id);
  }, [selectedMessage, session.traces]);

  const totalCost = session.traces.reduce((acc, t) => acc + (t.costUsd || 0), 0);
  const formattedCost = totalCost > 0 ? `$${totalCost.toFixed(4)}` : "N/A";

  const handleBackToConversation = () => {
    setMobileTab("conversation");
  };

  return <div className="chat-detail-page">
    <Link className="vehicle-detail-back" href="/admin/chat-sessions">
      <ChevronLeft size={16} /> Quay lại danh sách Phiên chat
    </Link>
    <div className="chat-detail-header"><div><span className="eyebrow">Session / {session.id}</span><h1>Phiên chat <span className="mono-text">#{session.id}</span></h1><p>Theo dõi transcript và cách AI xử lý từng lượt.</p></div><StatusBadge tone={chatSessionStatusTones[session.status]}>{chatSessionStatusLabels[session.status]}</StatusBadge></div>
    <div className="session-overview"><div><span>Customer</span><strong>{session.customer.name}</strong><small>{session.customer.email}</small></div><div><span>Advisor</span><strong>{session.advisor?.name ?? "Chưa phân công"}</strong><small>{session.advisor?.email ?? "N/A"}</small></div><div><span>Bắt đầu</span><strong>{session.startedAt.split(" · ")[0]}</strong><small>{session.startedAt.split(" · ")[1]}</small></div><div><span>Hoạt động cuối</span><strong>{session.lastActivityAt}</strong><small>{session.messageCount} tin nhắn · {session.aiTurnCount} lượt AI</small></div></div>
    <div className="chat-detail-metrics"><span><strong>{session.aiTurnCount}</strong> lượt AI</span><span><strong>{session.traces.length || session.traceCount}</strong> trace</span><span><strong>{session.duration ?? "Trực tiếp"}</strong> thời lượng</span><span><strong>{formattedCost}</strong> chi phí ước tính</span></div>
    <div className="chat-detail-tabs" role="tablist"><button type="button" className={mobileTab === "conversation" ? "is-active" : ""} onClick={() => setMobileTab("conversation")}><MessageSquare size={15} /> Conversation</button><button type="button" className={mobileTab === "trace" ? "is-active" : ""} onClick={() => setMobileTab("trace")}><GitBranch size={15} /> AI Trace</button></div>
    <div className="chat-detail-layout">
      <div className={mobileTab === "conversation" ? "" : "is-mobile-hidden"}><ConversationPanel session={session} selectedMessageId={selectedMessageId} onSelect={(message) => { setSelectedMessageId(message.id); setMobileTab("trace"); }} /></div>
      <aside className={mobileTab === "trace" ? "trace-panel" : "trace-panel is-mobile-hidden"}><TracePanel trace={selectedTrace} onBackToConversation={handleBackToConversation} /></aside>
    </div>
  </div>;
}