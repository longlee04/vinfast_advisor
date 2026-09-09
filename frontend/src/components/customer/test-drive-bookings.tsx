"use client";

import { AlertCircle, CalendarClock, CarFront, Loader2, MapPin } from "lucide-react";
import Link from "next/link";
import { forwardRef, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { fetchMyBookings } from "@/lib/api/bookings";
import type { BookingListItem, BookingStatus } from "@/types/bookings";

const STATUS_LABEL: Record<BookingStatus, string> = {
  REQUESTED: "Chờ xác nhận",
  CONFIRMED: "Đã xác nhận",
  CANCELLED: "Đã huỷ",
};

const STATUS_TONE: Record<BookingStatus, "success" | "warning" | "danger"> = {
  REQUESTED: "warning",
  CONFIRMED: "success",
  CANCELLED: "danger",
};

/** `HH:mm dd/MM/yyyy` theo giờ Việt Nam, bất kể múi giờ trình duyệt. */
function formatScheduledAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const parts = new Intl.DateTimeFormat("vi-VN", {
    timeZone: "Asia/Ho_Chi_Minh",
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour12: false,
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("day")}/${get("month")}/${get("year")}`;
}

export const TestDriveBookings = forwardRef<HTMLElement>(function TestDriveBookings(_props, ref) {
  const [bookings, setBookings] = useState<BookingListItem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchMyBookings();
      setBookings(data);
    } catch {
      setError("Không tải được lịch lái thử của bạn. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const sorted = [...(bookings ?? [])].sort(
    (a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime(),
  );

  return (
    <section
      ref={ref}
      id="test-drive-bookings"
      tabIndex={-1}
      aria-label="Lịch lái thử của bạn"
      className="mt-5 rounded-xl border border-slate-200 focus:outline-none"
    >
      <div className="history-section-heading">
        <div>
          <h2>Lịch lái thử của bạn</h2>
          <p>Cần đổi lịch hoặc huỷ? Liên hệ tư vấn viên để được hỗ trợ.</p>
        </div>
      </div>
      <div className="history-timeline">
        {loading ? (
          <div className="flex items-center justify-center p-8 text-slate-500 gap-2">
            <Loader2 className="animate-spin text-blue-600" size={18} />
            <span className="text-xs">Đang tải lịch lái thử...</span>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center gap-2 p-6 text-center text-xs text-red-600 bg-red-50 border border-dashed border-red-200 rounded-xl">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        ) : sorted.length === 0 ? (
          <div className="p-6 text-center text-slate-500 bg-slate-50 border border-dashed border-slate-200 rounded-xl text-xs">
            <p className="mb-2">Bạn chưa có lịch lái thử nào.</p>
            {/* Trỏ thẳng form đặt lịch — bắt khách vòng qua màn chat là thêm
                một bước thừa cho một ý định đã rõ. */}
            <Link className="primary-button inline-flex" href="/test-drive">
              Đặt lịch lái thử ngay
            </Link>
          </div>
        ) : (
          sorted.map((booking) => (
            <article key={booking.booking_id}>
              <span className="timeline-icon">
                <CarFront size={18} />
              </span>
              <div>
                <small className="flex items-center gap-1">
                  <CalendarClock size={12} /> {formatScheduledAt(booking.scheduled_at)}
                </small>
                <h3>{booking.vehicle_name}</h3>
                <p className="flex items-center gap-1">
                  <MapPin size={12} /> {booking.showroom}
                </p>
                <StatusBadge tone={STATUS_TONE[booking.status] ?? "neutral"}>
                  {STATUS_LABEL[booking.status] ?? booking.status}
                </StatusBadge>
              </div>
            </article>
          ))
        )}
      </div>
    </section>
  );
});
