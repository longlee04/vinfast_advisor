/**
 * Client cho Agent API thật (`/api/v1/agent/*`). Cùng quy ước với `auth.ts`:
 * cookie HttpOnly cho phiên, cookie CSRF đọc được phải echo qua header cho mọi
 * request đổi trạng thái, và `credentials: "include"` để trình duyệt gửi cookie
 * cross-origin.
 */

import type { BuyerFor, CustomerOverview, HeatBand, OpportunityStatus, SalesStage, ViewerRole } from "@/types/customer360";
import type {
  BottleneckSignal,
  BottleneckSignalDetail,
  BottleneckSignalQueueStatus,
  BottleneckSignalVerdict,
  ConversationDetail,
  ConversationSummary,
  CustomerDeliveries,
  LocationKind,
  NearbyLocationList,
  OfferAdjustment,
  PendingReview,
  QueueEntry,
  ResolveReviewInput,
  ReviewDetail,
  ReviewQueueStatus,
  ProvinceOption,
  SalesOpportunity,
  TcoCard,
  TurnResponse,
  TestDriveAvailability,
  TestDriveOptionsResponse,
} from "@/types/agent";

import { csrfHeader, withSessionRetry } from "@/lib/api/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export class AgentApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
    this.name = "AgentApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const attempt = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: {
        "Cache-Control": "no-store",
        "Content-Type": "application/json",
        ...init.headers,
        ...csrfHeader(),
      },
    });
  const response = await withSessionRetry(attempt);
  const body = await response.json().catch(() => ({}) as Record<string, unknown>);
  if (!response.ok) {
    // Backend trả mã có cấu trúc: `{"detail": {"code": "LOCATION_UNKNOWN"}}`.
    // Bản trước chỉ giữ `detail` khi nó là CHUỖI, nên ba loại 409 khác nhau —
    // chưa biết vị trí, chưa biết loại xe, lỗi máy chủ — về client thành cùng
    // một chữ `request_failed`, và UI không phân biệt được để nói đúng câu.
    const detail = (body as { detail?: unknown }).detail;
    const code =
      typeof detail === "string"
        ? detail
        : typeof (detail as { code?: unknown })?.code === "string"
          ? (detail as { code: string }).code
          : "request_failed";
    throw new AgentApiError(code, response.status);
  }
  return body as T;
}

export function sendTurn(
  sessionId: string,
  clientTurnId: string,
  message: string,
  vehicleType?: string,
): Promise<TurnResponse> {
  return request<TurnResponse>("/agent/turn", {
    method: "POST",
    // `client_turn_id` là khoá khử trùng lặp phía server khi khách bấm gửi lại.
    // `vehicle_type` chỉ gửi khi có — backend `TurnRequest` không khai nó.
    body: JSON.stringify({
      session_id: sessionId,
      client_turn_id: clientTurnId,
      message,
      ...(vehicleType ? { vehicle_type: vehicleType } : {}),
    }),
  });
}

/**
 * Tính lại chi phí 5 năm theo giả định khách vừa chỉnh trên thẻ.
 *
 * Không gọi LLM ở phía server — cùng bộ tính tất định với khối chữ trong chat,
 * nên kéo thanh km bao nhiêu lần cũng được.
 */
/**
 * Ô giờ còn trống của MỘT ngày trên thẻ lái thử.
 *
 * Lượt chat chỉ chở ô của ngày mặc định (126 ô → 18). Thẻ vẫn bày đủ bảy ngày,
 * nên sáu ngày còn lại phải nạp qua đây — thiếu nó thì khách bấm sang ngày thứ
 * tư và thấy mọi khung đều mờ.
 *
 * KHÔNG gửi toạ độ: server đọc vị trí từ phiên, cùng nguồn đã dựng thẻ.
 */
