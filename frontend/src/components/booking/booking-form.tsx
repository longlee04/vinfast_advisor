"use client";

import { AlertCircle, CalendarDays, CheckCircle2, LoaderCircle, LocateFixed, MapPin, Phone } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { buildScheduledAt, defaultBookingDate } from "@/components/booking/booking-time";
import {
  type BookingShowroomOption,
  type BookingVehicleOption,
  createTestDriveBooking,
  fetchBookingOptions,
} from "@/lib/api/assignments";
import { useAuth } from "@/store/auth-store";
import { useDemoStore } from "@/store/demo-store";

// Bản đồ Leaflet chỉ sống ở client — cùng cách nạp với panel hội thoại. Nạp
// lười: trang chỉ trả chi phí bundle khi thật sự có showroom mang toạ độ.
const TourMap = dynamic(() => import("@/components/consultation/tour-map"), { ssr: false });

const timeSlots = ["08:30", "09:30", "10:30", "13:30", "14:30", "15:30", "16:30"];

/** Khoảng cách đường chim bay (km) — đủ cho việc XẾP GẦN TRƯỚC, không cần đường đi thật. */
function haversineKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLng = (b.lng - a.lng) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

type LatLng = { readonly lat: number; readonly lng: number };

/**
 * Form đặt lịch lái thử của trang /test-drive — làm lại 2026-08-31 theo yêu cầu
 * Sếp: "khách chỉ cần cung cấp vị trí, chọn showroom + chọn lịch + chọn dòng xe".
 *
 * - Chọn XE bằng thẻ CÓ ẢNH (ảnh thật từ `vehicles.image_url`), không còn
 *   dropdown chữ trần.
 * - Vị trí → BẢN ĐỒ: nút xin GPS, showroom sắp theo khoảng cách, ghim trên
 *   cùng `TourMap` của cửa sổ hội thoại — một bản đồ cho cả sản phẩm.
 * - Họ tên/SĐT KHÔNG hỏi lại khi hồ sơ đăng nhập đã có đủ — hai ô đó chỉ hiện
 *   cho khách chưa có thông tin. Đó là hai trường "phải điền quá nhiều" mà
 *   khách đã đưa cho hệ thống từ lúc đăng ký.
 */
