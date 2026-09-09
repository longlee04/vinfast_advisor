import type { AITrace, ChatSession, TraceObservation, UserSummary } from "@/types/chat-observability";

const customer: UserSummary = { id: "customer-001", name: "Khách hàng #VF-101", email: "customer.101@example.com", initials: "KH" };
const advisor: UserSummary = { id: "advisor-001", name: "Tư vấn viên #01", email: "advisor.01@vinfast.vn", initials: "TV" };

const observations: TraceObservation[] = [
  { id: "obs-route", kind: "route", name: "Route Intent", status: "completed", latencyMs: 42, summary: "car_recommendation", details: { route: "car_recommendation", confidence: "0.96" } },
  { id: "obs-slots", kind: "slots", name: "Slot Extraction", status: "completed", latencyMs: 31, summary: "3 ràng buộc được xác định", details: { budget: "≤ 800.000.000 ₫", seats: "5", fuel: "Electric" } },
  { id: "obs-retrieval", kind: "retrieval", name: "Retrieval", status: "completed", latencyMs: 193, summary: "Qdrant · 10 kết quả", details: { vectorDb: "Qdrant", collection: "vehicle_catalog", query: "xe điện 5 chỗ ngân sách 800 triệu", topK: 10, retrieved: 10, documents: ["VF7 · 0.91", "VF6 · 0.88", "VF8 · 0.84"] } },
  { id: "obs-reranking", kind: "reranking", name: "Reranking", status: "completed", latencyMs: 112, summary: "top_k = 5", details: { strategy: "business_score_v2", topK: 5 } },
  { id: "obs-search", kind: "tool", name: "vehicle_search", status: "completed", latencyMs: 84, summary: "5 xe phù hợp", details: { input: "seats: 5 · budget_max: 800M", output: "5 vehicles found" } },
  { id: "obs-llm", kind: "llm", name: "LLM Generation", status: "completed", latencyMs: 2310, summary: "OpenAI · GPT-4o Mini", details: { provider: "OpenAI", model: "gpt-4o-mini", temperature: 0.0, inputTokens: 1248, outputTokens: 386 } },
];

const primaryTrace: AITrace = {
  id: "tr_01J8VF7RECOMMEND",
  sessionId: "d79b229c",
  messageId: "msg-ai-001",
  status: "completed",
  latencyMs: 2840,
  model: { provider: "OpenAI", name: "gpt-4o-mini", temperature: 0.0, maxTokens: 1024 },
  usage: { inputTokens: 1248, outputTokens: 386, totalTokens: 1634 },
  costUsd: 0.0042,
  observations,
  decision: { intent: "vehicle_recommendation", route: "car_recommendation", summary: "Người dùng cung cấp ngân sách và số chỗ ngồi, vì vậy workflow tư vấn xe được chọn.", extractedConstraints: ["Ngân sách ≤ 800 triệu", "5 chỗ ngồi", "Nhu cầu xe điện"], dataSources: ["Vehicle Catalog", "Pricing Database", "Qdrant Retrieval"] },
  input: { userMessage: "Tôi có 800 triệu và muốn mua xe điện 5 chỗ.", context: "Lịch sử hội thoại gần nhất của customer", retrievedContext: "VF7, VF6, VF8 · các mẫu xe điện đang kinh doanh" },
  output: "Với ngân sách 800 triệu và nhu cầu xe điện 5 chỗ, VF 6 và VF 7 là hai lựa chọn phù hợp để anh/chị cân nhắc.",
};

const secondTrace: AITrace = {
  id: "tr_01J8VF7POLICY",
  sessionId: "d79b229c",
  messageId: "msg-ai-002",
  status: "completed",
  latencyMs: 1680,
  model: { provider: "OpenAI", name: "gpt-4o-mini", temperature: 0.0 },
  usage: { inputTokens: 812, outputTokens: 214, totalTokens: 1026 },
  observations: [
    observations[0],
    { id: "obs-policy", kind: "tool", name: "policy_lookup", status: "completed", latencyMs: 92, summary: "2 chính sách được tìm thấy", details: { input: "bảo hành pin VF7", output: "2 policy documents found" } },
    observations[5],
  ],
  decision: { intent: "policy_lookup", route: "policy_rag", summary: "Câu hỏi yêu cầu tra cứu chính sách bảo hành hiện hành.", dataSources: ["Policy Documents", "Qdrant Retrieval"] },
  input: { userMessage: "Chính sách bảo hành pin của VF 7 như thế nào?", context: "Ngữ cảnh phiên hiện tại", retrievedContext: "Policy chunk: battery warranty" },
  output: "Chính sách bảo hành pin được áp dụng theo điều kiện và thời hạn hiện hành trong tài liệu chính sách.",
};

