/**
 * Nạp hồ sơ khách 360 cho trang `/advisor/customers/[id]` và `/admin/customers/[id]`.
 *
 * Một cửa duy nhất cho component: `loadCustomerProfile` trả `CustomerProfileView` bất
 * kể dữ liệu đến từ đâu.
 *
 * - `source: "fallback"` (Phase 2, và mọi lúc cờ `customer360_ui` TẮT): ghép từ các
 *   endpoint đã có — danh sách phiên, lịch lái thử, phân công. Chưa có cơ hội/độ nóng;
 *   nhu cầu lấy từ slot phiên gần nhất.
 * - `source: "overview"` (Phase 4): một lần gọi `GET /advisor/customers/{id}/overview`.
 */

import type { OpportunityCardData } from "@/components/customer360/opportunity-card";
import {
  type AdvisorConversationDetail,
  fetchCustomer360Meta,
  fetchCustomerOverview,
  listAdvisorConversations,
} from "@/lib/api/agent";
import {
  type AssignedCustomerItem,
  fetchAdvisorCustomers,
  fetchAssignmentHistory,
  fetchTestDriveBookings,
  type TestDriveBookingItem,
} from "@/lib/api/assignments";
import type { CustomerOverview, SessionRow, TestDriveItem, ViewerRole } from "@/types/customer360";

import type { CustomerSummaryData } from "@/components/customer360/customer-summary";

export type CustomerProfileView = {
  readonly source: "fallback" | "overview";
  /** Cờ ưu đãi (Phase 5): `rules` → "Ưu đãi phù hợp"; `lifecycle` → tab "Ưu đãi đã cấp". */
  readonly offers: { readonly rules: boolean; readonly lifecycle: boolean };
  readonly header: CustomerSummaryData;
  readonly opportunities: readonly (OpportunityCardData & { readonly id: string })[];
  readonly sessions: readonly SessionRow[];
  readonly testDrives: readonly TestDriveItem[];
  /** Thông tin tầng Khách (tỉnh, thanh toán…) — chỉ có khi đọc từ `/overview`. */
  readonly fields?: CustomerOverview["customer"]["fields"];
  /** Phiên nên mở khi bấm "Vào chat"/"Tiếp quản" — phiên chờ TVV trước, rồi phiên mới nhất chưa đóng. */
  readonly focusSessionId: string | null;
  readonly waitingSessionId: string | null;
};

/** Không truy cập được hồ sơ (ngoài phạm vi phân công, hoặc không tồn tại). */
export class CustomerProfileUnavailableError extends Error {
  constructor() {
    super("customer_profile_unavailable");
    this.name = "CustomerProfileUnavailableError";
  }
}

/**
 * Chuyển một dòng `/advisor/conversations` sang `SessionRow`. Trước Phase 4 chưa có
 * bảng gắn phiên–cơ hội nên `kind` là `UNASSIGNED` và các cột gắn cơ hội để trống.
 */
export function sessionRowFromConversation(item: AdvisorConversationDetail): SessionRow {
  const status = item.status?.toUpperCase();
  return {
    session_id: item.conversation_id,
    started_at: null,
    last_activity_at: item.last_activity_at,
    status: status === "WAITING_ADVISOR" ? "WAITING_ADVISOR" : status === "COMPLETED" || status === "CLOSED" ? "CLOSED" : "ACTIVE",
    kind: "UNASSIGNED",
    opportunity_id: null,
    needs_review: false,
    decided_by: null,
    turn_count: null,
    summary_excerpt: item.last_message_preview || null,
  };
}

function newest<T>(items: readonly T[], at: (item: T) => string): T | undefined {
  return [...items].sort((a, b) => at(b).localeCompare(at(a)))[0];
}

function toTestDrive(item: TestDriveBookingItem): TestDriveItem {
  return {
    booking_id: item.booking_id,
    vehicle_id: item.vehicle_name || item.vehicle_id,
    showroom: item.showroom,
    scheduled_at: item.scheduled_at,
    status: item.status,
  };
}

/** Slot của phiên gần nhất có slot — nguồn nhu cầu duy nhất trước khi có bảng cơ hội. */
export function latestSlots(conversations: readonly AdvisorConversationDetail[]): Record<string, unknown> | undefined {
  return newest(
    conversations.filter((item) => item.slots && Object.keys(item.slots).length > 0),
    (item) => item.last_activity_at,
  )?.slots;
}

function fallbackTitle(slots: Record<string, unknown> | undefined): string {
  const type = slots?.vehicle_type;
  if (type === "CAR") return "Nhu cầu ô tô điện";
  if (type === "ELECTRIC_MOTORBIKE") return "Nhu cầu xe máy điện";
  return "Nhu cầu hiện tại";
}

async function loadAssignment(customerId: string, role: ViewerRole): Promise<AssignedCustomerItem | { advisor_id: string } | null> {
  if (role === "admin") {
    const history = await fetchAssignmentHistory(customerId).catch(() => null);
    const active = history?.items.find((item) => item.status === "ACTIVE");
    return active ? { advisor_id: active.advisor_id } : null;
  }
  const mine = await fetchAdvisorCustomers().catch(() => null);
  return mine?.items.find((item) => item.customer_id === customerId) ?? null;
}

