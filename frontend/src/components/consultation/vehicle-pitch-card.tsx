"use client";

import { RichText } from "@/components/common/rich-text";
import { VehicleImage } from "@/components/shared/vehicle-image";
import type { RecommendedVehicle } from "@/types/agent";

/** Giá đến dưới dạng chuỗi số nguyên VND; không có giá hiệu lực thì nói thẳng. */
function formatPrice(value: string | null): string {
  if (value === null) return "Chưa có giá hiệu lực";
  const amount = Number(value);
  return Number.isFinite(amount)
    ? `Giá từ ${amount.toLocaleString("vi-VN")} đ`
    : "Chưa có giá hiệu lực";
}

export function VehiclePitchCard({
  vehicle,
  pitchHidden,
  onSelect,
  disabled = false,
}: Readonly<{
  vehicle: RecommendedVehicle;
  pitchHidden: boolean;
  /** Bỏ trống thì thẻ không có nút chọn — dùng cho thẻ chỉ để xem lại. */
  onSelect?: (vehicle: RecommendedVehicle) => void;
  disabled?: boolean;
}>): React.JSX.Element {
  return (
    <article className="vehicle-pitch-card">
      {/* Dùng `VehicleImage` thay cho `<img>` trần (Sếp 2026-08-25: "ảnh trong
          đoạn chat đang không hiện"). Nó làm hai việc thẻ trần không làm được:
          đổi link Google Drive dạng "xem" sang URL ảnh thật, và khi ảnh vẫn
          hỏng thì hiện khung "Ảnh đang được cập nhật" thay vì một ô vỡ. */}
      <VehicleImage
        alt={vehicle.display_name}
        className="vehicle-pitch-image"
        sizes="(max-width: 760px) 100vw, 320px"
        src={vehicle.image_url}
      />
      <div className="vehicle-pitch-body">
        <h3>{vehicle.display_name}</h3>
        <p className="vehicle-pitch-price">{formatPrice(vehicle.starting_price_vnd)}</p>
        {pitchHidden ? null : (
          <div className="vehicle-pitch-text">
            {/* Đoạn mô tả trong thẻ cũng là Markdown rút gọn: bố cục thẻ
                (ảnh/tên/giá) giữ nguyên, chỉ phần chữ được render đúng. */}
            <RichText text={vehicle.pitch} />
          </div>
        )}
        {/* Sếp 2026-08-26: "hiện ra 3 xe thì người dùng có thể chọn được ngay".
            Trước đây khách phải gõ lại tên xe — vừa mất công vừa dễ gõ sai tên
            phiên bản, mà tên sai thì lượt sau không khớp được mẫu nào. */}
        {onSelect ? (
          <button
            className="vehicle-pitch-select"
            disabled={disabled}
            onClick={() => onSelect(vehicle)}
            type="button"
          >
            Chọn mẫu này
          </button>
        ) : null}
      </div>
    </article>
  );
}
