import { BatteryCharging, CarFront, Gauge, UsersRound, WalletCards } from "lucide-react";

import { formatNumber } from "@/lib/format";
import type { CustomerNeedProfile } from "@/types/demo";

export function ProfileChips({ profile }: Readonly<{ profile: CustomerNeedProfile }>) {
  const chips = [
    { icon: CarFront, label: profile.vehicleType === "electric_motorbike" ? "Xe máy điện" : "Ô tô điện" },
    profile.vehicleType === "electric_motorbike"
      ? { icon: UsersRound, label: profile.electricMotorbikeUse === "delivery" ? "Giao hàng" : "Đi làm / cá nhân" }
      : { icon: UsersRound, label: `${profile.passengerCount ?? 5} người` },
    { icon: WalletCards, label: `${formatNumber((profile.budgetMaxVnd ?? 800_000_000) / 1_000_000)} triệu` },
    { icon: BatteryCharging, label: profile.homeChargingAccess === false ? "Không sạc tại nhà" : "Có sạc tại nhà" },
    { icon: Gauge, label: `${formatNumber(profile.monthlyDistanceKm ?? 1_200)} km/tháng` },
  ];
  return <div className="profile-chips" aria-label="Hồ sơ nhu cầu tóm tắt">{chips.map((chip) => { const Icon = chip.icon; return <span key={chip.label}><Icon size={15} />{chip.label}</span>; })}</div>;
}
