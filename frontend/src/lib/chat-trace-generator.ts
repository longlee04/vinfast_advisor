import type { AITrace, ChatMessage, TraceObservation } from "@/types/chat-observability";

/**
 * Tính toán NLU Confidence động dựa trên công thức NLU Layer của Backend:
 * Confidence = 0.50 * Evidence + 0.20 * Support + 0.30 * Trust
 */
export function calculateNluConfidence(userMessage: string): {
  confidence: number;
  formattedConfidence: string;
  tier: "AUTO" | "CONFIRM" | "CLARIFY";
} {
  const normalized = userMessage.toLowerCase();

  // 1. Nhận diện các thực thể (Vehicle models, specs, intent keywords)
  const vehicleModelMatches = (normalized.match(/vf\s?[2356789]|e34|minio|evo|feliz|klara|theon|vento/g) || []).length;
  const specKeywordMatches = (normalized.match(/giá|pin|sạc|tầm hoạt động|km|công suất|mô-men|màu|chỗ ngồi|kích thước|bảo hành|thuê pin/g) || []).length;
  const intentKeywordMatches = (normalized.match(/so sánh|tư vấn|mua|lái thử|đặt cọc|tìm|xem|bảng giá|khác biệt/g) || []).length;

  const totalEntityCount = vehicleModelMatches + specKeywordMatches + intentKeywordMatches;

  // 2. Evidence component (0.0 - 1.0): Điểm khớp của thực thể mạnh nhất
  let evidenceScore = 0.40;
  if (vehicleModelMatches > 0) {
    evidenceScore = 0.98;
  } else if (specKeywordMatches > 0 || intentKeywordMatches > 0) {
    evidenceScore = 0.85;
  } else if (/xe|ô tô|xe máy/i.test(normalized)) {
    evidenceScore = 0.70;
  } else if (/chào|hi|hello|ơi/i.test(normalized)) {
    evidenceScore = 0.60;
  }

  // 3. Support component (0.0 - 1.0): Mức độ chứng thực (>= 2 thực thể là full support)
  const supportScore = Math.min(totalEntityCount, 2) / 2;

  // 4. Rewrite trust (1.0 cho câu trực tiếp)
  const trustScore = 1.0;

  // 5. Tính raw confidence: 0.50 * Evidence + 0.20 * Support + 0.30 * Trust
  let rawConfidence = (0.50 * evidenceScore) + (0.20 * supportScore) + (0.30 * trustScore);

  // Phạt nếu không có từ khóa liên quan đến sản phẩm/hành động
  if (totalEntityCount === 0 && !/xe|ô tô|xe máy/i.test(normalized)) {
    rawConfidence *= 0.60;
  }

  const confidence = Math.min(0.99, Math.max(0.20, Number(rawConfidence.toFixed(2))));
  const tier = confidence >= 0.85 ? "AUTO" : confidence >= 0.60 ? "CONFIRM" : "CLARIFY";

  return {
    confidence,
    formattedConfidence: confidence.toFixed(2),
    tier,
  };
}

/**
 * Tạo trace Langfuse chi tiết và thực tế cho từng lượt phản hồi của AI.
 */
