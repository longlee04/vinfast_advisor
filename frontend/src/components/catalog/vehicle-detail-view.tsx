"use client";

import {
  ArrowLeft,
  BatteryCharging,
  BatteryFull,
  CarFront,
  Check,
  Gauge,
  LoaderCircle,
  UsersRound,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { formatVnd } from "@/lib/format";
import { fetchVehicle, type CatalogVehicle } from "@/lib/api/vehicles";
import { VinFastVehicleViewer } from "@/components/showroom/vinfast-vehicle-viewer";
import type { MotorbikeMenuEntry } from "@/mocks/motorbike-menu";
import type { VehicleMenuCategoryId, VehicleMenuEntry } from "@/mocks/vehicle-menu";
import { useDemoStore } from "@/store/demo-store";

const CATEGORY_DESCRIPTIONS: Record<VehicleMenuCategoryId, string> = {
  electric: "Khám phá thông số vận hành, phạm vi di chuyển và các lựa chọn phù hợp với nhu cầu của bạn.",
  gasoline: "Thông tin về dòng xe động cơ xăng trong danh mục sản phẩm của hệ thống.",
  service: "Dòng xe được thiết kế cho nhu cầu kinh doanh, vận tải và dịch vụ chuyên biệt.",
};

type VehicleDetailMenuEntry = VehicleMenuEntry | MotorbikeMenuEntry;

function getCategoryDescription(vehicle: VehicleDetailMenuEntry): string {
  if ("categoryDescription" in vehicle) return vehicle.categoryDescription;
  return CATEGORY_DESCRIPTIONS[vehicle.categoryId];
}

export function VehicleDetailView({ vehicle }: Readonly<{ vehicle: VehicleDetailMenuEntry }>) {
  const [catalogVehicle, setCatalogVehicle] = useState<CatalogVehicle | null>(null);
  const [loading, setLoading] = useState(Boolean(vehicle.catalogSlug));
  const { state, toggleSelectedVehicle } = useDemoStore();

  useEffect(() => {
    let cancelled = false;

    if (!vehicle.catalogSlug) {
      return;
    }

    void fetchVehicle(vehicle.catalogSlug)
      .then((detail) => {
        if (!cancelled) setCatalogVehicle(detail);
      })
      .catch(() => {
        if (!cancelled) setCatalogVehicle(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [vehicle.catalogSlug]);

  const selected = catalogVehicle
    ? state.selectedVehicleIds.includes(catalogVehicle.id)
    : false;

  return (
    <div className="vehicle-detail-page">
      <Link className="vehicle-detail-back" href="/vehicles">
        <ArrowLeft aria-hidden="true" size={17} /> Tất cả mẫu xe
      </Link>

      <section className="vehicle-detail-hero-panel">
        <div className="vehicle-detail-copy">
          <span className="eyebrow">{vehicle.categoryLabel}</span>
          <h1>{vehicle.name}</h1>
          <p>{getCategoryDescription(vehicle)}</p>

          <div className="vehicle-detail-data-state" aria-live="polite">
            {loading ? (
              <><LoaderCircle aria-hidden="true" className="spin" size={17} /> Đang tải thông tin xe...</>
            ) : catalogVehicle ? (
              <><Check aria-hidden="true" size={17} /> Thông tin sản phẩm</>
            ) : (
              <><CarFront aria-hidden="true" size={17} /> Thông tin chi tiết đang được cập nhật</>
            )}
          </div>

          {catalogVehicle?.priceVnd !== null && catalogVehicle?.priceVnd !== undefined ? (
            <div className="vehicle-detail-price">
              <span>Giá tham khảo</span>
              <strong>{formatVnd(catalogVehicle.priceVnd)}</strong>
            </div>
          ) : null}

          <div className="vehicle-detail-actions">
            <Link className="primary-button" href="/consultation">Nhờ AI tư vấn</Link>
            <Link className="secondary-button" href="/test-drive">Đăng ký lái thử</Link>
            <button
              className={selected ? "compare-card-button is-selected" : "compare-card-button"}
              disabled={!catalogVehicle}
              onClick={() => {
                if (catalogVehicle) toggleSelectedVehicle(catalogVehicle.id);
              }}
              type="button"
            >
              {catalogVehicle ? (selected ? "Đã chọn so sánh" : "Thêm vào so sánh") : "Chưa thể so sánh"}
            </button>
          </div>
        </div>

        <div className="vehicle-detail-main-visual">
          <VinFastVehicleViewer
            modelName={vehicle.name}
            posterUrl={vehicle.imageUrl}
            variant={catalogVehicle?.variant ?? ""}
            vehicleId={vehicle.id}
          />
        </div>
      </section>

      {catalogVehicle ? (
        <section className="vehicle-detail-information" aria-labelledby="vehicle-specifications-title">
          <div className="vehicle-detail-section-heading">
            <span className="eyebrow">Dữ liệu sản phẩm</span>
            <h2 id="vehicle-specifications-title">Thông tin nổi bật</h2>
            <p>Những thông số nổi bật giúp bạn dễ dàng tìm hiểu và so sánh xe.</p>
          </div>
          <div className="vehicle-detail-spec-grid">
            {catalogVehicle.rangeKm !== null ? (
              <div><Gauge aria-hidden="true" size={22} /><span>Quãng đường</span><strong>{catalogVehicle.rangeKm} km</strong></div>
            ) : null}
            {catalogVehicle.seats !== null ? (
              <div><UsersRound aria-hidden="true" size={22} /><span>Số chỗ</span><strong>{catalogVehicle.seats} chỗ</strong></div>
            ) : null}
            {catalogVehicle.batteryCapacityKwh !== null ? (
              <div><BatteryFull aria-hidden="true" size={22} /><span>Dung lượng pin</span><strong>{catalogVehicle.batteryCapacityKwh} kWh</strong></div>
            ) : null}
            {catalogVehicle.chargeMinutes !== null ? (
              <div><BatteryCharging aria-hidden="true" size={22} /><span>Thời gian sạc</span><strong>{catalogVehicle.chargeMinutes} phút</strong></div>
            ) : null}
          </div>
        </section>
      ) : (
        <section className="vehicle-detail-pending" aria-labelledby="vehicle-pending-title">
          <CarFront aria-hidden="true" size={30} strokeWidth={1.4} />
          <div>
            <h2 id="vehicle-pending-title">Dữ liệu sản phẩm đang được hoàn thiện</h2>
            <p>Bạn vẫn có thể yêu cầu AI tư vấn hoặc đăng ký lái thử. Thông số và tính năng chi tiết sẽ được cập nhật trong thời gian sớm nhất.</p>
          </div>
        </section>
      )}
    </div>
  );
}
