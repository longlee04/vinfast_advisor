import type { HeatBand } from "@/types/customer360";

import { HEAT_BAND_BADGES } from "./customer360-labels";

/** Viên độ nóng "Nóng · 86" — màu theo dải (cam/vàng/xám), không bao giờ đỏ (DESIGN.md §3). */
export function HeatPill({ band, score }: Readonly<{ band: HeatBand; score?: number | null }>) {
  const label = HEAT_BAND_BADGES[band].label;
  const text = score === null || score === undefined ? label : `${label} · ${score}`;
  return (
    <span aria-label={`Độ nóng: ${text}`} className="c360-heat-pill" data-band={band}>
      {text}
    </span>
  );
}