export function BookingForm() {
  const router = useRouter();
  const { user, profile } = useAuth();
  const { state, setBookingStatus } = useDemoStore();

  const [vehicles, setVehicles] = useState<BookingVehicleOption[]>([]);
  const [showrooms, setShowrooms] = useState<BookingShowroomOption[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);
  const [optionsError, setOptionsError] = useState(false);

  const [userLoc, setUserLoc] = useState<LatLng | null>(null);
  const [locating, setLocating] = useState(false);
  const [locateFailed, setLocateFailed] = useState(false);

  // "Ngày mai" theo Asia/Ho_Chi_Minh — không theo múi giờ máy (booking-time.ts).
  const defaultDate = useMemo(() => defaultBookingDate(), []);

  const [booking, setBooking] = useState({
    vehicleId: "",
    showroomId: "",
    date: defaultDate,
    timeSlot: "14:30",
    fullName: profile?.full_name || "",
    phone: profile?.phone_number || "",
  });

  const loadOptions = useCallback(() => {
    setLoadingOptions(true);
    setOptionsError(false);
    fetchBookingOptions()
      .then((res) => {
        setVehicles(res.vehicles || []);
        setShowrooms(res.showrooms || []);
        if (res.vehicles.length > 0) {
          setBooking((c) => ({
            ...c,
            vehicleId: c.vehicleId || res.vehicles[0].id,
            showroomId: c.showroomId || (res.showrooms[0]?.id || ""),
          }));
        }
      })
      .catch(() => {
        // Không nuốt lỗi trong im lặng như trước (form trống không lời giải
        // thích): bật khối lỗi + nút thử lại; submit bị khoá vì chưa có xe.
        setOptionsError(true);
      })
      .finally(() => setLoadingOptions(false));
  }, []);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);


  useEffect(() => {
    if (profile?.full_name || profile?.phone_number) {
      // Trả NGUYÊN state khi không có gì để điền: `profile` có thể là object
      // mới mỗi render (store/mock) — luôn spread là setState mới → render mới
      // → vòng lặp vô hạn (vitest treo cả pool 2026-08-31). React bỏ qua
      // setState trả cùng tham chiếu, vòng lặp đứt ở đây.
      setBooking((c) => {
        const fullName = c.fullName || profile?.full_name || "";
        const phone = c.phone || profile?.phone_number || "";
        if (fullName === c.fullName && phone === c.phone) return c;
        return { ...c, fullName, phone };
      });
    }
  }, [profile]);

  // Showroom sắp GẦN TRƯỚC khi đã có vị trí; chưa có thì giữ thứ tự city/name
  // của backend. Showroom thiếu toạ độ xếp cuối chứ không biến mất.
  const sortedShowrooms = useMemo(() => {
    const withDistance = showrooms.map((s) => ({
      ...s,
      distanceKm:
        userLoc && s.lat != null && s.lng != null ? haversineKm(userLoc, { lat: s.lat, lng: s.lng }) : null,
    }));
    if (!userLoc) return withDistance;
    return [...withDistance].sort((a, b) => (a.distanceKm ?? Infinity) - (b.distanceKm ?? Infinity));
  }, [showrooms, userLoc]);

  //: Danh sách bày ra: có vị trí thì 6 điểm gần nhất là đủ chọn; chưa có vị
  //: trí thì 12 điểm đầu — backend giờ trả CẢ nghìn showroom (hết LIMIT 100
  //: cắt mất Hà Nội), đổ hết vào DOM là trang è cổ mà không ai cuộn nghìn thẻ.
  const visibleShowrooms = useMemo(
    () => sortedShowrooms.slice(0, userLoc ? 6 : 12),
    [sortedShowrooms, userLoc],
  );

  const mapShowrooms = useMemo(
    () =>
      visibleShowrooms
        .filter((s) => s.lat != null && s.lng != null)
        .map((s) => ({
          showroom_id: s.id,
          name: s.name,
          address: s.address || s.city,
          lat: s.lat as number,
          lng: s.lng as number,
          distance_km: s.distanceKm,
        })),
    [visibleShowrooms],
  );

  const requestLocation = useCallback(() => {
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocateFailed(true);
      return;
    }
    setLocating(true);
    setLocateFailed(false);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const here = { lat: position.coords.latitude, lng: position.coords.longitude };
        setLocating(false);
        setUserLoc(here);
        // Tự trỏ về showroom GẦN NHẤT — khách bấm một nút là xong bước vị trí,
        // vẫn đổi được bằng cách bấm thẻ/ghim khác.
        setShowrooms((current) => {
          const nearest = current
            .filter((s) => s.lat != null && s.lng != null)
            .map((s) => ({ id: s.id, d: haversineKm(here, { lat: s.lat as number, lng: s.lng as number }) }))
            .sort((a, b) => a.d - b.d)[0];
          if (nearest) setBooking((c) => ({ ...c, showroomId: nearest.id }));
          return current;
        });
      },
      () => {
        setLocating(false);
        setLocateFailed(true);
      },
      { enableHighAccuracy: true, timeout: 10_000, maximumAge: 60_000 },
    );
  }, []);

  // Tự xin GPS ngay khi mở trang (Sếp 2026-08-31: chat gợi ý showroom theo vị
  // trí thật, còn form ngoài bày mặc định đầu danh sách — hai nơi hai kết quả).
  // Khách từ chối thì im lặng dùng danh sách như cũ, nút bấm tay vẫn còn.
  useEffect(() => {
    requestLocation();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ một lần khi mở trang
  }, []);

  const selectedVehicle = useMemo(() => {
    return vehicles.find((v) => v.id === booking.vehicleId) || vehicles[0];
  }, [vehicles, booking.vehicleId]);

  const selectedShowroom = useMemo(() => {
    return showrooms.find((s) => s.id === booking.showroomId) || showrooms[0];
  }, [showrooms, booking.showroomId]);

  // Hồ sơ đăng nhập đã đủ tên + SĐT → không bắt gõ lại; form chỉ còn ba việc
  // đúng như Sếp chốt: xe, showroom (vị trí), lịch.
  const contactFromProfile = Boolean(profile?.full_name && profile?.phone_number);

  async function submit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBookingStatus("submitting");
    try {
      // Giờ khách chọn là GIỜ VIỆT NAM — ghim +07:00 (booking-time.ts). Bản cũ
      // dùng `...Z` nên 14:30 khách chọn thành 21:30 VN trong hệ thống.
      const scheduledAt = buildScheduledAt(booking.date, booking.timeSlot);
      const showroomLabel = selectedShowroom
        ? `${selectedShowroom.name} (${selectedShowroom.address || selectedShowroom.city})`
        : "VinFast Showroom";

      await createTestDriveBooking({
        vehicle_id: booking.vehicleId || selectedVehicle?.id || "",
        showroom: showroomLabel,
        scheduled_at: scheduledAt,
        customer_name: booking.fullName || undefined,
        phone: booking.phone || undefined,
        customer_id: user?.id || undefined,
      });

      setBookingStatus("success");
      // Đẩy dữ liệu THẬT của lượt đặt sang màn thành công — trang đó không còn
      // thẻ bịa cứng, thiếu params thì nó hiện bản chung.
      const successParams = new URLSearchParams({
        vehicle: selectedVehicle?.name || "",
        date: booking.date,
        time: booking.timeSlot,
        showroom: selectedShowroom?.name || "",
      });
      router.push(`/test-drive/success?${successParams.toString()}`);
    } catch {
      setBookingStatus("error");
    }
  }

  if (loadingOptions) {
    return (
      <div className="ops-state py-12">
        <LoaderCircle className="spin" size={32} />
        <h2>Đang tải danh sách xe và showroom từ cơ sở dữ liệu...</h2>
      </div>
    );
  }

  return (
    <>
      {state.bookingStatus === "conflict" ? (
        <div className="booking-status status-conflict" role="alert">
          <AlertCircle size={21} />
          <span>
            <strong>Khung giờ vừa được chọn bởi người khác</strong>
            Vui lòng chọn một khung giờ khác.
          </span>
          <button onClick={() => setBookingStatus("idle")} type="button">
            Chọn lại
          </button>
        </div>
      ) : null}
      {optionsError ? (
        <div className="booking-status status-error" role="alert">
          <AlertCircle size={21} />
          <span>
            <strong>Không tải được danh sách xe/showroom</strong>
            Anh/chị bấm thử lại giúp em ạ.
          </span>
          <button onClick={loadOptions} type="button">
            Thử lại
          </button>
        </div>
      ) : null}
      {state.bookingStatus === "error" ? (
        <div className="booking-status status-error" role="alert">
          <AlertCircle size={21} />
          <span>
            <strong>Không thể gửi yêu cầu lái thử tới hệ thống</strong>
            Vui lòng kiểm tra lại thông tin và thử lại.
          </span>
          <button onClick={() => setBookingStatus("idle")} type="button">
            Thử lại
          </button>
        </div>
      ) : null}
      <form className="booking-layout" onSubmit={submit}>
        <section className="booking-fields">
          {/* Nhãn bước MỘT DÒNG (Sếp 2026-08-31: form vẫn dài dọc) — khối tiêu đề
              hai tầng cũ ngốn ~100px mỗi bước mà không thêm thông tin nào. */}
          <p className="booking-step-line"><span>01</span>Chọn dòng xe</p>
          {/* MỘT Ô chọn dòng (Sếp 2026-08-31: "chỉ cần cho 1 ô xong chọn dòng
              thôi") — dãy chip vẫn tốn 2-3 hàng dọc với 10+ mẫu. */}
          <label className="field-label">
            Dòng xe lái thử
            <select
              onChange={(event) => setBooking((current) => ({ ...current, vehicleId: event.target.value }))}
              value={booking.vehicleId}
            >
              {vehicles.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </label>
          <p className="booking-step-line"><span>02</span>Vị trí và showroom</p>
          <button className="booking-locate" disabled={locating} onClick={requestLocation} type="button">
            {locating ? <LoaderCircle className="spin" size={16} /> : <LocateFixed size={16} />}
            {locating ? "Đang xác định vị trí..." : "Dùng vị trí của tôi"}
          </button>
          {locateFailed ? (
            <p className="booking-locate-note" role="status">
              Chưa lấy được vị trí — anh/chị vẫn chọn được showroom trong danh sách dưới đây.
            </p>
          ) : null}
          {!userLoc && showrooms.length > 12 ? (
            <p className="booking-locate-note">
              Đang hiện 12/{showrooms.length} điểm — bấm “Dùng vị trí của tôi” để tìm showroom gần nhất.
            </p>
          ) : null}
          <div aria-label="Chọn showroom" className="booking-showroom-list" role="group">
            {visibleShowrooms.map((s) => (
              <button
                aria-pressed={booking.showroomId === s.id}
                className="booking-showroom-card"
                key={s.id}
                onClick={() => setBooking((current) => ({ ...current, showroomId: s.id }))}
                type="button"
              >
                <span className="booking-showroom-name">{s.name}</span>
                {s.distanceKm != null ? (
                  <span className="booking-showroom-distance">{s.distanceKm.toFixed(1)} km</span>
                ) : null}
                <span className="booking-showroom-address">{s.address || s.city}</span>
              </button>
            ))}
          </div>
          <p className="booking-step-line"><span>03</span>Ngày và thời gian</p>
          <div className="booking-when">
          <label className="field-label">
            Ngày dự kiến
            <input
              onChange={(event) => setBooking((current) => ({ ...current, date: event.target.value }))}
              type="date"
              value={booking.date}
            />
          </label>
          <fieldset className="time-slot-field">
            <legend>Khung giờ trải nghiệm</legend>
            <div>
              {timeSlots.map((slot) => (
                <button
                  className={booking.timeSlot === slot ? "is-active" : ""}
                  key={slot}
                  onClick={() => setBooking((current) => ({ ...current, timeSlot: slot }))}
                  type="button"
                >
                  {booking.timeSlot === slot ? <CheckCircle2 size={14} /> : null}
                  {slot}
                </button>
              ))}
            </div>
          </fieldset>
          </div>
          {!contactFromProfile ? (
            <>
              <p className="booking-step-line"><span>04</span>Thông tin liên hệ — tư vấn viên sẽ gọi số này</p>
              <div className="two-field-row">
                <label className="field-label">
                  Họ và tên
                  <input
                    onChange={(event) => setBooking((current) => ({ ...current, fullName: event.target.value }))}
                    placeholder="Nguyễn Văn A"
                    required
                    value={booking.fullName}
                  />
                </label>
                <label className="field-label">
                  Số điện thoại
                  <input
                    inputMode="tel"
                    onChange={(event) => setBooking((current) => ({ ...current, phone: event.target.value }))}
                    placeholder="0912 345 678"
                    required
                    value={booking.phone}
                  />
                </label>
              </div>
            </>
          ) : null}
        </section>
        <aside className="booking-summary">
          {/* Bản đồ đứng CỘT PHẢI, ngang hàng các bước (Sếp 2026-08-31) — chọn
              showroom bên trái là ghim nhảy ngay bên phải, không phải cuộn. */}
          {mapShowrooms.length > 0 ? (
            <div className="booking-map">
              <TourMap
                center={userLoc}
                onSelect={(showroomId) => setBooking((current) => ({ ...current, showroomId }))}
                selectedId={booking.showroomId}
                showrooms={mapShowrooms}
              />
            </div>
          ) : null}
          <span className="eyebrow">Tóm tắt yêu cầu</span>
          <h2>{selectedVehicle ? selectedVehicle.name : "VinFast EV"}</h2>
          <div className="booking-summary-item">
            <MapPin size={18} />
            <span>
              <small>Showroom</small>
              <strong>{selectedShowroom?.name || "Showroom VinFast"}</strong>
              <span className="block text-[11px] text-slate-500 font-normal">{selectedShowroom?.address}</span>
            </span>
          </div>
          <div className="booking-summary-item">
            <CalendarDays size={18} />
            <span>
              <small>Thời gian</small>
              <strong>
                {booking.date} · {booking.timeSlot}
              </strong>
            </span>
          </div>
          {contactFromProfile ? (
            <div className="booking-summary-item">
              <Phone size={18} />
              <span>
                <small>Liên hệ (từ tài khoản của bạn)</small>
                <strong>
                  {booking.fullName} · {booking.phone}
                </strong>
              </span>
            </div>
          ) : null}
          <button
            className="primary-button full-button"
            // Chưa có xe (danh sách chưa tải được) thì không cho gửi — gửi
            // vehicle_id rỗng chỉ đổi lấy một lỗi 4xx khó hiểu hơn.
            disabled={state.bookingStatus === "submitting" || !booking.vehicleId}
            type="submit"
          >
            {state.bookingStatus === "submitting" ? (
              <>
                <LoaderCircle className="spin" size={18} /> Đang lưu vào hệ thống...
              </>
            ) : (
              "Xác nhận đặt lịch lái thử"
            )}
          </button>
        </aside>
      </form>
    </>
  );
}
