/**
 * API client for Admin Assignment Center, Conversation Reassignment, and Live Analytics.
 */

import { csrfHeader, withSessionRetry } from "@/lib/api/session";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export class AssignmentApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
    this.name = "AssignmentApiError";
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
    const detail = (body as { detail?: unknown }).detail;
    throw new AssignmentApiError(
      typeof detail === "string" ? detail : "request_failed",
      response.status,
    );
  }
  return body as T;
}

export interface CustomerAssignment {
  assignment_id: string;
  customer_id: string;
  advisor_id: string;
  assigned_by: string;
  reason?: string | null;
  status: string;
  assigned_at: string;
  unassigned_at?: string | null;
  created_at: string;
}

export interface CustomerAssignmentsResponse {
  items: CustomerAssignment[];
  total: number;
  page: number;
  page_size: number;
}

export interface AssignmentHistoryItem {
  assignment_id: string;
  advisor_id: string;
  assigned_by: string;
  reason?: string | null;
  status: string;
  assigned_at: string;
  unassigned_at?: string | null;
}

export interface AssignedCustomerItem {
  customer_id: string;
  advisor_id: string;
  assigned_at: string;
  reason?: string | null;
  status: string;
  profile_payload: Record<string, unknown>;
  active_conversations_count: number;
  last_activity_at?: string | null;
}

export interface DashboardMetrics {
  total_conversations: number;
  completed_profiles: number;
  approved_reviews: number;
  total_bookings: number;
  funnel: Array<{ label: string; value: number; percent: number }>;
  quality_stats: {
    approved_original_pct: number;
    edited_pct: number;
    rejected_pct: number;
  };
}

export function fetchAssignments(params?: {
  advisorId?: string;
  status?: string;
  page?: number;
  pageSize?: number;
}): Promise<CustomerAssignmentsResponse> {
  const query = new URLSearchParams();
  if (params?.advisorId) query.set("advisor_id", params.advisorId);
  if (params?.status) query.set("status", params.status);
  if (params?.page) query.set("page", String(params.page));
  if (params?.pageSize) query.set("page_size", String(params.pageSize));

  const qs = query.toString();
  return request<CustomerAssignmentsResponse>(`/admin/customers/assignments${qs ? `?${qs}` : ""}`);
}

export function assignCustomer(
  customerId: string,
  advisorId: string,
  reason?: string,
): Promise<{ assignment_id: string; customer_id: string; advisor_id: string; status: string }> {
  return request(`/admin/customers/${customerId}/assign`, {
    method: "POST",
    body: JSON.stringify({ advisor_id: advisorId, reason: reason ?? null }),
  });
}

export function unassignCustomer(
  customerId: string,
  reason?: string,
): Promise<{ customer_id: string; status: string; unassigned: boolean }> {
  return request(`/admin/customers/${customerId}/unassign`, {
    method: "POST",
    body: JSON.stringify({ reason: reason ?? null }),
  });
}

export function fetchAssignmentHistory(
  customerId: string,
): Promise<{ customer_id: string; items: AssignmentHistoryItem[] }> {
  return request(`/admin/customers/${customerId}/assignment-history`);
}

export function fetchAvailableCustomers(): Promise<Array<{ customer_id: string; display_name: string; phone?: string; email?: string }>> {
  return request("/admin/customers/available");
}

export function reassignConversation(
  conversationId: string,
  advisorId: string,
  reason?: string,
): Promise<{ session_id: string; previous_advisor_id?: string; new_advisor_id: string; reassigned: boolean }> {
  return request(`/admin/conversations/${conversationId}/reassign`, {
    method: "POST",
    body: JSON.stringify({ advisor_id: advisorId, reason: reason ?? null }),
  });
}

export function fetchAdvisorCustomers(advisorId?: string): Promise<{ items: AssignedCustomerItem[] }> {
  const qs = advisorId ? `?advisor_id=${encodeURIComponent(advisorId)}` : "";
  return request<{ items: AssignedCustomerItem[] }>(`/advisor/customers${qs}`);
}

export function fetchAdminDashboardMetrics(): Promise<DashboardMetrics> {
  return request<DashboardMetrics>("/admin/analytics/dashboard");
}

/** Thông báo nội bộ cho tư vấn viên — khớp `NoticeResponse` (`src/agents/api/schemas.py`). */
export type NoticeItem = {
  readonly notice_id: string;
  readonly title: string;
  readonly content: string;
  readonly priority: string;
  readonly created_at: string;
  readonly read: boolean;
};

export function fetchNoticeList(): Promise<readonly NoticeItem[]> {
  return request<readonly NoticeItem[]>("/agent/notices");
}

export async function markNoticeRead(noticeId: string): Promise<void> {
  await request(`/agent/notices/${encodeURIComponent(noticeId)}/read`, { method: "POST" });
}

export interface BookingVehicleOption {
  id: string;
  name: string;
  model: string;
  variant: string;
  vehicle_type: string;
  image_url?: string | null;
}

export interface BookingShowroomOption {
  id: string;
  name: string;
  address: string;
  city: string;
  /** Toạ độ cho bản đồ + sắp theo khoảng cách của form /test-drive; nguồn cũ có thể chưa gửi. */
  lat?: number | null;
  lng?: number | null;
}

export interface BookingOptionsResponse {
  vehicles: BookingVehicleOption[];
  showrooms: BookingShowroomOption[];
}

export interface TestDriveBookingItem {
  booking_id: string;
  customer_id: string;
  customer_name?: string | null;
  phone?: string | null;
  vehicle_id: string;
  vehicle_name?: string;
  advisor_id?: string | null;
  showroom: string;
  scheduled_at: string;
  status: string;
  created_at: string;
}

export function fetchBookingOptions(): Promise<BookingOptionsResponse> {
  return request<BookingOptionsResponse>("/agent/bookings/options");
}

export function createTestDriveBooking(payload: {
  vehicle_id: string;
  showroom: string;
  scheduled_at: string;
  customer_name?: string;
  phone?: string;
  customer_id?: string;
}): Promise<{ booking_id: string }> {
  return request<{ booking_id: string }>("/agent/bookings", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function fetchTestDriveBookings(statusFilter?: string): Promise<TestDriveBookingItem[]> {
  const qs = statusFilter ? `?status_filter=${encodeURIComponent(statusFilter)}` : "";
  return request<TestDriveBookingItem[]>(`/agent/bookings${qs}`);
}

export function confirmTestDriveBooking(bookingId: string): Promise<{ confirmed: boolean }> {
  return request<{ confirmed: boolean }>(`/agent/bookings/${bookingId}/confirm`, {
    method: "POST",
  });
}

export function cancelTestDriveBooking(bookingId: string): Promise<{ cancelled: boolean }> {
  return request<{ cancelled: boolean }>(`/agent/bookings/${bookingId}/cancel`, {
    method: "POST",
  });
}

export interface CustomerActivity {
  id: string;
  kind: "session" | "booking" | "comparison";
  date: string;
  title: string;
  description: string;
  status: string;
  tone: "success" | "warning" | "neutral" | "danger";
  icon: "message" | "calendar" | "file";
}

export interface CustomerAccountSummary {
  session_count: number;
  booking_count: number;
  comparison_count: number;
  approved_recommendations_count: number;
  activities: CustomerActivity[];
}

export function fetchCustomerSummary(): Promise<CustomerAccountSummary> {
  return request<CustomerAccountSummary>("/agent/customer/summary");
}

