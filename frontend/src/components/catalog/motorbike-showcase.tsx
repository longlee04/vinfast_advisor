"use client";

import { BatteryCharging, Cpu, Gauge, LoaderCircle, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { VehicleImage } from "@/components/shared/vehicle-image";
import { fetchVehicle, type CatalogVehicle } from "@/lib/api/vehicles";
import { formatVnd } from "@/lib/format";
import type { MotorbikeMenuEntry } from "@/mocks/motorbike-menu";

function formatMetric(value: unknown, unit: string): string {
  const numeric = Number(value);
  if (value === null || value === undefined || value === "" || !Number.isFinite(numeric)) {
    return "Đang cập nhật";
  }
  return `${numeric.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} ${unit}`;
}

export function MotorbikeShowcase({ vehicle }: Readonly<{ vehicle: MotorbikeMenuEntry }>) {
  const [catalog, setCatalog] = useState<CatalogVehicle | null>(null);
  const [loading, setLoading] = useState(Boolean(vehicle.catalogSlug));

  useEffect(() => {
    let cancelled = false;
    void fetchVehicle(vehicle.catalogSlug)
      .then((value) => { if (!cancelled) setCatalog(value); })
      .catch(() => { if (!cancelled) setCatalog(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [vehicle.catalogSlug]);

  return (
    <div className="motorbike-showcase-page">
      <nav aria-label={`Điều hướng ${vehicle.name}`} className="motorbike-showcase-nav">
        <strong>{vehicle.name}</strong>
        <div><a href="#overview">Tổng quan</a><a href="#specifications">Thông số</a><a href="#price">Giá xe</a></div>
      </nav>

      <section className="motorbike-showcase-hero" id="overview">
        <VehicleImage alt={`VinFast ${vehicle.name}`} className="motorbike-showcase-image" preload sizes="100vw" src={vehicle.detailImageUrl} />
        <div className="motorbike-showcase-title">
          <span>{vehicle.categoryLabel}</span><h1>{vehicle.name}</h1><p>{vehicle.categoryDescription}</p>
        </div>
      </section>

      <section className="motorbike-showcase-specifications" id="specifications">
        <div className="motorbike-showcase-spec-heading">
          <span>Khả năng vận hành — {catalog?.variant || "phiên bản hiện hành"}</span>
          <h2>Linh hoạt cho từng hành trình</h2>
          <p>Quãng đường thực tế có thể thay đổi theo tải trọng, tốc độ, địa hình và điều kiện sử dụng.</p>
        </div>
        <div className="motorbike-showcase-metrics">
          <div><Gauge aria-hidden="true" /><strong>{formatMetric(catalog?.specs.max_speed_kmh, "km/h")}</strong><span>Vận tốc tối đa</span></div>
          <div><BatteryCharging aria-hidden="true" /><strong>{formatMetric(catalog?.rangeKm, "km")}</strong><span>Quãng đường tham chiếu</span></div>
          <div><Zap aria-hidden="true" /><strong>{formatMetric(catalog?.specs.max_power_w, "W")}</strong><span>Công suất tối đa</span></div>
        </div>
      </section>

      <section className="motorbike-showcase-price" id="price">
        <div>
          <span className="eyebrow">Giá xe</span>
          <h2>{catalog?.priceVnd ? formatVnd(catalog.priceVnd) : "Liên hệ tư vấn"}</h2>
          <p>Khám phá mức giá và lựa chọn pin phù hợp với nhu cầu di chuyển hằng ngày của bạn.</p>
          <div className="motorbike-showcase-state" aria-live="polite">
            {loading ? <><LoaderCircle className="spin" size={17} /> Đang tải thông tin sản phẩm...</> : <>Tư vấn viên sẵn sàng hỗ trợ bạn chọn phiên bản phù hợp.</>}
          </div>
        </div>
        <div className="motorbike-showcase-actions">
          <Link className="primary-button" href="/consultation"><Cpu aria-hidden="true" size={17} /> Nhờ AI tư vấn</Link>
          <Link className="secondary-button" href="/test-drive">Đăng ký lái thử</Link>
        </div>
      </section>
    </div>
  );
}
