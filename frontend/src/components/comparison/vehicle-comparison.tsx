"use client";

import { AlertCircle, Check, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchVehicles, type CatalogVehicle } from "@/lib/api/vehicles";
import type { VehicleType } from "@/types/demo";
import { formatVnd } from "@/lib/format";
import { resolveCatalogVehicleImage } from "@/lib/vehicle-media";
import { VehicleImage } from "@/components/shared/vehicle-image";
import { useDemoStore } from "@/store/demo-store";

type ComparisonRow = {
  label: string;
  value: (vehicle: CatalogVehicle) => string;
  /** Số để so "xe nào tốt nhất hàng này"; null = không so được. */
  metric: (vehicle: CatalogVehicle) => number | null;
  /** Chiều tốt: giá/phút sạc thấp tốt, tầm chạy/ghế/pin cao tốt. */
  better: "min" | "max";
};

const rows: ComparisonRow[] = [
  { label: "Giá niêm yết", value: (vehicle) => (vehicle.priceVnd === null ? "Chưa có giá" : formatVnd(vehicle.priceVnd)), metric: (vehicle) => vehicle.priceVnd, better: "min" },
  { label: "Tầm hoạt động", value: (vehicle) => (vehicle.rangeKm !== null ? `${vehicle.rangeKm} km` : "Chưa có dữ liệu"), metric: (vehicle) => vehicle.rangeKm, better: "max" },
  { label: "Số ghế", value: (vehicle) => (vehicle.seats ? `${vehicle.seats} chỗ` : "Không áp dụng"), metric: (vehicle) => vehicle.seats, better: "max" },
  { label: "Sạc nhanh", value: (vehicle) => (vehicle.chargeMinutes !== null ? `${vehicle.chargeMinutes} phút` : "Chưa có dữ liệu"), metric: (vehicle) => vehicle.chargeMinutes, better: "min" },
  { label: "Dung lượng pin", value: (vehicle) => (vehicle.batteryCapacityKwh !== null ? `${vehicle.batteryCapacityKwh} kWh` : "Chưa có dữ liệu"), metric: (vehicle) => vehicle.batteryCapacityKwh, better: "max" },
];

/** Cột TỐT NHẤT của một hàng theo số thật; hoà hoặc thiếu số thì không ai được tích. */
function bestColumn(row: ComparisonRow, vehicles: readonly CatalogVehicle[]): number | null {
  const values = vehicles.map((vehicle) => row.metric(vehicle));
  const usable = values.filter((value): value is number => value !== null);
  if (usable.length < 2) return null;
  const best = row.better === "min" ? Math.min(...usable) : Math.max(...usable);
  const winners = values.map((value, index) => (value === best ? index : -1)).filter((index) => index >= 0);
  return winners.length === 1 ? winners[0] : null;
}

/** Một cột của bảng so sánh, đã tách khỏi mọi nguồn dữ liệu. */
export type ComparisonColumn = {
  readonly key: string;
  readonly title: string;
  readonly subtitle?: string | null;
  readonly rankLabel: string;
  readonly imageUrl: string | null;
  /** Có nút "Bỏ xe" hay không. Trang so sánh có, bong bóng chat thì không. */
  readonly onRemove?: () => void;
};

/** Một hàng tiêu chí: nhãn + giá trị theo đúng thứ tự cột. */
export type ComparisonTableRow = {
  readonly label: string;
  readonly values: readonly string[];
  /** Cột thắng hàng này theo SỐ THẬT; undefined = nguồn không so được (đường
      cũ của bong bóng chat), null = hoà/thiếu số — không tích ai. */
  readonly bestIndex?: number | null;
};

/**
 * BẢNG so sánh thuần trình bày — không fetch, không store, không quyết định gì.
 *
 * Tách ra khỏi `VehicleComparison` để bong bóng so sánh trong khung chat dùng
 * lại ĐÚNG bảng này (cùng markup, cùng class CSS, cùng cách xử lý ảnh hỏng) thay
 * vì dựng một bảng thứ hai trông na ná. Hai bảng song song là hai chỗ phải sửa
 * mỗi lần đổi bố cục, và chúng sẽ lệch nhau ngay ở lần sửa đầu tiên.
 */
