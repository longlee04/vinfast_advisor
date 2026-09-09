import type { TcoRates } from "@/types/agent";

export type TcoBreakdown = {
  readonly total: number;
  readonly components: {
    readonly fixed: number;
    readonly energy: number;
    readonly insurance: number;
    readonly maintenance: number;
    readonly battery: number;
  };
};

/**
 * Tính TCO thuần phía client khi backend gửi kèm `rates` — không gọi mạng,
 * nên kéo thanh km bao nhiêu lần cũng rẻ và tức thời (`tco-card.tsx`).
 *
 * `total = fixed + energy_vnd_per_km*km*days_per_year*years
 *        + insurance_vnd_per_year*years
 *        + ceil(km*days_per_year*years / maintenance_interval_km) * maintenance_vnd_per_service
 *        + battery_vnd_per_month*12*years`
 *
 * Số lần bảo dưỡng làm tròn LÊN (`ceil`, không `floor`) — khớp
 * `src/agents/contracts.py TcoRatesView` phía backend: đi hết một khoảng bảo
 * dưỡng dù chỉ 1km cũng tính đủ một lần bảo dưỡng, không được làm tròn xuống
 * để mất khoản đó.
 *
 * Đơn giá vào là CHUỖI VND (tiền không đi qua float khi TRUYỀN) — riêng
 * `energy_vnd_per_km` có thể là chuỗi THẬP PHÂN (vd `"512.5"`), `Number()` giữ
 * nguyên phần lẻ. Phép NHÂN ở đây dùng `Number`, không `BigInt`: độ lớn thực tế
 * (một chiếc xe vài trăm triệu đến vài tỷ, quãng đường vài trăm nghìn km trong
 * 5 năm) nhân lên vẫn nằm dưới 2^53 (~9 x 10^15) — biên số nguyên an toàn của
 * `Number` — nên không mất độ chính xác.
 */
/**
 * Đọc một khoản tiền từ wire về số.
 *
 * VẮNG MẶT/null/chuỗi rỗng là 0 — KHÔNG phải NaN. Bài học VF 7 (đợt 11): xe
 * không thuê pin thì backend bỏ hẳn `battery_vnd_per_month` khỏi `rates`, mà
 * `Number(undefined)` là NaN và NaN cộng vào đâu là tổng thành "NaN đồng" ở
 * đó — thẻ "bị lỗi" dù backend trả đủ mọi khoản còn lại.
 */
function readVnd(value: unknown): number {
  if (value === undefined || value === null || value === "") return 0;
  return Number(value);
}

export function computeTco(rates: TcoRates, dailyDistanceKm: number): TcoBreakdown | null {
  const fixed = readVnd(rates.fixed_vnd);
  const energyPerKm = readVnd(rates.energy_vnd_per_km);
  const insurancePerYear = readVnd(rates.insurance_vnd_per_year);
  const maintenancePerService = readVnd(rates.maintenance_vnd_per_service);
  const batteryPerMonth = readVnd(rates.battery_vnd_per_month);
  // Payload thật gửi interval dạng CHUỖI "12000" (đợt 11) — ép số cho tất định,
  // không dựa vào chuyện `"12000" > 0` so sánh kiểu ngầm vẫn tình cờ đúng.
  const interval = readVnd(rates.maintenance_interval_km);

  const km = Math.max(0, dailyDistanceKm);
  const totalKm = km * rates.days_per_year * rates.years;

  const energy = energyPerKm * totalKm;
  const insurance = insurancePerYear * rates.years;
  const serviceCount = interval > 0 ? Math.ceil(totalKm / interval) : 0;
  const maintenance = serviceCount * maintenancePerService;
  const battery = batteryPerMonth * 12 * rates.years;

  const total = fixed + energy + insurance + maintenance + battery;
  // Đơn giá hỏng thật (chuỗi không phải số, years/days lạ...) thì trả `null`
  // để thẻ RƠI VỀ con số server (`total_vnd` + `components`) — thà mất thanh
  // kéo tức thời còn hơn bày "NaN đồng" cho khách.
  if (!Number.isFinite(total)) return null;

  return {
    total,
    components: { fixed, energy, insurance, maintenance, battery },
  };
}