export function fetchTestDriveAvailability(params: {
  sessionId: string;
  date: string;
}): Promise<TestDriveAvailability> {
  const query = new URLSearchParams({ session_id: params.sessionId, date: params.date });
  return request<TestDriveAvailability>(`/agent/test-drive/availability?${query.toString()}`);
}

/**
 * Thẻ lái thử tự xin vị trí rồi gọi đây để đổi thành thẻ đủ showroom/giờ
 * (hợp đồng đợt 8 mục 2). Phải có toạ độ HOẶC `locationText`. Server lưu vị
 * trí vào phiên và ghi pending `PENDING_SHOWROOM_SLOT`, nên nút giờ bấm sau đó
 * vẫn đi đúng đường `__lichlaithu__…` hiện có — client không thêm gì.
 */
export function fetchTestDriveOptions(params: {
  sessionId: string;
  vehicleId: string;
  latitude?: number | null;
  longitude?: number | null;
  locationText?: string | null;
}): Promise<TestDriveOptionsResponse> {
  const body: Record<string, unknown> = { session_id: params.sessionId, vehicle_id: params.vehicleId };
  if (params.latitude != null && params.longitude != null) {
    body.latitude = params.latitude;
    body.longitude = params.longitude;
  }
  if (params.locationText) body.location_text = params.locationText;
  return request<TestDriveOptionsResponse>("/agent/test-drive/options", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function estimateTco(params: {
  vehicleId: string;
  dailyDistanceKm: number;
  provinceCode?: string | null;
  sessionId?: string | null;
}): Promise<TcoCard> {
  return request<TcoCard>("/agent/tco/estimate", {
    method: "POST",
    body: JSON.stringify({
      vehicle_id: params.vehicleId,
      daily_distance_km: params.dailyDistanceKm,
      province_code: params.provinceCode ?? null,
      session_id: params.sessionId ?? null,
    }),
  });
}

/** Danh sách tỉnh cho ô chọn trên thẻ chi phí. */
export function fetchProvinceOptions(): Promise<readonly ProvinceOption[]> {
  return request<readonly ProvinceOption[]>("/agent/tco/provinces");
}

export function postNearestLocation(params: {
  sessionId?: string;
  locationType: readonly LocationKind[] | readonly string[];
  latitude?: number | null;
  longitude?: number | null;
  locationText?: string | null;
}): Promise<NearbyLocationList & { reply_text: string }> {
  return request("/locations/nearest", {
    method: "POST",
    body: JSON.stringify({
      session_id: params.sessionId ?? null,
      location_type: params.locationType,
      latitude: params.latitude ?? null,
      longitude: params.longitude ?? null,
      location_text: params.locationText ?? null,
    }),
  });
}

export type ReviewQueueStats = {
  pending: number;
  claimed: number;
  approved: number;
  rejected: number;
};

export function fetchReviewQueue(): Promise<readonly PendingReview[]> {
  return request<readonly PendingReview[]>("/agent/review");
}

export function fetchReviewStats(): Promise<ReviewQueueStats> {
  return request<ReviewQueueStats>("/agent/review/stats");
}

export function fetchReviewDetail(reviewId: string): Promise<ReviewDetail> {
  return request<ReviewDetail>(`/agent/review/${reviewId}`);
}

export function fetchDeliveries(sessionId: string): Promise<CustomerDeliveries> {
  return request<CustomerDeliveries>(`/agent/deliveries/${sessionId}`);
}

export function claimReview(
  reviewId: string,
): Promise<{ granted: boolean; rejection: string | null }> {
  return request(`/agent/review/${reviewId}/claim`, { method: "POST" });
}

export function approveReview(
  reviewId: string,
  editedContent?: string,
): Promise<{ review_id: string }> {
  return request(`/agent/review/${reviewId}/approve`, {
    method: "POST",
    body: JSON.stringify({ edited_content: editedContent ?? null }),
  });
}

export function rejectReview(reviewId: string): Promise<{ review_id: string }> {
  return request(`/agent/review/${reviewId}/reject`, { method: "POST" });
}

/**
 * Duyệt/từ chối kèm TUỲ CHỌN cấp ưu đãi và cờ chuyển tư vấn trực tiếp.
 *
 * Cửa này THÊM vào chứ không thay `/approve` + `/reject`: hai đường cũ vẫn là
 * hợp đồng đang chạy cho luồng duyệt trơn, đường này dành cho luồng có ưu đãi
 * hoặc handoff. `offer_adjustment` bỏ trống là hợp lệ (D12) — đề xuất ưu đãi là
 * bằng chứng, không phải nghĩa vụ.
 */
export function resolveReview(
  reviewId: string,
  input: ResolveReviewInput,
): Promise<{ review_id: string }> {
  return request(`/agent/review/${reviewId}/resolve`, {
    method: "POST",
    body: JSON.stringify({
      status: input.status,
      edited_content: input.edited_content ?? null,
      offer_adjustment: input.offer_adjustment ?? null,
      handoff_requested: input.handoff_requested ?? false,
    }),
  });
}

/**
 * Hàng đợi có lọc trạng thái + phân trang (`GET /agent/reviews`).
 *
 * Khác `fetchReviewQueue` ở chỗ đọc được cả mục đã xử lý và mang theo hồ sơ
 * khách + `offer_state` cho từng dòng. Backend chặn `limit` ngoài khoảng 1..100
 * bằng 400, nên đừng gửi giá trị ngoài biên.
 */
export function fetchReviews(
  options: {
    readonly status?: ReviewQueueStatus;
    readonly limit?: number;
    readonly offset?: number;
  } = {},
): Promise<readonly QueueEntry[]> {
  const query = new URLSearchParams({ status: options.status ?? "pending" });
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset !== undefined) query.set("offset", String(options.offset));
  return request<readonly QueueEntry[]>(`/agent/reviews?${query.toString()}`);
}

/**
 * Cơ hội bán hàng: phiên đang chạy đã bộc lộ >= 2 nút thắt, mới hoạt động xếp
 * trước. Nguồn tách hẳn khỏi hàng đợi duyệt.
 */
export function fetchBottleneckSignals(
  options: {
    readonly status?: BottleneckSignalQueueStatus;
    readonly limit?: number;
    readonly offset?: number;
  } = {},
): Promise<readonly BottleneckSignal[]> {
  const query = new URLSearchParams({ status: options.status ?? "pending" });
  if (options.limit !== undefined) query.set("limit", String(options.limit));
  if (options.offset !== undefined) query.set("offset", String(options.offset));
  return request<readonly BottleneckSignal[]>(`/agent/bottleneck-signals?${query.toString()}`);
}

export function fetchBottleneckSignalDetail(signalId: string): Promise<BottleneckSignalDetail> {
  return request<BottleneckSignalDetail>(`/agent/bottleneck-signals/${signalId}`);
}

export function claimBottleneckSignal(signalId: string): Promise<BottleneckSignal> {
  return request<BottleneckSignal>(`/agent/bottleneck-signals/${signalId}/claim`, { method: "POST" });
}

export function sendBottleneckSignalVerdict(
  signalId: string,
  verdict: BottleneckSignalVerdict,
): Promise<BottleneckSignal> {
  return request<BottleneckSignal>(`/agent/bottleneck-signals/${signalId}/verdict`, {
    method: "POST",
    body: JSON.stringify({ verdict }),
  });
}

export function sendBottleneckSignalOffer(
  signalId: string,
  adjustment: OfferAdjustment,
): Promise<{ readonly signal_id: string }> {
  return request(`/agent/bottleneck-signals/${signalId}/offer`, {
    method: "POST",
    body: JSON.stringify(adjustment),
  });
}

export function fetchSalesOpportunities(limit?: number): Promise<readonly SalesOpportunity[]> {
  const query = limit === undefined ? "" : `?limit=${limit}`;
  return request<readonly SalesOpportunity[]>(`/agent/sales-opportunities${query}`);
}

export function turnEventsUrl(sessionId: string): string {
  return `${API_BASE_URL}/agent/events/${sessionId}`;
}

export type ConversationMessagePage = {
  readonly items: ReadonlyArray<{ message_id: string; role: string; content: string; created_at: string }>;
  readonly next_cursor: string | null;
};

/** Số trang tối đa khi tải lại một hội thoại cũ — chặn vòng lặp nếu con trỏ hỏng. */
const MAX_MESSAGE_PAGES = 20;

export function fetchConversationMessages(
  sessionId: string,
  options?: Readonly<{ limit?: number; cursor?: string }>,
): Promise<ConversationMessagePage> {
  const query = new URLSearchParams();
  if (options?.limit) query.set("limit", String(options.limit));
  if (options?.cursor) query.set("cursor", options.cursor);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return request(`/conversations/${sessionId}/messages${suffix}`);
}

/**
 * Toàn bộ nội dung một hội thoại, theo đúng thứ tự thời gian.
 *
 * `GET /conversations/{id}/messages` phân trang TIẾN (cũ → mới, `limit` mặc
 * định 50). Gọi một lần rồi thôi thì hội thoại dài chỉ hiện được đoạn đầu và
 * khách tưởng mất tin nhắn, nên phải đi hết `next_cursor`.
 *
 * `MAX_MESSAGE_PAGES` là chốt chặn: một con trỏ hỏng không được phép biến việc
 * mở lại hội thoại thành vòng lặp gọi API vô tận.
 */
export async function fetchAllConversationMessages(
  sessionId: string,
): Promise<ConversationMessagePage["items"]> {
  const collected: Array<{ message_id: string; role: string; content: string; created_at: string }> = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_MESSAGE_PAGES; page += 1) {
    const result = await fetchConversationMessages(sessionId, { limit: 100, cursor });
    collected.push(...result.items);
    if (!result.next_cursor) break;
    cursor = result.next_cursor;
  }
  return collected;
}

