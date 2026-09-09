"use client";

import { Check, CheckCircle2, FileCheck2, Scale, ShieldCheck } from "lucide-react";

import { StatusBadge } from "@/components/shared/status-badge";
import { formatVnd } from "@/lib/format";
import { getVehicle } from "@/mocks/vehicles";
import { useDemoStore } from "@/store/demo-store";
import type { VehicleRecommendation } from "@/types/demo";

export function RecommendationCard({ recommendation }: Readonly<{ recommendation: VehicleRecommendation }>) {
  const vehicle = getVehicle(recommendation.vehicleId);
  const { state, toggleSelectedVehicle } = useDemoStore();
  const selected = state.selectedVehicleIds.includes(vehicle.id);

  return (
    <article className="recommendation-card">
      <div className="recommendation-visual">
        <span className="rank-badge">#{recommendation.rank}</span>
        <div className="asset-mini-fallback"><span>V</span><small>Ảnh chính thức đang chờ cung cấp</small></div>
      </div>
      <div className="recommendation-content">
        <div className="recommendation-title-row"><div><span className="eyebrow">Đề xuất {recommendation.rank}</span><h2>{vehicle.modelName} <small>{vehicle.variant}</small></h2><strong className="recommendation-price">{formatVnd(vehicle.priceVnd)}</strong></div><StatusBadge tone="success"><ShieldCheck size={14} /> Advisor đã duyệt</StatusBadge></div>
        <ul className="reason-list">{recommendation.reasons.map((reason) => <li key={reason}><CheckCircle2 size={17} />{reason}</li>)}</ul>
        <div className="tradeoff"><Scale size={17} /><span><strong>Điểm cần cân nhắc</strong>{recommendation.tradeoff}</span></div>
        <div className="source-labels"><FileCheck2 size={15} />{recommendation.sourceLabels.map((label) => <span key={label}>{label}</span>)}</div>
        <div className="recommendation-actions"><label className={selected ? "compare-toggle is-selected" : "compare-toggle"}><input checked={selected} onChange={() => toggleSelectedVehicle(vehicle.id)} type="checkbox" />{selected ? <Check size={15} /> : null} Chọn so sánh</label><button className="text-button" type="button">Xem chi tiết →</button></div>
      </div>
    </article>
  );
}
