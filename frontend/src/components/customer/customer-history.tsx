"use client";

import {
  BatteryCharging,
  Bike,
  CalendarCheck2,
  CarFront,
  CheckCircle2,
  Clock3,
  Edit3,
  FileText,
  Loader2,
  MapPin,
  MessageSquareText,
  Phone,
  RotateCw,
  UserRound,
  UsersRound,
  WalletCards,
  X,
} from "lucide-react";
import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

import { TestDriveBookings } from "@/components/customer/test-drive-bookings";
import { ProfileChips } from "@/components/recommendations/profile-chips";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  AssignmentApiError,
  CustomerAccountSummary,
  fetchCustomerSummary,
} from "@/lib/api/assignments";
import { useAuth } from "@/store/auth-store";
import { useDemoStore } from "@/store/demo-store";

export function CustomerHistory() {
  const { user, profile, saveProfile } = useAuth();
  const { state } = useDemoStore();
  const approved = state.recommendationStatus === "approved" || state.recommendationStatus === "edited";

  const [summary, setSummary] = useState<CustomerAccountSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const bookingsSectionRef = useRef<HTMLElement | null>(null);

  function focusBookingsSection(): void {
    bookingsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    bookingsSectionRef.current?.focus();
  }

  const [summaryError, setSummaryError] = useState<string | null>(null);

  const loadSummary = async () => {
    try {
      setSummaryError(null);
      const data = await fetchCustomerSummary();
      setSummary(data);
    } catch (error) {
      // 401 = phiên hết hạn: nói thẳng thay vì bảng toàn số 0 trong im lặng
      // như trước (khách tưởng dữ liệu của mình biến mất). Lỗi khác giữ nguyên
      // hành vi cũ — trang vẫn dùng được với phần còn lại.
      if (error instanceof AssignmentApiError && error.status === 401) {
        setSummaryError("Phiên đã hết hạn, anh/chị đăng nhập lại giúp em ạ.");
      }
    } finally {
      setLoadingSummary(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadSummary();
  }, [user]);

  const [editing, setEditing] = useState(false);
  const [fullName, setFullName] = useState(profile?.full_name || "");
  const [phoneNumber, setPhoneNumber] = useState(profile?.phone_number || "");
  const [address, setAddress] = useState(profile?.address || "");
  const [vehiclePreference, setVehiclePreference] = useState(profile?.vehicle_preference || "car");
  const [budgetPreference, setBudgetPreference] = useState(profile?.budget_preference || "800 triệu");
  const [seatsPreference, setSeatsPreference] = useState(profile?.seats_preference || "5 chỗ");
  const [homeCharging, setHomeCharging] = useState(profile?.home_charging ?? true);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);


  // Tính phần trăm hoàn thiện hồ sơ
  let completeness = 20; // Có tài khoản email
  if (profile?.full_name?.trim()) completeness += 20;
  if (profile?.phone_number?.trim()) completeness += 20;
  if (profile?.address?.trim()) completeness += 20;
  if (profile?.budget_preference?.trim() || profile?.vehicle_preference?.trim()) completeness += 20;

  function openEditModal(): void {
    setFullName(profile?.full_name || "");
    setPhoneNumber(profile?.phone_number || "");
    setAddress(profile?.address || "");
    setVehiclePreference(profile?.vehicle_preference || "car");
    setBudgetPreference(profile?.budget_preference || "800 triệu");
    setSeatsPreference(profile?.seats_preference || "5 chỗ");
    setHomeCharging(profile?.home_charging ?? true);
    setSaveSuccess(false);
    setEditing(true);
  }

  async function handleSaveProfile(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    try {
      setSaving(true);
      await saveProfile({
        full_name: fullName,
        phone_number: phoneNumber,
        address: address,
        vehicle_preference: vehiclePreference,
        budget_preference: budgetPreference,
        seats_preference: seatsPreference,
        home_charging: homeCharging,
      });
      setSaveSuccess(true);
      setTimeout(() => {
        setEditing(false);
        setSaveSuccess(false);
      }, 600);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  const displayName = profile?.full_name?.trim() || (user?.email ? user.email.split("@")[0] : "Khách hàng");
  const displayEmail = user?.email || "Chưa đăng nhập";
  const displayPhone = profile?.phone_number?.trim() || "Chưa cập nhật SĐT";
  const displayAddress = profile?.address?.trim() || "Chưa cập nhật địa chỉ";

  return (
    <div className="history-layout">
      <aside className="customer-profile-card">
        <div className="profile-avatar"><UserRound size={25} /></div>
        <span className="eyebrow">Tài khoản khách hàng</span>
        <h2>{displayName}</h2>
        <p>
          <span>{displayEmail}</span>
          <br />
          <span className="flex items-center gap-1 text-slate-600 text-xs mt-1">
            <Phone size={12} /> {displayPhone}
          </span>
          <span className="flex items-center gap-1 text-slate-600 text-xs mt-0.5">
            <MapPin size={12} /> {displayAddress}
          </span>
        </p>

        <button
          className="mt-3 px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-blue-700 border border-blue-200 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-all cursor-pointer w-full"
          onClick={openEditModal}
          type="button"
        >
          <Edit3 size={14} />
          <span>Cập nhật hồ sơ & nhu cầu</span>
        </button>

        <div className="profile-completeness mt-4">
          <div>
            <span>Mức hoàn thiện hồ sơ</span>
            <strong>{completeness}%</strong>
          </div>
          <span><i style={{ width: `${completeness}%` }} /></span>
        </div>

        <h3 className="mt-4">Nhu cầu & Sở thích đã lưu</h3>
        <div className="profile-chips">
          <span>
            {profile?.vehicle_preference === "bike" ? <Bike size={14} /> : <CarFront size={14} />}
            {profile?.vehicle_preference === "bike" ? "Xe máy điện" : "Ô tô điện"}
          </span>
          <span>
            <UsersRound size={14} />
            {profile?.seats_preference || "5 chỗ"}
          </span>
          <span>
            <WalletCards size={14} />
            {profile?.budget_preference || "800 triệu"}
          </span>
          <span>
            <BatteryCharging size={14} />
            {profile?.home_charging === false ? "Sạc công cộng" : "Có sạc tại nhà"}
          </span>
        </div>

        <button className="secondary-button full-button mt-3" onClick={openEditModal} type="button">
          Cập nhật nhu cầu
        </button>
      </aside>

      <section className="history-content">
        {summaryError ? (
          <div className="booking-status status-error" role="alert">
            <span>
              <strong>Phiên đã hết hạn</strong>
              {summaryError}
            </span>
            <Link className="primary-button" href="/login?next=/account">Đăng nhập lại</Link>
          </div>
        ) : null}
        <div className="history-summary-row">
          <article>
            <MessageSquareText size={20} />
            <span>Phiên tư vấn</span>
            <strong>{loadingSummary ? "..." : (summary?.session_count ?? 0)}</strong>
          </article>
          <article>
            <FileText size={20} />
            <span>Bảng so sánh</span>
            <strong>{loadingSummary ? "..." : (summary?.comparison_count ?? 0)}</strong>
          </article>
          <button
            type="button"
            className="history-summary-tile-button"
            onClick={focusBookingsSection}
            aria-label="Xem lịch lái thử của bạn"
          >
            <article>
              <CalendarCheck2 size={20} />
              <span>Lịch lái thử</span>
              <strong>{loadingSummary ? "..." : (summary?.booking_count ?? 0)}</strong>
            </article>
          </button>
        </div>

        <TestDriveBookings ref={bookingsSectionRef} />

        <div className="history-section-heading flex items-center justify-between mt-5">
          <div>
            <h2>Hoạt động gần đây</h2>
            <p>Theo dõi các phiên tư vấn, so sánh và lịch lái thử của bạn.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition cursor-pointer"
              onClick={() => {
                setRefreshing(true);
                loadSummary();
              }}
              disabled={refreshing}
              type="button"
            >
              <RotateCw size={13} className={refreshing ? "animate-spin" : ""} />
              <span>Làm mới</span>
            </button>
            <StatusBadge tone={(summary?.approved_recommendations_count ?? 0) > 0 || approved ? "success" : "warning"}>
              {(summary?.approved_recommendations_count ?? 0) > 0 || approved ? <CheckCircle2 size={14} /> : <Clock3 size={14} />}
              {(summary?.approved_recommendations_count ?? 0) > 0 || approved ? "Có đề xuất đã duyệt" : "Đang chờ duyệt"}
            </StatusBadge>
          </div>
        </div>
        <div className="history-timeline">
          {loadingSummary ? (
            <div className="flex items-center justify-center p-8 text-slate-500 gap-2">
              <Loader2 className="animate-spin text-blue-600" size={18} />
              <span className="text-xs">Đang tải lịch sử hoạt động từ cơ sở dữ liệu...</span>
            </div>
          ) : summary?.activities && summary.activities.length > 0 ? (
            summary.activities.map((item) => {
              const Icon =
                item.icon === "calendar"
                  ? CalendarCheck2
                  : item.icon === "file"
                  ? FileText
                  : MessageSquareText;
              return (
                <article key={item.id}>
                  <span className="timeline-icon">
                    <Icon size={18} />
                  </span>
                  <div>
                    <small>{item.date}</small>
                    <h3>{item.title}</h3>
                    <p>{item.description}</p>
                    <StatusBadge
                      tone={
                        (item.tone as "success" | "warning" | "neutral" | "danger") ||
                        (item.status === "Đã xác nhận" || item.status === "Đã hoàn thành"
                          ? "success"
                          : "warning")
                      }
                    >
                      {item.status}
                    </StatusBadge>
                  </div>
                </article>
              );
            })
          ) : (
            <div className="p-6 text-center text-slate-500 bg-slate-50 border border-dashed border-slate-200 rounded-xl text-xs">
              Chưa có hoạt động nào được ghi nhận. Hãy bắt đầu phiên tư vấn hoặc đăng ký lái thử xe!
            </div>
          )}
        </div>
        <div className="history-demo-action">
          <div>
            <strong>Đề xuất dành riêng cho bạn</strong>
            <p>Xem các lựa chọn đã được tư vấn viên kiểm tra.</p>
          </div>
          <Link className="primary-button" href="/recommendations">Xem đề xuất</Link>
        </div>
      </section>

      {editing ? (
        <div className="chat-confirm-backdrop" role="presentation">
          <section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="edit-profile-title" style={{ maxWidth: "520px" }}>
            <button className="chat-confirm-close" onClick={() => setEditing(false)} type="button" aria-label="Đóng">
              <X size={18} />
            </button>
            <span className="eyebrow text-blue-600">Hồ sơ cá nhân</span>
            <h2 id="edit-profile-title">Cập nhật thông tin & Nhu cầu</h2>
            <p>Thông tin giúp tư vấn viên và hệ thống hỗ trợ bạn chính xác và chu đáo nhất.</p>

            <form onSubmit={handleSaveProfile} className="flex flex-col gap-3 mt-4 text-left">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Họ và tên</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                  placeholder="Ví dụ: Lê Văn Khách"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Số điện thoại</label>
                  <input
                    type="tel"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                    placeholder="Ví dụ: 0912345678"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Địa chỉ / Tỉnh thành</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                    placeholder="Ví dụ: Hà Nội"
                    value={address}
                    onChange={(e) => setAddress(e.target.value)}
                  />
                </div>
              </div>

              <div className="border-t border-slate-200 pt-3 mt-1">
                <span className="text-xs font-bold text-slate-900 block mb-2">Sở thích & Nhu cầu tư vấn mặc định</span>
                
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Loại xe quan tâm</label>
                    <select
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500 bg-white"
                      value={vehiclePreference}
                      onChange={(e) => setVehiclePreference(e.target.value)}
                    >
                      <option value="car">Ô tô điện</option>
                      <option value="bike">Xe máy điện</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Ngân sách dự kiến</label>
                    <input
                      type="text"
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500"
                      placeholder="Ví dụ: 800 triệu, 1.2 tỷ..."
                      value={budgetPreference}
                      onChange={(e) => setBudgetPreference(e.target.value)}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 mt-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Số chỗ ngồi</label>
                    <select
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500 bg-white"
                      value={seatsPreference}
                      onChange={(e) => setSeatsPreference(e.target.value)}
                    >
                      <option value="5 chỗ">5 chỗ</option>
                      <option value="7 chỗ">7 chỗ</option>
                      <option value="2 chỗ">2 chỗ (Xe máy)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">Điều kiện sạc</label>
                    <select
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-blue-500 bg-white"
                      value={homeCharging ? "true" : "false"}
                      onChange={(e) => setHomeCharging(e.target.value === "true")}
                    >
                      <option value="true">Có sạc tại nhà</option>
                      <option value="false">Sử dụng trạm sạc công cộng</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-2 mt-4">
                <button className="secondary-button" onClick={() => setEditing(false)} type="button">
                  Huỷ
                </button>
                <button
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                  disabled={saving}
                  type="submit"
                >
                  {saving ? <Loader2 className="spin" size={16} /> : null}
                  {saveSuccess ? "Đã lưu thành công!" : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}
