"use client";

import { BadgeCheck, BatteryCharging, CircleDollarSign, ClipboardCheck, Info, Route, ShieldCheck, Wrench } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchTco, fetchVehicles, type CatalogVehicle, type TcoResult } from "@/lib/api/vehicles";
import { formatNumber, formatVnd } from "@/lib/format";

/** Ba lựa chọn đủ để phủ đúng logic hai khu vực lệ phí biển số.
 *
 * [GIẢ ĐỊNH] Rút gọn thay vì liệt kê đủ 34 tỉnh: backend chỉ phân biệt Hà Nội /
 * TP.HCM (Khu vực I) với phần còn lại (Khu vực II), nên ba mục này cho đúng kết
 * quả cho mọi khách. Liệt kê đủ tỉnh là việc riêng, ngoài phạm vi thay đổi này.
 *
 * "Tỉnh/thành khác" gửi MÃ RỖNG (backend tự dùng mặc định Khu vực II) — bản cũ
 * gửi cứng "Cần Thơ": kết quả tính vẫn đúng nhưng dữ liệu bịa lọt vào log và
 * mọi thống kê theo tỉnh (đợt vá 2026-08-31).
 */
const PROVINCE_OPTIONS = [
  { value: "Hà Nội", label: "Hà Nội" },
  { value: "Hồ Chí Minh", label: "Hồ Chí Minh" },
  { value: "", label: "Tỉnh/thành khác" },
] as const;

const REGION_LABELS: Record<string, string> = {
  KHU_VUC_I: "Khu vực I (Hà Nội, TP.HCM)",
  KHU_VUC_II: "Khu vực II (các tỉnh/thành còn lại)",
};

