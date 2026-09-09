/**
 * API client cho lịch lái thử của khách hàng đang đăng nhập.
 *
 * Đọc qua endpoint riêng cho khách `GET /agent/bookings/me` (khác
 * `/agent/bookings` — endpoint đó yêu cầu `require_staff`, chỉ dành cho
 * ADVISOR/ADMIN).
 *
 * KHÔNG có `cancelBooking`: `POST /agent/bookings/{id}/cancel` yêu cầu
 * `require_staff` (`src/agents/api/booking_routes.py`, hàm `cancel_booking`
 * dùng `Depends(require_staff)`), tức chỉ ADVISOR/ADMIN được huỷ — khách hàng
 * gọi sẽ nhận 403. Màn khách chỉ hiển thị, không có nút huỷ.
 */

import { csrfHeader, withSessionRetry } from "@/lib/api/session";
import type { BookingListItem } from "@/types/bookings";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export class BookingApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
  ) {
    super(code);
    this.name = "BookingApiError";
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
    throw new BookingApiError(
      typeof detail === "string" ? detail : "request_failed",
      response.status,
    );
  }
  return body as T;
}

export function fetchMyBookings(): Promise<BookingListItem[]> {
  return request<BookingListItem[]>("/agent/bookings/me");
}