export function fetchConversations(): Promise<{ items: readonly ConversationSummary[] }> {
  return request<{ items: readonly ConversationSummary[] }>("/conversations");
}

export function fetchCustomerConversations(): Promise<readonly ConversationSummary[]> {
  return fetchConversations().then((res) => res.items);
}

export function fetchConversation(conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`/conversations/${conversationId}`);
}

export function deleteConversation(conversationId: string): Promise<void> {
  return request<void>(`/conversations/${conversationId}`, { method: "DELETE" });
}

export interface AdvisorConversationDetail {
  conversation_id: string;
  customer_id: string;
  customer_display?: string | null;
  status: string;
  hitl_priority?: string | null;
  hitl_reasons: string[];
  last_message_preview: string;
  last_activity_at: string;
  assigned_advisor_id?: string | null;
  /** AI | PENDING_HANDOFF | HUMAN (Phase 3). */
  ownership?: string;
  /** Độ nóng của khách — chỉ có khi cờ `customer360_ui` bật (Phase 4). */
  heat_band?: "HOT" | "WARM" | "COLD" | null;
  /** Nhãn rào cản đã ghi nhận trong phiên (Phase 4). */
  bottlenecks?: readonly string[];
  messages: Array<{
    message_id?: string;
    sender_type: "CUSTOMER" | "AGENT" | "ADVISOR" | "SYSTEM";
    content: string;
    created_at: string;
  }>;
  current_summary?: string | null;
  slots?: Record<string, unknown>;
  ai_summary?: Record<string, unknown> | null;
}