export function TcoCalculator() {
  const [vehicles, setVehicles] = useState<CatalogVehicle[]>([]);
  const [province, setProvince] = useState<string>(PROVINCE_OPTIONS[0].value);
  const [vehiclesError, setVehiclesError] = useState<string | null>(null);
  const [vehicleId, setVehicleId] = useState("");
  const [monthlyDistanceKm, setMonthlyDistanceKm] = useState(1_200);
  const [ownershipYears, setOwnershipYears] = useState(5);
  const [result, setResult] = useState<TcoResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Theo dõi request /tco đang chạy: mỗi lần recalculate() được gọi (đổi xe,
  // kéo slider) huỷ request trước đó và chỉ request MỚI NHẤT mới được phép
  // ghi vào state — tránh phản hồi đến trễ ghi đè kết quả mới hơn.
  const activeRequestRef = useRef<AbortController | null>(null);
  // Debounce cho hai slider: kéo thả bắn ra hàng chục lần onChange, nhưng chỉ
  // request MỘT lần sau khi người dùng dừng kéo ~250ms. Không xung đột với
  // activeRequestRef ở trên — timer chỉ trì hoãn LÚC gọi recalculate(), còn
  // recalculate() vẫn tự huỷ request trước đó như cũ khi thực sự chạy.
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const recalculate = useCallback(
    async (id: string, prov: string, km: number, years: number) => {
    activeRequestRef.current?.abort();
    const controller = new AbortController();
    activeRequestRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      const data = await fetchTco(id, prov, km, years, controller.signal);
      if (activeRequestRef.current !== controller) return; // đã bị request mới hơn thay thế
      setResult(data);
    } catch (caught) {
      if (activeRequestRef.current !== controller) return;
      const code = caught instanceof Error ? caught.message : "unknown";
      setError(
        code === "tco_unavailable"
          ? "Chưa đủ dữ liệu để tính chi phí sở hữu cho mẫu xe này."
          : "Không tính được chi phí sở hữu.",
      );
      setResult(null);
    } finally {
      if (activeRequestRef.current === controller) setBusy(false);
    }
    },
    [],
  );

  const debouncedRecalculate = useCallback(
    (id: string, prov: string, km: number, years: number) => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        void recalculate(id, prov, km, years);
      }, 250);
    },
    [recalculate],
  );

  useEffect(() => () => activeRequestRef.current?.abort(), []);
  useEffect(() => () => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const list = await fetchVehicles({ pageSize: 60 });
        setVehicles(list);
        if (list.length > 0) {
          setVehicleId(list[0].id);
          void recalculate(list[0].id, province, monthlyDistanceKm, ownershipYears);
        }
      } catch {
        setVehiclesError("Không tải được danh sách xe.");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- chỉ chạy 1 lần lúc mount, dùng giá trị mặc định ban đầu
  }, []);

  function handleVehicleChange(id: string) {
    setVehicleId(id);
    void recalculate(id, province, monthlyDistanceKm, ownershipYears);
  }

  function handleProvinceChange(value: string) {
    setProvince(value);
    // Không debounce: đây là dropdown, mỗi lần đổi là một ý định rõ ràng của
    // khách, khác với slider bắn ra hàng chục onChange khi kéo.
    if (vehicleId) void recalculate(vehicleId, value, monthlyDistanceKm, ownershipYears);
  }

  function handleMonthlyKmChange(km: number) {
    setMonthlyDistanceKm(km);
    if (vehicleId) debouncedRecalculate(vehicleId, province, km, ownershipYears);
  }

  function handleOwnershipYearsChange(years: number) {
    setOwnershipYears(years);
    if (vehicleId) debouncedRecalculate(vehicleId, province, monthlyDistanceKm, years);
  }

  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === vehicleId) ?? null;
  const cars = vehicles.filter((vehicle) => vehicle.vehicleType === "car");
  const motorbikes = vehicles.filter((vehicle) => vehicle.vehicleType === "electric_motorbike");

  const breakdownItems = result
    ? [
        { label: "Giá xe", value: result.breakdown.vehicle_price_vnd, icon: CircleDollarSign, count: null },
        { label: "Lệ phí trước bạ", value: result.breakdown.registration_fee_vnd, icon: Info, count: null },
        { label: "Phí biển số", value: result.breakdown.plate_fee_vnd, icon: BadgeCheck, count: null },
        { label: "Đăng kiểm", value: result.breakdown.inspection_fee_vnd, icon: ClipboardCheck, count: result.breakdown.inspection_count },
        { label: "Bảo hiểm TNDS", value: result.breakdown.insurance_vnd, icon: ShieldCheck, count: null },
        { label: "Phí đường bộ", value: result.breakdown.road_fee_vnd, icon: Route, count: null },
        { label: `Tiền điện · ${ownershipYears} năm`, value: result.breakdown.electricity_vnd, icon: BatteryCharging, count: null },
        { label: `Bảo dưỡng · ${ownershipYears} năm`, value: result.breakdown.maintenance_vnd, icon: Wrench, count: result.breakdown.maintenance_count },
      ]
    : [];

  return (
    <div className="tco-layout">
      <section className="tco-controls">
        <span className="eyebrow">Thiết lập giả định</span>
        <h2>Điều chỉnh theo nhu cầu của bạn</h2>
        <label className="field-label">
          Nơi đăng ký xe
          <select value={province} onChange={(event) => handleProvinceChange(event.target.value)}>
            {PROVINCE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field-label">
          Mẫu xe
          <select value={vehicleId} onChange={(event) => handleVehicleChange(event.target.value)}>
            {cars.length > 0 ? (
              <optgroup label="Ô tô điện">
                {cars.map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {vehicle.modelName} {vehicle.variant}
                  </option>
                ))}
              </optgroup>
            ) : null}
            {motorbikes.length > 0 ? (
              <optgroup label="Xe máy điện">
                {motorbikes.map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {vehicle.modelName} {vehicle.variant}
                  </option>
                ))}
              </optgroup>
            ) : null}
          </select>
        </label>
        {vehiclesError ? <p className="tco-error-note">{vehiclesError}</p> : null}
        <label className="range-control">
          <span>
            <strong>Quãng đường mỗi tháng</strong>
            <output>{formatNumber(monthlyDistanceKm)} km</output>
          </span>
          <input min="300" max="3000" step="100" type="range" value={monthlyDistanceKm} onChange={(event) => handleMonthlyKmChange(Number(event.target.value))} />
        </label>
        <label className="range-control">
          <span>
            <strong>Thời gian sở hữu</strong>
            <output>{ownershipYears} năm</output>
          </span>
          <input min="1" max="10" type="range" value={ownershipYears} onChange={(event) => handleOwnershipYearsChange(Number(event.target.value))} />
        </label>
        <div className="tco-assumptions">
          <Info size={17} />
          <p>Kết quả tính theo bảng giả định TCO hiện hành của hệ thống, áp dụng chung cho toàn bộ khu vực và giá điện EVN.</p>
        </div>
      </section>
      <section className="tco-results" aria-live="polite">
        <div className="tco-result-header">
          <div>
            <span className="eyebrow">{selectedVehicle ? `${selectedVehicle.modelName} ${selectedVehicle.variant}` : "Chưa chọn xe"}</span>
            <h2>Chi phí sở hữu dự kiến</h2>
          </div>
          <span>{ownershipYears} năm</span>
        </div>
        {error ? (
          <p className="tco-error-note">{error}</p>
        ) : result ? (
          <>
            <div className="tco-breakdown">
              {breakdownItems.map((item) => {
                const Icon = item.icon;
                return (
                  <div key={item.label}>
                    <span>
                      <Icon size={18} />
                      {item.label}
                    </span>
                    <strong>
                      {formatVnd(item.value)}
                      {item.count !== null ? <small> {item.count} lần</small> : null}
                    </strong>
                  </div>
                );
              })}
            </div>
            <div className="tco-initial">
              <span>Tổng chi phí ban đầu</span>
              <strong>{formatVnd(result.breakdown.total_upfront_vnd)}</strong>
            </div>
            <div className="tco-total">
              <span>Tổng chi phí sở hữu ước tính</span>
              <strong>{formatVnd(result.breakdown.total_ownership_vnd)}</strong>
              <small>≈ {formatVnd(Math.round(result.breakdown.total_ownership_vnd / (ownershipYears * 12)))}/tháng</small>
            </div>
            <p className="tco-region-note">
              Biểu phí áp dụng:{" "}
              <strong>
                {REGION_LABELS[result.assumptions.region_code] ?? result.assumptions.region_code}
              </strong>
            </p>
            <p className="tco-source-note">{result.assumptions.source_note}</p>
            {result.consumption.source === "derived" ? (
              <p className="tco-derived-warning" role="note">
                Mức tiêu thụ {result.consumption.kwh_per_100km} kWh/100km là số suy ra từ dung lượng pin và
                quãng đường công bố ({result.consumption.derivation}). Quãng đường công bố đo theo chu trình
                thử nghiệm, nên mức tiêu thụ thực tế khi chạy hằng ngày thường cao hơn.
              </p>
            ) : null}
          </>
        ) : (
          <p className="tco-source-note">{busy ? "Đang tính chi phí sở hữu..." : "Chọn mẫu xe để xem chi phí sở hữu."}</p>
        )}
        <p className="legal-note">Kết quả chỉ mang tính ước tính, không phải báo giá cuối cùng.</p>
        <div className="tco-actions">
          <Link className="secondary-button" href="/compare">
            Quay lại so sánh
          </Link>
          <Link className="primary-button" href="/test-drive">
            Đặt lịch lái thử
          </Link>
        </div>
      </section>
    </div>
  );
}