export function generateTraceForAiTurn(
  sessionId: string,
  messageId: string,
  userMessage: string,
  aiMessage: string,
  index: number,
): AITrace {
  const isVehicleQuery = /xe|car|ô tô|xe máy|vf|giá|tiền|triệu|tỷ/i.test(userMessage);
  const isGreetingOrClarify = /chào|hello|hi|muốn|gặp|tư vấn viên|không/i.test(userMessage);

  const intent = isVehicleQuery ? "vehicle_recommendation" : isGreetingOrClarify ? "slot_clarification" : "general_consultation";
  const route = isVehicleQuery ? "car_recommendation" : isGreetingOrClarify ? "clarification_workflow" : "faq_policy";

  const nlu = calculateNluConfidence(userMessage);

  const traceHex = (index + 1).toString().padStart(2, "0");
  const traceId = `tr_01J8VF${traceHex}${intent === "vehicle_recommendation" ? "RECOMMEND" : "CLARIFY"}`;

  const latencyMs = Math.floor(1800 + (index * 230) % 1200);
  const inputTokens = Math.floor(950 + (userMessage.length * 12));
  const outputTokens = Math.floor(120 + (aiMessage.length / 3));
  const totalTokens = inputTokens + outputTokens;
  const costUsd = Number(((inputTokens * 0.00000125) + (outputTokens * 0.000005)).toFixed(5));

  const observations: TraceObservation[] = [
    {
      id: `obs-${messageId}-route`,
      kind: "route",
      name: "Route Intent",
      status: "completed",
      latencyMs: 38 + (index * 5) % 20,
      summary: route,
      details: {
        route,
        confidence: nlu.formattedConfidence,
        tier: nlu.tier,
        intent,
      },
    },
    {
      id: `obs-${messageId}-slots`,
      kind: "slots",
      name: "Slot Extraction",
      status: "completed",
      latencyMs: 28 + (index * 4) % 15,
      summary: isVehicleQuery ? "Trích xuất tiêu chí & nhu cầu người dùng" : "Phân tích ngữ cảnh hội thoại",
      details: isVehicleQuery
        ? {
            vehicle_type: /xe máy/i.test(userMessage) ? "electric_motorbike" : "electric_car",
            extracted_text: userMessage.slice(0, 80),
            status: "extracted",
          }
        : {
            dialog_turn: index + 1,
            clarification_needed: "true",
          },
    },
    {
      id: `obs-${messageId}-retrieval`,
      kind: "retrieval",
      name: "Retrieval",
      status: "completed",
      latencyMs: 165 + (index * 12) % 40,
      summary: "Qdrant · 10 kết quả liên quan",
      details: {
        vectorDb: "Qdrant",
        collection: "vehicle_catalog",
        query: userMessage,
        topK: 10,
        retrieved: 10,
        documents: ["VF 6 · 0.92", "VF 7 · 0.89", "VF 8 · 0.85", "VF 5 · 0.81"],
      },
    },
    {
      id: `obs-${messageId}-reranking`,
      kind: "reranking",
      name: "Reranking",
      status: "completed",
      latencyMs: 95 + (index * 7) % 30,
      summary: "top_k = 5",
      details: {
        strategy: "business_score_v2",
        topK: 5,
      },
    },
    {
      id: `obs-${messageId}-tool`,
      kind: "tool",
      name: "vehicle_search",
      status: "completed",
      latencyMs: 75 + (index * 9) % 25,
      summary: "Tra cứu danh mục sản phẩm VinFast",
      details: {
        tool_name: "query_vinfast_catalog",
        input: userMessage,
        output: "Danh sách thông số, giá niêm yết và chính sách pin",
      },
    },
    {
      id: `obs-${messageId}-llm`,
      kind: "llm",
      name: "LLM Generation",
      status: "completed",
      latencyMs: latencyMs - 400,
      summary: "OpenAI · GPT-4o Mini",
      details: {
        provider: "OpenAI",
        model: "gpt-4o-mini",
        temperature: 0.0,
        inputTokens,
        outputTokens,
      },
    },
  ];

  return {
    id: traceId,
    sessionId,
    messageId,
    status: "completed",
    latencyMs,
    model: {
      provider: "OpenAI",
      name: "gpt-4o-mini",
      temperature: 0.0,
      maxTokens: 1024,
    },
    usage: {
      inputTokens,
      outputTokens,
      totalTokens,
    },
    costUsd,
    observations,
    decision: {
      intent,
      route,
      summary: `Hệ thống xác định yêu cầu "${userMessage.slice(0, 60)}" và điều phối qua workflow ${route}.`,
      extractedConstraints: isVehicleQuery
        ? ["Sản phẩm VinFast", "Danh mục xe điện", "Chính sách bảo hành"]
        : ["Hội thoại trực tiếp", "Ngữ cảnh khách hàng"],
      dataSources: ["Vehicle Catalog", "Pricing Database", "Qdrant Retrieval"],
    },
    input: {
      userMessage,
      context: "Ngữ cảnh phiên hội thoại hiện tại",
      retrievedContext: "Dữ liệu thông số kỹ thuật xe và chính sách ưu đãi VinFast",
    },
    output: aiMessage,
  };
}

/**
 * Xây dựng toàn bộ danh sách traces và gán `traceId` cho từng message AI trong phiên.
 */
export function buildTracesForMessages(sessionId: string, rawMessages: ChatMessage[]): { messages: ChatMessage[]; traces: AITrace[] } {
  const traces: AITrace[] = [];
  const messages: ChatMessage[] = [];

  let lastUserMessage = "Khách hàng bắt đầu phiên tư vấn";
  let aiIndex = 0;

  for (const msg of rawMessages) {
    if (msg.role === "customer") {
      lastUserMessage = msg.content;
      messages.push(msg);
    } else if (msg.role === "ai") {
      const trace = generateTraceForAiTurn(sessionId, msg.id, lastUserMessage, msg.content, aiIndex++);
      traces.push(trace);
      messages.push({
        ...msg,
        traceId: trace.id,
      });
    } else {
      messages.push(msg);
    }
  }

  return { messages, traces };
}
