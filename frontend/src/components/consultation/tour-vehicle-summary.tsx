"use client";

import { ExternalLink } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { VehicleImage } from "@/components/shared/vehicle-image";
import { fetchVehicle, type CatalogVehicle } from "@/lib/api/vehicles";
import type { NavigateVehicle } from "@/types/agent";

/**
 * Tóm tắt xe cho cửa sổ "trang web đi theo hội thoại" (đợt 10).
 *
 * Trước đây panel nhúng NGUYÊN trang chi tiết (`*Experience`) — những trang đó
 * dàn cho full-width, nhét vào cột hẹp là vỡ: chữ tràn, ảnh hero cắt, lưới
 * thông số chen nhau. Thay vì ép trang lớn co lại, dựng một bản tóm tắt thiết
 * kế cho BIÊN 560–900px của panel (Sếp chốt đợt 10: panel là vai chính, chat
 * nhường chỗ): ảnh to, tên + giá, 4–6 thông số chính lưới 2–3 cột, và một nút
 * mở trang đầy đủ cho ai muốn xem hết.
 *
 * Dữ liệu lấy từ Catalog API thật (`fetchVehicle` theo slug/vehicle_id) chứ
 * không từ bảng slug cứng như `vehicle-detail-content` cũ — nhờ vậy mẫu nào có
 * trong catalog (kể cả xe máy chưa có trang riêng) cũng có tóm tắt, không còn
 * nhánh "slug lạ thì xin lỗi".
 *
 * Nút "Mở toàn trang" là điều hướng THẬT (`router.push`) — được phép vì nó nằm
 * trong panel, không chen giữa đoạn chat (luật đợt 10: đoạn chat sạch nút điều
 * hướng).
 */

type LoadState =
  | { readonly kind: "loading" }
  | { readonly kind: "error" }
  | { readonly kind: "ready"; readonly vehicle: CatalogVehicle };

