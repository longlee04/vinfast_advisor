"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";

import { VehiclePitchCard } from "@/components/consultation/vehicle-pitch-card";
import type { RecommendedVehicle } from "@/types/agent";

export function VehiclePitchList({
  vehicles,
  pitchHidden,
  onSelect,
  disabled = false,
}: Readonly<{
  vehicles: readonly RecommendedVehicle[];
  pitchHidden: boolean;
  onSelect?: (vehicle: RecommendedVehicle) => void;
  disabled?: boolean;
}>) {
  const [expanded, setExpanded] = useState(false);
  const visibleVehicles = expanded ? vehicles : vehicles.slice(0, 5);
  const remainingCount = Math.max(0, vehicles.length - 5);

  return (
    <div className="vehicle-pitch-list">
      {visibleVehicles.map((vehicle) => (
        <VehiclePitchCard
          disabled={disabled}
          key={vehicle.vehicle_id}
          onSelect={onSelect}
          pitchHidden={pitchHidden}
          vehicle={vehicle}
        />
      ))}
      {vehicles.length > 5 ? (
        <button
          type="button"
          className="see-more-vehicles-btn px-4 py-2.5 bg-slate-50 hover:bg-slate-100 text-slate-700 border border-slate-200 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition-all shadow-xs cursor-pointer w-full mt-1.5"
          onClick={() => setExpanded((prev) => !prev)}
        >
          {expanded ? (
            <>
              <ChevronUp size={15} /> Thu gọn danh sách ({vehicles.length} xe)
            </>
          ) : (
            <>
              <ChevronDown size={15} /> Xem thêm ({remainingCount} mẫu xe khác)
            </>
          )}
        </button>
      ) : null}
    </div>
  );
}