export function fetchAdvisorConversation(conversationId: string): Promise<AdvisorConversationDetail> {
  return request<AdvisorConversationDetail>(`/advisor/conversations/${conversationId}`);
}

export function sendAdvisorMessage(
  conversationId: string,
  content: string,
): Promise<{ message_id: string; created_at: string }> {
  return request<{ message_id: string; created_at: string }>(`/advisor/conversations/${conversationId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function closeAdvisorConversation(conversationId: string): Promise<{ closed: boolean }> {
  return request<{ closed: boolean }>(`/advisor/conversations/${conversationId}/close`, {
    method: "POST",
  });
}

export function deleteAdvisorConversation(conversationId: string): Promise<{ deleted: boolean }> {
  return request<{ deleted: boolean }>(`/advisor/conversations/${conversationId}`, {
    method: "DELETE",
  });
}

/** TVV nhận phiên AI đang giữ (`POST /advisor/conversations/{id}/join`) — 409 khi đã có người nhận/đã đóng. */
export function joinAdvisorConversation(conversationId: string): Promise<{ joined: boolean; conversation_id: string }> {
  return request(`/advisor/conversations/${conversationId}/join`, { method: "POST" });
}

export function handoffAdvisorConversation(conversationId: string): Promise<{ released: boolean }> {
  return request<{ released: boolean }>(`/advisor/conversations/${conversationId}/handoff`, {
    method: "POST",
  });
}

export function listAdvisorConversations(customerId?: string): Promise<{ items: readonly AdvisorConversationDetail[] }> {
  const query = customerId ? `?customer_id=${encodeURIComponent(customerId)}` : "";
  return request<{ items: readonly AdvisorConversationDetail[] }>(`/advisor/conversations${query}`);
}

export type TurnTraceStats = {
  readonly total: number;
  readonly with_intent: number;
  readonly coverage_pct: number;
  readonly tier_counts: Record<string, number>;
  readonly histogram: Record<string, number>;
};

/** Vệt quyết định một lượt. `payload` là phần trả lời câu "vì sao". */
export type TurnTrace = {
  readonly trace_id: string;
  readonly session_id: string;
  readonly created_at: string;
  readonly user_message: string;
  readonly intent_hint: string | null;
  readonly confidence: number | null;
  readonly tier: string | null;
  readonly scope_label: string | null;
  readonly terminal_reason: string | null;
  readonly routing_enabled: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly payload: Record<string, any>;
};

export function fetchTurnTraceStats(hours: number): Promise<TurnTraceStats> {
  return request<TurnTraceStats>(`/agent/turn-traces/stats?hours=${hours}`);
}

export function fetchTurnTraces(
  options: Readonly<{ hours: number; limit?: number; tier?: string }>,
): Promise<{ items: readonly TurnTrace[] }> {
  const query = new URLSearchParams({ hours: String(options.hours) });
  if (options.limit) query.set("limit", String(options.limit));
  if (options.tier) query.set("tier", options.tier);
  return request<{ items: readonly TurnTrace[] }>(`/agent/turn-traces?${query.toString()}`);
}

// ---------------------------------------------------------------- Customer 360 (plan Phase 4)

export type Customer360Meta = {
  readonly enabled: {
    readonly ui: boolean;
    readonly attach: boolean;
    readonly extractor: boolean;
    readonly offer_rules?: boolean;
    readonly offer_lifecycle?: boolean;
  };
  readonly stages?: readonly SalesStage[];
  readonly heat_thresholds?: { readonly hot: number; readonly warm: number };
  readonly heat_version?: string;
};

/** Cờ + enum của backend. Lỗi (chưa đăng nhập, backend cũ) → coi như TẮT, dùng màn dự phòng. */
export async function fetchCustomer360Meta(): Promise<Customer360Meta> {
  try {
    return await request<Customer360Meta>("/agent/customer-360/meta");
  } catch {
    return { enabled: { ui: false, attach: false, extractor: false } };
  }
}

/** Khách vừa lưu hồ sơ: chép ngay tên/SĐT/địa chỉ sang phía tư vấn viên (plan §19). */
export function refreshCustomerIdentity(): Promise<{ refreshed: boolean }> {
  return request("/agent/customer-360/identity/refresh", { method: "POST" });
}

export function fetchCustomerOverview(customerId: string, role: ViewerRole): Promise<CustomerOverview> {
  const base = role === "admin" ? "/admin" : "/advisor";
  return request<CustomerOverview>(`${base}/customers/${encodeURIComponent(customerId)}/overview`);
}

export function moveSessionOpportunity(
  sessionId: string,
  body: { readonly action: "SPLIT" } | { readonly action: "MOVE"; readonly opportunity_id: string },
): Promise<{ session_id: string; opportunity_id: string; decided_by: "ADVISOR" }> {
  return request(`/advisor/sessions/${sessionId}/opportunity`, { method: "POST", body: JSON.stringify(body) });
}

export async function sendInsightFeedback(insightId: string, verdict: "WRONG" | "OK", note?: string): Promise<void> {
  await request(`/advisor/insights/${insightId}/feedback`, {
    method: "POST",
    body: JSON.stringify({ verdict, note: note ?? null }),
  });
}

export type OpportunityListItem = {
  readonly opportunity_id: string;
  readonly customer_id: string;
  readonly display_name: string | null;
  readonly assigned_advisor_id: string | null;
  readonly vehicle_type: string | null;
  readonly buyer_for: BuyerFor;
  readonly status: OpportunityStatus;
  readonly stage: SalesStage;
  readonly heat_score: number;
  readonly heat_band: HeatBand;
  readonly slots: Record<string, unknown>;
  readonly barriers: readonly string[];
  readonly needs_review: boolean;
  readonly last_seen_at: string;
  // Màn "Khách cần xử lý" — backend cũ không trả thì coi như chưa có.
  readonly sessions_count?: number;
  readonly has_phone?: boolean;
  /** Khách đang chờ người thật. */
  readonly waiting?: boolean;
  readonly has_test_drive?: boolean;
  readonly top_vehicle_name?: string | null;
  readonly next_action?: { readonly code: string; readonly label: string } | null;
};

export type OpportunityFilters = {
  readonly band?: HeatBand;
  readonly waiting?: boolean;
  readonly hasTestDrive?: boolean;
  readonly limit?: number;
};

export function fetchOpportunities(options: OpportunityFilters = {}): Promise<readonly OpportunityListItem[]> {
  const query = new URLSearchParams();
  if (options.band) query.set("band", options.band);
  if (options.waiting) query.set("waiting", "true");
  if (options.hasTestDrive) query.set("has_test_drive", "true");
  if (options.limit) query.set("limit", String(options.limit));
  const qs = query.toString();
  return request<readonly OpportunityListItem[]>(`/advisor/opportunities${qs ? `?${qs}` : ""}`);
}

/**
 * Một khách đang phụ trách (tab "Đã nhận", plan §20) — xuất phát từ PHÂN CÔNG nên khách chưa có
 * nhu cầu (chưa chat) vẫn có mặt; khi đó các trường cơ hội là `null`.
 */
export type MyCustomerItem = {
  readonly customer_id: string;
  readonly display_name: string | null;
  readonly email: string | null;
  readonly assigned_at: string | null;
  readonly opportunity_id: string | null;
  readonly vehicle_type: string | null;
  readonly stage: SalesStage | null;
  readonly heat_score: number | null;
  readonly heat_band: HeatBand | null;
  readonly slots: Record<string, unknown>;
  readonly barriers: readonly string[];
  readonly needs_review: boolean;
  readonly last_seen_at: string | null;
  readonly sessions_count: number;
  readonly has_phone: boolean;
  readonly waiting: boolean;
  readonly has_test_drive: boolean;
  readonly top_vehicle_name: string | null;
  readonly next_action: { readonly code: string; readonly label: string } | null;
};

export function fetchMyCustomers(options: OpportunityFilters = {}): Promise<readonly MyCustomerItem[]> {
  const query = new URLSearchParams();
  if (options.band) query.set("band", options.band);
  if (options.waiting) query.set("waiting", "true");
  if (options.hasTestDrive) query.set("has_test_drive", "true");
  if (options.limit) query.set("limit", String(options.limit));
  const qs = query.toString();
  return request<readonly MyCustomerItem[]>(`/advisor/customers/mine${qs ? `?${qs}` : ""}`);
}

/** Bốn thẻ số đầu màn "Khách cần xử lý" — cùng phạm vi TVV với danh sách. */
export type OpportunitySummary = {
  readonly hot: number;
  readonly waiting: number;
  readonly test_drives_48h: number;
  readonly unanswered: number;
};

export function fetchOpportunitySummary(): Promise<OpportunitySummary> {
  return request<OpportunitySummary>("/advisor/opportunities/summary");
}

export type Customer360Metrics = {
  readonly stages: Partial<Record<SalesStage, number>>;
  readonly heat: Partial<Record<HeatBand, number>>;
  readonly barriers: readonly { readonly code: string; readonly count: number }[];
  readonly workload: readonly {
    readonly advisor_id: string;
    readonly customers: number;
    readonly hot_customers: number;
    readonly waiting_sessions: number;
  }[];
  readonly totals: {
    readonly conversations: number;
    readonly customers: number;
    readonly open_opportunities: number;
    readonly test_drives: number;
    readonly needs_review: number;
  };
  readonly offers?: readonly { readonly status: string; readonly count: number }[];
};

export function fetchCustomer360Metrics(windowDays = 30): Promise<Customer360Metrics> {
  return request<Customer360Metrics>(`/admin/customer-360/metrics?window=${windowDays}`);
}

/** Khách chưa ai phụ trách — tư vấn viên tự nhận (thay màn phân công của Admin). SĐT đã che. */
export type CustomerPoolItem = {
  readonly customer_id: string;
  readonly display_name: string | null;
  readonly phone: string | null;
  /** Đã che (`mi***@gmail.com`) — khách mới đăng nhập chưa khai tên vẫn nhận ra được. */
  readonly email?: string | null;
  readonly sessions_count: number;
  readonly last_seen_at: string | null;
  /** Khách đang chờ người thật. */
  readonly waiting: boolean;
  readonly heat_band: HeatBand | null;
  readonly heat_score: number | null;
  readonly stage: SalesStage | null;
  readonly slots: Record<string, unknown>;
};

export function fetchCustomerPool(limit = 100): Promise<readonly CustomerPoolItem[]> {
  return request<readonly CustomerPoolItem[]>(`/advisor/customers/pool?limit=${limit}`);
}

/** Nhận khách từ hàng chờ — 409 khi tư vấn viên khác đã nhận trước. */
export function claimCustomer(customerId: string): Promise<{ outcome: "CLAIMED" | "ALREADY_MINE"; customer_id: string }> {
  return request(`/advisor/customers/${encodeURIComponent(customerId)}/claim`, { method: "POST" });
}

/** Trả khách về hàng chờ — chỉ người đang phụ trách. */
export function releaseCustomer(customerId: string): Promise<{ released: boolean }> {
  return request(`/advisor/customers/${encodeURIComponent(customerId)}/release`, { method: "POST" });
}

export type ExtractionQuality = {
  readonly insights_total: number;
  readonly insights_reported_wrong: number;
  readonly by_field: readonly { readonly field: string; readonly total: number; readonly wrong: number }[];
  readonly attach_total: number;
  readonly attach_by_decider: Record<string, number>;
  readonly corrected_by_decider: Record<string, number>;
  readonly samples: readonly {
    readonly insight_id: string;
    readonly field: string;
    readonly value: string;
    readonly evidence_quote: string;
    readonly note: string | null;
    readonly created_at: string;
  }[];
};

export function fetchExtractionQuality(windowDays = 30): Promise<ExtractionQuality> {
  return request<ExtractionQuality>(`/admin/customer-360/extraction-quality?window=${windowDays}`);
}