const fallbackTrace: AITrace = {
  id: "tr_01J8TIMEOUTRESTART",
  sessionId: "d79b229c",
  messageId: "msg-ai-003",
  status: "warning",
  latencyMs: 38500,
  model: { provider: "OpenAI", name: "gpt-4o-mini", temperature: 0.0 },
  usage: { inputTokens: 990, outputTokens: 421, totalTokens: 1411 },
  observations: [
    observations[0],
    { id: "obs-llm-fail", kind: "llm", name: "LLM Generation", status: "failed", latencyMs: 30100, summary: "Provider timeout sau 30 giây", details: { provider: "OpenAI", model: "gpt-4o-mini", error: "Read timed out · retry 1", retry: 1 } },
    { id: "obs-llm-fallback", kind: "llm", name: "LLM Fallback", status: "completed", latencyMs: 8350, summary: "GPT-4o · thành công", details: { provider: "OpenAI", model: "gpt-4o", fallback: "true" } },
  ],
  decision: { intent: "tco_estimate", route: "tco_workflow", summary: "Người dùng yêu cầu tính toán chi phí sở hữu; provider chính quá thời gian nên hệ thống chuyển fallback.", dataSources: ["TCO Assumptions", "Pricing Database"] },
  input: { userMessage: "Tổng chi phí sở hữu VF 7 trong 5 năm khoảng bao nhiêu?", context: "Ngữ cảnh phiên hiện tại", retrievedContext: "TCO assumption: khu vực miền Bắc" },
  output: "Chi phí sở hữu ước tính của VF 7 trong 5 năm tại khu vực miền Bắc khoảng 420 triệu đồng.",
  error: { title: "Provider timeout", detail: "gpt-4o-mini không phản hồi trong 30 giây. Hệ thống đã chuyển sang GPT-4o và hoàn tất.", retry: 1, fallback: "GPT-4o" },
};

const messages = [
  { id: "msg-customer-001", role: "customer" as const, content: "Tôi có 800 triệu và muốn mua xe điện 5 chỗ.", timestamp: "22:51" },
  { id: "msg-ai-001", role: "ai" as const, content: "Với ngân sách 800 triệu và nhu cầu xe điện 5 chỗ, VF 6 và VF 7 là hai lựa chọn phù hợp để anh/chị cân nhắc.", timestamp: "22:51", traceId: primaryTrace.id },
  { id: "msg-advisor-001", role: "advisor" as const, content: "Em có thể tư vấn thêm về không gian và chi phí sử dụng của VF 7 nếu anh/chị muốn.", timestamp: "22:52" },
  { id: "msg-customer-002", role: "customer" as const, content: "Chính sách bảo hành pin của VF 7 như thế nào?", timestamp: "22:55" },
  { id: "msg-ai-002", role: "ai" as const, content: "Chính sách bảo hành pin được áp dụng theo điều kiện và thời hạn hiện hành trong tài liệu chính sách.", timestamp: "22:55", traceId: secondTrace.id },
  { id: "msg-customer-003", role: "customer" as const, content: "Tổng chi phí sở hữu VF 7 trong 5 năm khoảng bao nhiêu?", timestamp: "22:57" },
  { id: "msg-ai-003", role: "ai" as const, content: "Chi phí sở hữu ước tính của VF 7 trong 5 năm tại khu vực miền Bắc khoảng 420 triệu đồng.", timestamp: "22:58", traceId: fallbackTrace.id },
];

export const chatSessions: ChatSession[] = [
  { id: "d79b229c", customer, advisor, status: "ACTIVE", messageCount: 26, aiTurnCount: 9, traceCount: 9, startedAt: "22:31 · 08/08/2026", lastActivityAt: "22:58", duration: "27 phút", messages, traces: [primaryTrace, secondTrace, fallbackTrace] },
  { id: "92af18b2", customer: { id: "customer-002", name: "Khách hàng #VF-102", email: "customer.102@example.com", initials: "KH" }, advisor: { id: "advisor-001", name: "Tư vấn viên #01", email: "advisor.01@vinfast.vn", initials: "TV" }, status: "WAITING_ADVISOR", messageCount: 8, aiTurnCount: 3, traceCount: 3, startedAt: "21:48 · 08/08/2026", lastActivityAt: "22:52", messages: [], traces: [] },
  { id: "71bc112a", customer: { id: "customer-003", name: "Khách hàng #VF-103", email: "customer.103@example.com", initials: "KH" }, advisor: { id: "advisor-002", name: "Tư vấn viên #02", email: "advisor.02@vinfast.vn", initials: "TV" }, status: "CLOSED", messageCount: 24, aiTurnCount: 8, traceCount: 8, startedAt: "18:20 · 03/08/2026", lastActivityAt: "21:45", duration: "3 giờ 25 phút", messages: [], traces: [] },
  { id: "44ca809e", customer: { id: "customer-004", name: "Khách hàng #VF-104", email: "customer.104@example.com", initials: "KH" }, status: "TRANSFERRED", messageCount: 14, aiTurnCount: 5, traceCount: 5, startedAt: "16:12 · 15/07/2026", lastActivityAt: "20:18", messages: [], traces: [] },
];

export function getChatSession(id: string): ChatSession | undefined {
  return chatSessions.find((session) => session.id === id);
}

export function getTraceForMessage(session: ChatSession, messageId: string): AITrace | undefined {
  return session.traces.find((trace) => trace.messageId === messageId);
}
