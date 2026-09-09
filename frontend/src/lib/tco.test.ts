import { describe, expect, it } from "vitest";

import { computeTco } from "@/lib/tco";
import type { TcoRates } from "@/types/agent";

// Đơn giá cố định để tay tính đối chiếu — mọi số hạng đều tròn, không làm
// tròn số ẩn đi sai số của công thức.
const RATES: TcoRates = {
  fixed_vnd: "900000000",
  energy_vnd_per_km: "1500",
  insurance_vnd_per_year: "8000000",
  maintenance_vnd_per_service: "2500000",
  maintenance_interval_km: 10000,
  battery_vnd_per_month: "1000000",
  years: 5,
  days_per_year: 365,
  formula_note: "Tính cho 5 năm, 365 ngày/năm.",
};

describe("computeTco", () => {
  it("tính đúng theo công thức tay ở 30 km/ngày — bảo dưỡng làm tròn LÊN", () => {
    // totalKm = 30 * 365 * 5 = 54.750
    // energy = 1500 * 54.750 = 82.125.000
    // insurance = 8.000.000 * 5 = 40.000.000
    // maintenance = ceil(54.750 / 10.000) * 2.500.000 = ceil(5.475) * 2.500.000 = 6 * 2.500.000 = 15.000.000
    // battery = 1.000.000 * 12 * 5 = 60.000.000
    // total = 900.000.000 + 82.125.000 + 40.000.000 + 15.000.000 + 60.000.000 = 1.097.125.000
    const result = computeTco(RATES, 30)!;

    expect(result.components).toEqual({
      fixed: 900_000_000,
      energy: 82_125_000,
      insurance: 40_000_000,
      maintenance: 15_000_000,
      battery: 60_000_000,
    });
    expect(result.total).toBe(1_097_125_000);
  });

  it("tính đúng ở 90 km/ngày — kiểm lại phần ceil() của bảo dưỡng", () => {
    // totalKm = 90 * 365 * 5 = 164.250
    // energy = 1500 * 164.250 = 246.375.000
    // maintenance = ceil(164.250 / 10.000) * 2.500.000 = ceil(16.425) * 2.500.000 = 17 * 2.500.000 = 42.500.000
    // total = 900.000.000 + 246.375.000 + 40.000.000 + 42.500.000 + 60.000.000 = 1.288.875.000
    const result = computeTco(RATES, 90)!;

    expect(result.components.maintenance).toBe(42_500_000);
    expect(result.total).toBe(1_288_875_000);
  });

  it("đi vừa hết một khoảng bảo dưỡng (chia hết) thì KHÔNG làm tròn lên thừa", () => {
    // totalKm = 20 * 365 * 5 = 36.500 — không chia hết 10.000, đổi interval để
    // ra đúng số chẵn: dùng 36.500 / 3.650 = 10 (chia hết), ceil(10) phải = 10.
    const result = computeTco({ ...RATES, maintenance_interval_km: 3650 }, 20)!;

    expect(result.components.maintenance).toBe(10 * 2_500_000);
  });

  it("giá theo km là số thập phân thì vẫn giữ nguyên phần lẻ, không làm tròn", () => {
    // Backend gửi `energy_vnd_per_km` dạng thập phân (vd "512.5").
    const result = computeTco({ ...RATES, energy_vnd_per_km: "512.5" }, 30)!;

    // totalKm = 54.750 → energy = 512.5 * 54.750 = 28.059.375
    expect(result.components.energy).toBe(28_059_375);
  });

  it("0 km/ngày: chỉ còn chi phí cố định, bảo hiểm và thuê pin", () => {
    const result = computeTco(RATES, 0)!;

    expect(result.components.energy).toBe(0);
    expect(result.components.maintenance).toBe(0);
    expect(result.total).toBe(900_000_000 + 40_000_000 + 60_000_000);
  });

  it("km âm coi như 0, không trả tổng âm", () => {
    const result = computeTco(RATES, -20)!;

    expect(result.components.energy).toBe(0);
    expect(result.total).toBe(900_000_000 + 40_000_000 + 60_000_000);
  });

  it("maintenance_interval_km bằng 0 thì không chia cho 0 — bỏ hẳn khoản bảo dưỡng", () => {
    const result = computeTco({ ...RATES, maintenance_interval_km: 0 }, 30)!;

    expect(result.components.maintenance).toBe(0);
    expect(Number.isFinite(result.total)).toBe(true);
  });
});

// Đợt 11 — hình dạng wire THẬT của VF 7: `computeTco` giờ trả nullable, các
// test cũ dùng `!` vì đơn giá của chúng luôn hợp lệ.
describe("computeTco — payload lệch hợp đồng (VF 7 đợt 11)", () => {
  it("battery_vnd_per_month VẮNG HẲN: pin là 0 đồng, không phải NaN", () => {
    const { battery_vnd_per_month: _bo, ...rest } = RATES;
    const result = computeTco(rest as TcoRates, 30)!;

    expect(result.components.battery).toBe(0);
    expect(result.total).toBe(1_097_125_000 - 60_000_000);
  });

  it("maintenance_interval_km là CHUỖI '10000': vẫn tính đúng số lần bảo dưỡng", () => {
    const result = computeTco({ ...RATES, maintenance_interval_km: "10000" }, 30)!;

    expect(result.components.maintenance).toBe(15_000_000);
    expect(result.total).toBe(1_097_125_000);
  });

  it("đơn giá hỏng thật (không phải số) thì trả null — thẻ rơi về con số server, không bày NaN", () => {
    expect(computeTco({ ...RATES, fixed_vnd: "chua co gia" }, 30)).toBeNull();
  });
});
