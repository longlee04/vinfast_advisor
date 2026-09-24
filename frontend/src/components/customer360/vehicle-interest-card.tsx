import type { VehicleInterest } from "@/types/customer360";

import { shortDate, vehicleRoleLabel } from "./customer360-labels";

/**
 * Một xe khách quan tâm. Xe đứng đầu viền xanh. Chỉ có NGÀY gửi báo giá — số tiền không lưu
 * theo xe nên không bao giờ hiện (càng không để LLM sinh ra).
 */
export function VehicleInterestCard({ vehicle, primary }: Readonly<{ vehicle: VehicleInterest; primary: boolean }>) {
  return (
    <li className="c360-vehicle" data-primary={primary || undefined}>
      <div className="c360-vehicle-head">
        <strong>{vehicle.name}</strong>
        <span>{vehicleRoleLabel(vehicle.role, vehicle.rank)}</span>
      </div>
      {vehicle.quote_sent_at ? <p>Đã gửi báo giá lăn bánh {shortDate(vehicle.quote_sent_at)}</p> : null}
      {vehicle.asked_features.length ? <p>Hỏi về: {vehicle.asked_features.join(", ")}</p> : null}
    </li>
  );
}
