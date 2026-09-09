export type ChatSessionStatus = "ACTIVE" | "WAITING_ADVISOR" | "ADVISOR_CONNECTED" | "CLOSED" | "TRANSFERRED";
export type TraceStatus = "completed" | "failed" | "running" | "warning";
export type ObservationKind = "route" | "slots" | "retrieval" | "reranking" | "tool" | "llm";

export type UserSummary = {
  id: string;
  name: string;
  email: string;
  initials: string;
};

export type ChatMessage = {
  id: string;
  role: "customer" | "ai" | "advisor";
  content: string;
  timestamp: string;
  traceId?: string;
};

export type TraceObservation = {
  id: string;
  kind: ObservationKind;
  name: string;
  status: TraceStatus;
  latencyMs: number;
  summary: string;
  details: Record<string, string | number | string[]>;
};

export type AITrace = {
  id: string;
  sessionId: string;
  messageId: string;
  status: TraceStatus;
  latencyMs: number;
  model?: { provider: string; name: string; temperature?: number; maxTokens?: number };
  usage?: { inputTokens?: number; outputTokens?: number; totalTokens?: number };
  costUsd?: number;
  observations: TraceObservation[];
  decision?: {
    intent?: string;
    route?: string;
    summary?: string;
    extractedConstraints?: string[];
    dataSources?: string[];
  };
  input?: { userMessage: string; context: string; retrievedContext: string };
  output?: string;
  error?: { title: string; detail: string; retry?: number; fallback?: string };
};

export type ChatSession = {
  id: string;
  customer: UserSummary;
  advisor?: UserSummary;
  status: ChatSessionStatus;
  messageCount: number;
  aiTurnCount: number;
  traceCount: number;
  startedAt: string;
  lastActivityAt: string;
  duration?: string;
  messages: ChatMessage[];
  traces: AITrace[];
};