/** Specs backend trả dạng chuỗi số ("376.00") — ép về số, hỏng thì coi như không có. */
function toNum(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/** "210.00" → "210", 87.7 → "87,7" — không cắt phần lẻ có nghĩa (dung lượng pin). */
function formatAmount(amount: number): string {
  return amount.toLocaleString("vi-VN", { maximumFractionDigits: 1 });
}

// Mỗi thông số một chấm màu riêng — mắt bám theo màu nhanh hơn đọc nhãn khi
// khách so hai xe liên tiếp trong cùng phiên tư vấn.
const DOT_COLORS = ["#1464f4", "#12b76a", "#f79009", "#7a5af8", "#ee46bc", "#0e9384"] as const;

/**
 * Chỉ bày thông số CÓ dữ liệu — một ô "— km" không nói được gì mà còn làm lưới
 * trông như catalog thiếu. Tối đa 6 ô cho lưới 2–3 cột không thành bảng dài.
 */
export function summarySpecs(vehicle: CatalogVehicle): readonly { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  const push = (label: string, amount: number | null, unit: string): void => {
    if (amount === null) return;
    rows.push({ label, value: `${formatAmount(amount)} ${unit}` });
  };
  push("Tầm chạy", vehicle.rangeKm, "km");
  push("Sạc nhanh", vehicle.chargeMinutes, "phút");
  push("Chỗ ngồi", vehicle.seats, "chỗ");
  push("Cốp", toNum(vehicle.specs.cargo_volume_standard_l), "L");
  // Ô tô có `motor_power_kw`; xe máy điện chỉ có công suất theo W.
  const kw = toNum(vehicle.specs.motor_power_kw);
  if (kw !== null) push("Công suất", kw, "kW");
  else push("Công suất", toNum(vehicle.specs.max_power_w ?? vehicle.specs.motor_power_w), "W");
  push("Pin", vehicle.batteryCapacityKwh, "kWh");
  return rows.slice(0, 6);
}

export function TourVehicleSummary({ navigate }: Readonly<{ navigate: NavigateVehicle }>) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  // Đếm lần thử lại để effect chạy lại — không gọi fetch thẳng trong onClick
  // để mọi lượt tải (đầu + thử lại) đi chung một đường có guard `alive`.
  const [attempt, setAttempt] = useState(0);
  const slug = navigate.slug.trim();
  // Tra theo vehicle_id (uuid — luôn khớp DB); slug của navigate là slug TRANG
  // ("vf-5") còn slug catalog DB là "vinfast-vf-5-all-new" — đưa slug trang vào
  // API là rơi nhánh SKU và từng 500 trên prod (2026-08-31). Slug chỉ dùng cho
  // nút "Mở toàn trang".
  const identifier = navigate.vehicle_id || slug;

  useEffect(() => {
    let alive = true;
    setState({ kind: "loading" });
    fetchVehicle(identifier)
      .then((vehicle) => {
        if (alive) setState({ kind: "ready", vehicle });
      })
      .catch(() => {
        // Nói ra và cho thử lại ngay trong panel — panel trống không lời giải
        // thích đọc như app hỏng.
        if (alive) setState({ kind: "error" });
      });
    return () => {
      alive = false;
    };
  }, [identifier, attempt]);

  if (state.kind === "loading") {
    // Cùng khung xám chờ với phần còn lại của panel — không nháy trắng.
    return (
      <div aria-hidden="true" className="tour-panel__skeleton">
        <span />
        <span />
        <span />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="tour-vehicle-summary">
        <p className="tour-panel__notice">Dạ em chưa tải được thông tin {navigate.name}.</p>
        <button
          className="tour-vehicle-summary__retry"
          onClick={() => setAttempt((current) => current + 1)}
          type="button"
        >
          Thử lại
        </button>
      </div>
    );
  }

  const { vehicle } = state;
  const title = [vehicle.modelName, vehicle.variant].filter(Boolean).join(" ") || navigate.name;
  const specs = summarySpecs(vehicle);

  return (
    <section aria-label={`Tóm tắt ${navigate.name}`} className="tour-vehicle-summary">
      {/* VehicleImage chứ không <img> trần: đổi link Google Drive dạng "xem"
          sang URL ảnh thật, và ảnh hỏng thì có khung fallback thay vì ô vỡ. */}
      <VehicleImage
        alt={title}
        className="tour-vehicle-summary__image"
        sizes="(max-width: 1099px) 100vw, 62vw"
        src={vehicle.imageUrl}
      />
      <div className="tour-vehicle-summary__head">
        <h3 className="tour-vehicle-summary__name">{title}</h3>
        <p className="tour-vehicle-summary__price">
          {vehicle.priceVnd != null
            ? `Giá từ ${vehicle.priceVnd.toLocaleString("vi-VN")} đ`
            : "Chưa có giá hiệu lực"}
        </p>
      </div>
      {specs.length > 0 ? (
        <ul aria-label="Thông số chính" className="tour-vehicle-summary__specs">
          {specs.map((row, index) => (
            <li className="tour-vehicle-summary__spec" key={row.label}>
              <span
                aria-hidden="true"
                className="tour-vehicle-summary__dot"
                style={{ background: DOT_COLORS[index % DOT_COLORS.length] }}
              />
              <span className="tour-vehicle-summary__spec-text">
                <strong>{row.value}</strong>
                <span>{row.label}</span>
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {/* Slug rỗng = chưa có trang /vehicles/ cho mẫu này (xe máy) — không bày
          một nút dẫn tới trang trống. */}
      {slug ? (
        <button
          className="tour-vehicle-summary__open"
          onClick={() => router.push(`/vehicles/${slug}`)}
          type="button"
        >
          <ExternalLink aria-hidden="true" size={16} />
          <span>Mở toàn trang</span>
        </button>
      ) : null}
    </section>
  );
}
