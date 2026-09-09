"use client";

import { Check, ChevronRight, X } from "lucide-react";

import { formatNumber } from "@/lib/format";
import { useDemoStore } from "@/store/demo-store";
import type { CustomerNeedProfile } from "@/types/demo";

const profileFields: { key: keyof CustomerNeedProfile; label: string; step: number }[] = [
  { key: "vehicleType", label: "Loại phương tiện", step: 0 },
  { key: "passengerCount", label: "Số người", step: 1 },
  { key: "electricMotorbikeUse", label: "Mục đích xe máy điện", step: 1 },
  { key: "monthlyDistanceKm", label: "Quãng đường", step: 2 },
  { key: "homeChargingAccess", label: "Sạc tại nhà", step: 3 },
  { key: "budgetMaxVnd", label: "Ngân sách", step: 4 },
  { key: "primaryUse", label: "Mục đích chính", step: 5 },
  { key: "priorities", label: "Ưu tiên", step: 6 },
];

function presentValue(key: keyof CustomerNeedProfile, value: CustomerNeedProfile[keyof CustomerNeedProfile]): string {
  if (value === undefined) return "Chưa rõ";
  if (key === "vehicleType") return value === "car" ? "Ô tô" : "Xe máy điện";
  if (key === "budgetMaxVnd" && typeof value === "number") return `${formatNumber(value / 1_000_000)} triệu`;
  if (key === "monthlyDistanceKm" && typeof value === "number") return `${formatNumber(value)} km/tháng`;
  if (key === "passengerCount" && typeof value === "number") return `${value} người`;
  if (key === "homeChargingAccess") return value === true ? "Có" : value === false ? "Không" : "Chưa rõ";
  if (Array.isArray(value)) return value.join(", ") || "Chưa rõ";
  const labels: Record<string, string> = { family: "Gia đình", personal: "Cá nhân", business: "Kinh doanh", mixed: "Kết hợp", commuting: "Đi làm", delivery: "Giao hàng" };
  return labels[String(value)] ?? String(value);
}

export function NeedsSummarySheet({ open, onClose }: Readonly<{ open: boolean; onClose: () => void }>) {
  const { state, goToConsultationStep } = useDemoStore();
  if (!open) return null;
  const fields = profileFields.filter((field) => field.key !== (state.needProfile.vehicleType === "electric_motorbike" ? "passengerCount" : "electricMotorbikeUse"));

  return (
    <div className="sheet-layer" role="dialog" aria-modal="true" aria-labelledby="needs-sheet-title">
      <button className="sheet-backdrop" onClick={onClose} aria-label="Đóng hồ sơ nhu cầu" type="button" />
      <section className="needs-sheet">
        <div className="sheet-header"><div><span className="eyebrow">Hồ sơ nhu cầu</span><h2 id="needs-sheet-title">Thông tin đã ghi nhận</h2></div><button className="icon-button" onClick={onClose} aria-label="Đóng" type="button"><X size={20} /></button></div>
        <div className="needs-field-list">
          {fields.map((field) => {
            const value = state.needProfile[field.key];
            const complete = value !== undefined && (!Array.isArray(value) || value.length > 0);
            return <button className="needs-field" key={field.key} onClick={() => { goToConsultationStep(field.step); onClose(); }} type="button"><span className={complete ? "field-state is-complete" : "field-state"}>{complete ? <Check size={15} /> : "·"}</span><span><small>{field.label}</small><strong>{presentValue(field.key, value)}</strong></span><ChevronRight size={17} /></button>;
          })}
        </div>
        <button className="primary-button full-button" onClick={onClose} type="button">Lưu và tiếp tục</button>
      </section>
    </div>
  );
}
