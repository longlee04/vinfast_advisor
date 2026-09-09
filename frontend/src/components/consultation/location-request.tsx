"use client";

import { LocateFixed, MapPin, Send, ShieldCheck } from "lucide-react";
import { FormEvent, useState } from "react";

/**
 * UI xin vị trí khách, hiện khi backend trả `charging_stations.needs_location`.
 *
 * ĐÚNG HAI nguồn:
 * 1. `navigator.geolocation` — nút chính (GPS tự động).
 * 2. Ô gõ địa danh — nhánh dự phòng (gõ khu vực/tỉnh thành).
 */
export function LocationRequest({
  onCoordinates,
  onLocationText,
  disabled = false,
}: Readonly<{
  onCoordinates: (position: { latitude: number; longitude: number }) => void;
  onLocationText: (locationText: string) => void;
  disabled?: boolean;
}>): React.JSX.Element {
  const [state, setState] = useState<"idle" | "loading" | "denied" | "unavailable">("idle");
  const [draft, setDraft] = useState("");

  function requestPosition(): void {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setState("unavailable");
      return;
    }
    setState("loading");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setState("idle");
        onCoordinates({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      (error) => setState(error.code === error.PERMISSION_DENIED ? "denied" : "unavailable"),
      { enableHighAccuracy: true, maximumAge: 60_000, timeout: 10_000 },
    );
  }

  function submitText(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    onLocationText(text);
  }

  return (
    <div aria-label="Chia sẻ vị trí để tìm trạm sạc" className="location-request-container">
      <div className="location-request-card">
        <div className="location-request-header">
          <div className="location-request-icon">
            <MapPin size={20} />
          </div>
          <div>
            <h3 className="location-request-title">Xác định vị trí xung quanh bạn</h3>
            <p className="location-request-desc">Chọn chia sẻ vị trí tự động hoặc nhập khu vực bạn muốn tìm</p>
          </div>
        </div>

        <div className="location-request-actions">
          <button
            className="location-gps-button"
            disabled={disabled || state === "loading"}
            onClick={requestPosition}
            type="button"
          >
            <LocateFixed className={state === "loading" ? "animate-spin" : ""} size={18} />
            <span>{state === "loading" ? "Đang xác định toạ độ..." : "Chia sẻ vị trí của bạn (GPS)"}</span>
          </button>

          {state === "denied" ? (
            <p className="location-request-error" role="status">
              Trình duyệt đã từ chối quyền vị trí. Bạn có thể gõ tên khu vực hoặc quận/huyện bên dưới nhé.
            </p>
          ) : null}
          {state === "unavailable" ? (
            <p className="location-request-error" role="status">
              Không thể lấy toạ độ GPS lúc này. Bạn vui lòng gõ tên khu vực bên dưới nhé.
            </p>
          ) : null}

          <div className="location-divider">
            <span>hoặc gõ tên khu vực</span>
          </div>

          <form className="location-input-form" onSubmit={submitText}>
            <input
              aria-label="Nhập tên khu vực hoặc địa chỉ"
              disabled={disabled}
              id="charging-location-text"
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Ví dụ: Cầu Giấy, Hà Nội hoặc Quận 1, TP.HCM..."
              value={draft}
            />
            <button aria-label="Tìm kiếm trạm sạc theo khu vực" disabled={disabled || !draft.trim()} type="submit">
              <Send size={15} />
              <span>Tìm kiếm</span>
            </button>
          </form>
        </div>

        <div className="location-request-footer">
          <ShieldCheck size={14} />
          <span>Vị trí chỉ dùng để tính khoảng cách tới trạm sạc trong phiên tư vấn này.</span>
        </div>
      </div>
    </div>
  );
}