export function VehicleComparisonTable({
  columns,
  rows: tableRows,
  highlightedRowCount = 0,
}: Readonly<{
  columns: readonly ComparisonColumn[];
  rows: readonly ComparisonTableRow[];
  /**
   * Số hàng ĐẦU được tô đậm ở cột đầu tiên. Mặc định 0 — bảng do agent trả về
   * cố ý không tô: nó là bảng đối chiếu trung lập, và một dấu tích chỉ ở cột
   * đầu đọc như một lời khuyên mà khách chưa hỏi.
   */
  highlightedRowCount?: number;
}>) {
  return (
    <div className="comparison-table-wrap">
      <table className="comparison-table">
        <thead>
          <tr>
            <th>Tiêu chí</th>
            {columns.map((column) => (
              <th key={column.key}>
                <div className="comparison-header">
                  <span className="comparison-rank">{column.rankLabel}</span>
                  <VehicleImage
                    alt={`Ảnh xe ${column.title}`}
                    className="comparison-vehicle-image"
                    sizes="(max-width: 760px) 195px, 260px"
                    src={column.imageUrl}
                  />
                  <h2>{column.title}</h2>
                  {column.subtitle ? <small>{column.subtitle}</small> : null}
                  {column.onRemove ? (
                    <button onClick={column.onRemove} type="button">
                      <X size={14} /> Bỏ xe
                    </button>
                  ) : null}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tableRows.map((row, rowIndex) => (
            <tr key={row.label}>
              <th>{row.label}</th>
              {columns.map((column, columnIndex) => {
                // Hàng mang `bestIndex` thì tích theo SỐ THẬT (Sếp 2026-08-31:
                // "cứ xe pick đầu là 3 hàng đầu tích V, không thấy dựa tiêu chí
                // gì" — tô cột 0 vô điều kiện là một lời khen bịa). Nguồn không
                // có số (bong bóng chat) giữ đường cũ.
                const highlighted =
                  row.bestIndex !== undefined
                    ? row.bestIndex === columnIndex
                    : rowIndex < highlightedRowCount && columnIndex === 0;
                return (
                  <td className={highlighted ? "is-highlight" : ""} key={column.key}>
                    {highlighted ? <Check size={15} /> : null}
                    {row.values[columnIndex] ?? "Chưa có dữ liệu"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function VehicleComparison() {
  const { state, toggleSelectedVehicle } = useDemoStore();
  const [vehicles, setVehicles] = useState<CatalogVehicle[]>([]);
  const [pickerType, setPickerType] = useState<VehicleType | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void (async () => {
      setLoading(true);
      setLoadError(null);
      try {
        setVehicles(await fetchVehicles({ pageSize: 60 }));
      } catch {
        setLoadError("Không tải được danh sách xe.");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selected = state.selectedVehicleIds.map((id) => vehicles.find((vehicle) => vehicle.id === id)).filter((vehicle): vehicle is CatalogVehicle => Boolean(vehicle));
  // Tab loại xe (Sếp 2026-08-31: "quá nhiều xe, không hình dung được" — dãy nút
  // chữ trần trộn cả ô tô lẫn xe máy). Mặc định theo xe ĐANG chọn; chưa chọn gì
  // thì ưu tiên ô tô, catalog không có ô tô thì rơi về loại đang có.
  const hasCar = vehicles.some((vehicle) => vehicle.vehicleType === "car");
  const activeType: VehicleType = pickerType ?? selected[0]?.vehicleType ?? (hasCar ? "car" : "electric_motorbike");
  const pickable = vehicles.filter((vehicle) => vehicle.vehicleType === activeType);

  function tryAdd(vehicleId: string): void {
    const vehicle = vehicles.find((item) => item.id === vehicleId);
    const selectedType = selected[0]?.vehicleType;
    if (vehicle && selectedType && vehicle.vehicleType !== selectedType) {
      setMessage("Chỉ có thể so sánh các phương tiện cùng loại.");
      return;
    }
    setMessage("");
    toggleSelectedVehicle(vehicleId);
  }

  if (loading) {
    return <div className="state-panel"><h2>Đang tải danh sách xe...</h2></div>;
  }

  if (loadError) {
    return <div className="state-panel"><h2>{loadError}</h2><p>Vui lòng thử tải lại trang.</p></div>;
  }

  const columns: ComparisonColumn[] = selected.map((vehicle, index) => ({
    key: vehicle.id,
    title: vehicle.modelName,
    subtitle: vehicle.variant,
    // "Lựa chọn N" cho MỌI cột: thứ tự bấm chọn không phải một bảng xếp hạng,
    // gọi cột đầu là "Đề xuất hàng đầu" là khen không căn cứ (Sếp 2026-08-31).
    rankLabel: `Lựa chọn ${index + 1}`,
    imageUrl: resolveCatalogVehicleImage(vehicle),
    onRemove: () => toggleSelectedVehicle(vehicle.id),
  }));
  const tableRows: ComparisonTableRow[] = rows.map((row) => ({
    label: row.label,
    values: selected.map((vehicle) => row.value(vehicle)),
    bestIndex: bestColumn(row, selected),
  }));

  return (
    <>
      {message ? <div className="inline-alert" role="alert"><AlertCircle size={18} />{message}<button onClick={() => setMessage("")} aria-label="Đóng cảnh báo" type="button"><X size={16} /></button></div> : null}
      <div className="comparison-picker-panel">
        <div className="comparison-picker-head">
          <span>Đang so sánh {selected.length}/3 xe</span>
          <div aria-label="Loại phương tiện" className="comparison-type-tabs" role="group">
            <button aria-pressed={activeType === "car"} onClick={() => setPickerType("car")} type="button">
              Ô tô điện
            </button>
            <button
              aria-pressed={activeType === "electric_motorbike"}
              onClick={() => setPickerType("electric_motorbike")}
              type="button"
            >
              Xe máy điện
            </button>
          </div>
        </div>
        {pickable.length === 0 ? (
          <p className="comparison-picker-empty">Chưa có xe thuộc nhóm này trong danh mục.</p>
        ) : (
          <div aria-label="Chọn xe để so sánh" className="comparison-vehicle-grid" role="group">
            {pickable.map((vehicle) => {
              const isSelected = state.selectedVehicleIds.includes(vehicle.id);
              return (
                <button
                  aria-pressed={isSelected}
                  className="comparison-vehicle-option"
                  key={vehicle.id}
                  onClick={() => (isSelected ? toggleSelectedVehicle(vehicle.id) : tryAdd(vehicle.id))}
                  type="button"
                >
                  {/* Ảnh là TRANG TRÍ của nút (tên nút đã nói đủ) — alt rỗng +
                      aria-hidden để không lẫn với ảnh cột trong bảng so sánh. */}
                  {/* `VehicleImage` dùng next/image `fill`: khung PHẢI có chiều
                      cao (class dưới) — bọc ngoài mà không truyền class là khung
                      cao 0 và ảnh tàng hình (Sếp báo 2026-08-31). */}
                  <span aria-hidden="true" className="comparison-option-thumb">
                    <VehicleImage
                      alt=""
                      className="comparison-option-image"
                      sizes="180px"
                      src={resolveCatalogVehicleImage(vehicle)}
                    />
                  </span>
                  <span className="comparison-option-name">
                    {vehicle.modelName} {vehicle.variant}
                  </span>
                  {isSelected ? (
                    <span className="comparison-option-badge">
                      <Check size={12} /> Đang so sánh
                    </span>
                  ) : null}
                </button>
              );
            })}
          </div>
        )}
      </div>
      {selected.length < 2 ? <div className="state-panel"><h2>Chọn ít nhất hai xe</h2><p>Bạn có thể chọn tối đa ba phương tiện cùng loại.</p><Link className="primary-button" href="/recommendations">Quay lại đề xuất</Link></div> : (
        // `highlightedRowCount={4}` giữ nguyên hành vi cũ của TRANG so sánh:
        // bốn tiêu chí đầu tô đậm ở cột "Đề xuất hàng đầu".
        <VehicleComparisonTable columns={columns} highlightedRowCount={4} rows={tableRows} />
      )}
      <div className="comparison-footer"><p><strong>Gợi ý:</strong> so sánh thêm tại trang TCO để xem chi phí sở hữu theo thời gian.</p><div><Link className="secondary-button" href="/tco">Xem TCO</Link><Link className="primary-button" href="/test-drive">Đặt lịch lái thử</Link></div></div>
    </>
  );
}
