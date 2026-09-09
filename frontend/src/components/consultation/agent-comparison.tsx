"use client";

import {
  VehicleComparisonTable,
  type ComparisonColumn,
  type ComparisonTableRow,
} from "@/components/comparison/vehicle-comparison";
import { RichText } from "@/components/common/rich-text";
import type { ComparedVehicle, VehicleComparison } from "@/types/agent";

const NO_DATA = "Chưa có dữ liệu";
const PRICE_LABEL = "Giá niêm yết";

/** Giá đến dạng chuỗi số nguyên VND — cùng quy ước với `VehiclePitchCard`. */
function formatPrice(value: string | null): string {
  if (value === null) return "Chưa có giá hiệu lực";
  const amount = Number(value);
  return Number.isFinite(amount) ? `${amount.toLocaleString("vi-VN")} đ` : value;
}

function column(vehicle: ComparedVehicle, index: number): ComparisonColumn {
  return {
    key: vehicle.vehicle_id,
    title: vehicle.display_name,
    // Không có `onRemove`: bảng trong khung chat là ẢNH CHỤP câu trả lời của
    // đúng lượt đó. Cho phép bỏ cột ở đây sẽ sửa lại một tin nhắn đã gửi, và
    // đoạn tóm tắt bên dưới lập tức nói về một bảng không còn tồn tại.
    rankLabel: `Lựa chọn ${index + 1}`,
    imageUrl: vehicle.image_url,
  };
}

/**
 * Bảng so sánh do agent trả về, hiện ngay trong dòng hội thoại.
 *
 * Chỉ ÁNH XẠ payload sang props của `VehicleComparisonTable` — không dựng bảng
 * riêng, không quyết định tiêu chí nào được hiện. Bộ tiêu chí (`spec_fields`) do
 * backend chốt từ chính dữ liệu catalog của các xe trong lượt, nên hai xe máy
 * điện không bao giờ nhận một hàng "Số chỗ ngồi" trống rỗng.
 */
export function AgentComparison({
  comparison,
}: Readonly<{ comparison: VehicleComparison }>): React.JSX.Element | null {
  const found = comparison.vehicles.filter((vehicle) => vehicle.found);
  if (found.length === 0) return null;

  const columns = found.map(column);
  const rows: ComparisonTableRow[] = [
    {
      label: PRICE_LABEL,
      values: found.map((vehicle) => formatPrice(vehicle.starting_price_vnd)),
    },
    ...comparison.spec_fields.map((field) => ({
      label: field.label,
      values: found.map((vehicle) => vehicle.specs[field.code] ?? NO_DATA),
    })),
  ];

  return (
    <div className="agent-comparison">
      <VehicleComparisonTable columns={columns} rows={rows} />
      {comparison.missing_vehicle_names.length > 0 ? (
        <p className="agent-comparison-missing">
          Chưa tìm thấy trong danh mục: {comparison.missing_vehicle_names.join(", ")}.
        </p>
      ) : null}
      {/* Đoạn tóm tắt nằm NGAY DƯỚI phần ảnh/bảng: nó nói về những gì khách vừa
          nhìn thấy, nên đặt trên bảng sẽ bắt họ đọc kết luận trước dữ liệu. */}
      {comparison.summary ? (
        <div className="agent-comparison-summary">
          <RichText text={comparison.summary} />
        </div>
      ) : null}
    </div>
  );
}