async function loadFallback(customerId: string, role: ViewerRole): Promise<CustomerProfileView> {
  const [conversations, bookings, assignment] = await Promise.all([
    listAdvisorConversations(customerId).then((response) => response.items || []),
    fetchTestDriveBookings()
      .then((items) => items.filter((item) => item.customer_id === customerId))
      .catch(() => [] as TestDriveBookingItem[]),
    loadAssignment(customerId, role),
  ]);
  // Backend chỉ trả phiên trong phạm vi người xem (Phase 0): không phiên, không phân công
  // thì coi như hồ sơ ngoài phạm vi thay vì dựng một trang rỗng gây hiểu lầm.
  if (conversations.length === 0 && assignment === null && role === "advisor") {
    throw new CustomerProfileUnavailableError();
  }

  const profile = assignment && "profile_payload" in assignment ? assignment.profile_payload : {};
  const latest = newest(conversations, (item) => item.last_activity_at);
  const booking = bookings[0];
  const slots = latestSlots(conversations);
  const sessions = conversations.map(sessionRowFromConversation);
  const waiting = sessions.find((item) => item.status === "WAITING_ADVISOR");
  const open = newest(
    sessions.filter((item) => item.status !== "CLOSED"),
    (item) => item.last_activity_at,
  );

  return {
    source: "fallback",
    offers: { rules: false, lifecycle: false },
    header: {
      customer_id: customerId,
      display_name:
        (profile.name as string | undefined) || latest?.customer_display || booking?.customer_name || null,
      // Danh sách phân công đã che SĐT ở backend; SĐT đầy đủ chỉ có qua `/overview` (Phase 4).
      phone_masked: (profile.phone as string | undefined) || null,
      assigned_advisor_id: assignment?.advisor_id ?? null,
      sessions_count: conversations.length,
      last_seen_at: latest?.last_activity_at ?? null,
    },
    opportunities: [{ id: "current", title: fallbackTitle(slots), slots: slots ?? {}, barriers: [] }],
    sessions,
    testDrives: bookings.map(toTestDrive),
    focusSessionId: waiting?.session_id ?? open?.session_id ?? null,
    waitingSessionId: waiting?.session_id ?? null,
  };
}

const VEHICLE_TITLES: Record<string, string> = { CAR: "Ô tô điện", ELECTRIC_MOTORBIKE: "Xe máy điện" };

/** `/overview` → cùng hình dữ liệu với màn dự phòng, để component không phải biết hai nguồn. */
export function profileFromOverview(
  overview: CustomerOverview,
  offers: CustomerProfileView["offers"] = { rules: false, lifecycle: false },
): CustomerProfileView {
  const sessions = overview.sessions;
  const waiting = sessions.find((item) => item.status === "WAITING_ADVISOR");
  const open = newest(
    sessions.filter((item) => item.status !== "CLOSED"),
    (item) => item.last_activity_at,
  );
  return {
    source: "overview",
    offers,
    header: {
      customer_id: overview.customer.customer_id,
      display_name: overview.customer.display_name,
      phone_masked: overview.customer.phone_masked,
      phone: overview.customer.phone,
      assigned_advisor_id: overview.customer.assigned_advisor_id,
      sessions_count: overview.customer.sessions_count,
      last_seen_at: overview.customer.last_seen_at,
      heat_band: overview.customer.heat_band,
      heat_score: overview.customer.heat_score,
    },
    fields: overview.customer.fields,
    opportunities: overview.opportunities.map((opportunity) => ({
      id: opportunity.opportunity_id,
      title: VEHICLE_TITLES[opportunity.vehicle_type ?? ""] ?? "Nhu cầu chưa rõ loại xe",
      buyerFor: opportunity.buyer_for,
      stage: opportunity.stage,
      status: opportunity.status,
      heatBand: opportunity.heat_band,
      heatScore: opportunity.heat_score,
      heatBreakdown: opportunity.heat_breakdown,
      slots: Object.fromEntries(opportunity.needs.known.map((item) => [item.slot, item.value])),
      history: Object.fromEntries(opportunity.needs.known.map((item) => [item.slot, item.history])),
      missing: opportunity.needs.missing,
      evaded: opportunity.needs.evaded,
      barriers: opportunity.barriers,
      insights: opportunity.insights,
      openingHint: opportunity.opening_hint,
      nextActions: opportunity.next_actions,
    })),
    sessions,
    testDrives: overview.test_drives,
    focusSessionId: waiting?.session_id ?? open?.session_id ?? null,
    waitingSessionId: waiting?.session_id ?? null,
  };
}

/** Cờ `customer360_ui` bật → một lần gọi `/overview`; tắt → ghép từ endpoint cũ (Phase 2). */
export async function loadCustomerProfile(customerId: string, role: ViewerRole): Promise<CustomerProfileView> {
  const meta = await fetchCustomer360Meta();
  if (!meta.enabled.ui) return loadFallback(customerId, role);
  return profileFromOverview(await fetchCustomerOverview(customerId, role), {
    rules: Boolean(meta.enabled.offer_rules),
    lifecycle: Boolean(meta.enabled.offer_lifecycle),
  });
}

