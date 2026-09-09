"use client";

import { AlertCircle, CalendarDays, CheckCircle2, Clock3, Inbox, LoaderCircle, Phone, RefreshCw, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { MetricCard } from "@/components/shared/metric-card";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  cancelTestDriveBooking,
  confirmTestDriveBooking,
  fetchTestDriveBookings,
  type TestDriveBookingItem,
} from "@/lib/api/assignments";

export default function AdvisorTestDrivesPage() {
  const [bookings, setBookings] = useState<TestDriveBookingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorText, setErrorText] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setErrorText("");
    try {
      const data = await fetchTestDriveBookings();
      setBookings(data);
    } catch {
      setErrorText("Không thể tải danh sách lịch lái thử từ cơ sở dữ liệu.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleConfirm = async (bookingId: string) => {
    setActionLoading(bookingId);
    try {
      await confirmTestDriveBooking(bookingId);
      await reload();
    } catch {
      alert("Không thể xác nhận lịch hẹn.");
    } finally {
      setActionLoading(null);
    }
  };

  const handleCancel = async (bookingId: string) => {
    if (!confirm("Bạn có chắc muốn hủy lịch lái thử này?")) return;
    setActionLoading(bookingId);
    try {
      await cancelTestDriveBooking(bookingId);
      await reload();
    } catch {
      alert("Không thể hủy lịch hẹn.");
    } finally {
      setActionLoading(null);
    }
  };

  function formatDate(val: string): string {
    return new Intl.DateTimeFormat("vi-VN", {
      dateStyle: "full",
      timeStyle: "short",
    }).format(new Date(val));
  }

  const requestedCount = useMemo(() => bookings.filter((b) => b.status === "REQUESTED").length, [bookings]);
  const confirmedCount = useMemo(() => bookings.filter((b) => b.status === "CONFIRMED").length, [bookings]);
  const cancelledCount = useMemo(() => bookings.filter((b) => b.status === "CANCELLED").length, [bookings]);

  const filteredBookings = useMemo(() => {
    if (filterStatus === "ALL") return bookings;
    return bookings.filter((b) => b.status === filterStatus);
  }, [bookings, filterStatus]);

  return (
    <OperationalShell role="advisor">
      <PageHeading
        description="Quản lý, điều phối và xác nhận lịch hẹn lái thử xe tại Showroom của khách hàng (Dữ liệu PostgreSQL)."
        eyebrow="Advisor / Showroom"
        title="Yêu cầu lái thử"
      />

      <div className="metric-grid advisor-metrics">
        <MetricCard label="Tổng yêu cầu" note="Tất cả các lượt đăng ký" value={String(bookings.length)} />
        <MetricCard label="Chờ xác nhận" note="Cần tư vấn viên liên hệ" value={String(requestedCount)} />
        <MetricCard label="Đã xác nhận" note="Đã xếp xe & showroom" value={String(confirmedCount)} />
        <MetricCard label="Đã hủy" note="Khách hủy hoặc dời lịch" value={String(cancelledCount)} />
      </div>

      <section className="ops-panel">
        <div className="ops-panel-heading">
          <div className="flex items-center gap-3">
            <h2>Danh sách đăng ký lái thử</h2>
            <div className="filter-pill-group flex gap-1 bg-slate-100 dark:bg-slate-800 p-1 rounded-lg text-xs">
              <button
                className={`px-2.5 py-1 rounded-md transition font-medium ${filterStatus === "ALL" ? "bg-white dark:bg-slate-700 shadow-sm text-blue-600 dark:text-blue-400 font-semibold" : "text-slate-600 dark:text-slate-300"}`}
                onClick={() => setFilterStatus("ALL")}
                type="button"
              >
                Tất cả ({bookings.length})
              </button>
              <button
                className={`px-2.5 py-1 rounded-md transition font-medium ${filterStatus === "REQUESTED" ? "bg-white dark:bg-slate-700 shadow-sm text-amber-600 font-semibold" : "text-slate-600 dark:text-slate-300"}`}
                onClick={() => setFilterStatus("REQUESTED")}
                type="button"
              >
                Chờ xác nhận ({requestedCount})
              </button>
              <button
                className={`px-2.5 py-1 rounded-md transition font-medium ${filterStatus === "CONFIRMED" ? "bg-white dark:bg-slate-700 shadow-sm text-emerald-600 font-semibold" : "text-slate-600 dark:text-slate-300"}`}
                onClick={() => setFilterStatus("CONFIRMED")}
                type="button"
              >
                Đã xác nhận ({confirmedCount})
              </button>
            </div>
          </div>
          <button
            className="secondary-button"
            disabled={loading}
            onClick={() => void reload()}
            title="Làm mới"
            type="button"
          >
            <RefreshCw className={loading ? "animate-spin" : ""} size={14} /> Làm mới
          </button>
        </div>

        {errorText ? (
          <div className="ops-state py-8">
            <AlertCircle className="text-amber-500" size={28} />
            <p className="text-sm text-slate-600 dark:text-slate-300">{errorText}</p>
            <button className="primary-button mt-2" onClick={() => void reload()} type="button">
              Thử lại
            </button>
          </div>
        ) : null}

        {loading ? (
          <div className="ops-state py-12">
            <LoaderCircle className="spin text-blue-600" size={28} />
            <p className="text-sm text-slate-500">Đang tải lịch lái thử từ PostgreSQL...</p>
          </div>
        ) : null}

        {!loading && !errorText && filteredBookings.length === 0 ? (
          <div className="ops-state py-12">
            <Inbox className="text-slate-400" size={32} />
            <h3>Không có yêu cầu lái thử nào</h3>
            <p className="text-xs text-slate-500">
              {filterStatus === "ALL"
                ? "Chưa có lượt đăng ký lái thử nào trong cơ sở dữ liệu."
                : `Không có yêu cầu nào ở trạng thái "${filterStatus}".`}
            </p>
          </div>
        ) : null}

        {!loading && !errorText && filteredBookings.length > 0 ? (
          <div className="booking-request-list">
            {filteredBookings.map((booking) => {
              const isConfirmed = booking.status === "CONFIRMED";
              const isCancelled = booking.status === "CANCELLED";
              const isActing = actionLoading === booking.booking_id;

              return (
                <article key={booking.booking_id}>
                  <span
                    className={
                      isConfirmed
                        ? "booking-state-icon is-confirmed"
                        : isCancelled
                          ? "booking-state-icon is-cancelled opacity-50"
                          : "booking-state-icon"
                    }
                  >
                    {isConfirmed ? (
                      <CheckCircle2 size={19} />
                    ) : isCancelled ? (
                      <XCircle size={19} />
                    ) : (
                      <Clock3 size={19} />
                    )}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                        {booking.customer_name || booking.customer_id}
                      </h3>
                      {booking.phone ? (
                        <span className="inline-flex items-center gap-1 text-xs text-slate-500 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">
                          <Phone size={11} /> {booking.phone}
                        </span>
                      ) : null}
                    </div>
                    <p className="text-xs text-slate-600 dark:text-slate-300 mt-1">
                      <strong>{booking.vehicle_name || "VinFast EV"}</strong> · {booking.showroom}
                    </p>
                    <span className="text-[11px] text-slate-400 block mt-0.5">
                      Đăng ký lúc: {new Date(booking.created_at).toLocaleString("vi-VN")}
                    </span>
                  </div>
                  <strong>{formatDate(booking.scheduled_at)}</strong>
                  <StatusBadge
                    tone={
                      isConfirmed
                        ? "success"
                        : isCancelled
                          ? "neutral"
                          : "warning"
                    }
                  >
                    {isConfirmed
                      ? "Đã xác nhận"
                      : isCancelled
                        ? "Đã hủy"
                        : "Chờ xác nhận"}
                  </StatusBadge>
                  <div className="flex items-center gap-2">
                    {!isConfirmed && !isCancelled ? (
                      <button
                        className="primary-button text-xs py-1 px-2.5"
                        disabled={isActing}
                        onClick={() => void handleConfirm(booking.booking_id)}
                        type="button"
                      >
                        {isActing ? "Đang xử lý..." : "Xác nhận lịch"}
                      </button>
                    ) : null}
                    {!isCancelled ? (
                      <button
                        className="secondary-button text-xs py-1 px-2.5 text-rose-600 hover:bg-rose-50 border-rose-200 dark:border-rose-900"
                        disabled={isActing}
                        onClick={() => void handleCancel(booking.booking_id)}
                        type="button"
                      >
                        Hủy
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </OperationalShell>
  );
}
