"use client";

import {
  AlertTriangle,
  BatteryCharging,
  Cpu,
  Gauge,
  LoaderCircle,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { VehicleImage } from "@/components/shared/vehicle-image";
import {
  fetchVehicle,
  type CatalogVehicle,
  type VehicleShowcaseItem,
} from "@/lib/api/vehicles";
import { formatVnd } from "@/lib/format";
import type { VehicleMenuEntry } from "@/mocks/vehicle-menu";

const PLUS_SLUG = "vinfast-vf-8-plus-extended-range";
const VISIBLE_COLOR_KEYS = new Set([
  "colors.ce11",
  "colors.ce22",
  "colors.ce18",
  "colors.ce1m",
  "colors.171v",
  "colors.1v18",
]);
const COLOR_SWATCH_GRADIENTS: Record<string, string> = {
  "colors.ce11": "radial-gradient(circle at 32% 24%, #62666a 0, #191b1e 32%, #030405 72%)",
  "colors.ce22": "radial-gradient(circle at 32% 24%, #9cae9d 0, #526556 34%, #27362d 72%)",
  "colors.ce18": "radial-gradient(circle at 32% 24%, #ffffff 0, #f4f4f1 42%, #cfd1d0 82%)",
  "colors.ce1m": "radial-gradient(circle at 32% 24%, #ff7378 0, #d92736 38%, #8d101b 82%)",
  "colors.171v": "linear-gradient(180deg, #aeb0b1 0 46%, #646667 50% 100%)",
  "colors.1v18": "linear-gradient(180deg, #f7f7f5 0 46%, #bfc1c0 50% 100%)",
};
const SECTION_LINKS = [
  ["overview", "Tổng quan"],
  ["colors", "Màu sắc"],
  ["exterior", "Ngoại thất"],
  ["interior", "Nội thất"],
  ["technology", "Công nghệ"],
  ["performance", "Vận hành"],
  ["safety", "An toàn"],
  ["offers", "Ưu đãi"],
  ["versions", "Các phiên bản"],
] as const;

type ShowcaseData = {
  eco: CatalogVehicle;
  plus: CatalogVehicle;
};

function bySection(items: VehicleShowcaseItem[], section: string): VehicleShowcaseItem[] {
  return items.filter((item) => item.section === section).sort((a, b) => a.order - b.order);
}

function spec(vehicle: CatalogVehicle, key: string): string | number | boolean | null {
  return vehicle.specs[key] ?? null;
}

function metric(value: string | number | boolean | null, suffix = ""): string {
  if (value === null || value === "") return "Chưa có dữ liệu";
  if (typeof value === "boolean") return `${String(value)}${suffix}`;
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    return `${numeric.toLocaleString("vi-VN", { maximumFractionDigits: 3 })}${suffix}`;
  }
  return `${String(value)}${suffix}`;
}

function VariantCard({ image, vehicle }: Readonly<{ image?: VehicleShowcaseItem; vehicle: CatalogVehicle }>) {
  return (
    <article className="vf8-variant-card">
      <VehicleImage
        alt={image?.mediaAlt ?? `Ảnh ${vehicle.modelName} ${vehicle.variant}`}
        className="vf8-variant-image"
        sizes="(max-width: 760px) 92vw, 42vw"
        src={image?.mediaUrl ?? vehicle.imageUrl}
      />
      <div className="vf8-variant-card-copy">
        <span>{vehicle.modelName}</span>
        <h3>{vehicle.variant.replace(" Extended Range", "")}</h3>
        <p>Giá niêm yết</p>
        <strong>{vehicle.priceVnd === null ? "Chưa có giá" : formatVnd(vehicle.priceVnd)}</strong>
        <dl>
          <div><dt>Quãng đường</dt><dd>{metric(vehicle.rangeKm, " km")}</dd></div>
          <div><dt>Công suất</dt><dd>{metric(spec(vehicle, "motor_power_kw"), " kW")}</dd></div>
        </dl>
      </div>
    </article>
  );
}

function MediaSection({
  fourColumns = false,
  id,
  items,
  title,
}: Readonly<{
  fourColumns?: boolean;
  id: string;
  items: VehicleShowcaseItem[];
  title: string;
}>) {
  if (items.length === 0) return null;
  return (
    <section className="vf8-content-section" id={id}>
      <header className="vf8-section-heading">
        <h2>{title}</h2>
      </header>
      <div className={fourColumns ? "vf8-feature-grid is-four-column" : "vf8-feature-grid"}>
        {items.map((item) => (
          <article className="vf8-feature-card" key={item.id}>
            <VehicleImage
              alt={item.mediaAlt}
              className="vf8-feature-image"
              sizes={fourColumns ? "(max-width: 760px) 100vw, 24vw" : "(max-width: 760px) 100vw, 48vw"}
              src={item.mediaUrl}
            />
            <div><h3>{item.title}</h3><p>{item.description}</p></div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function Vf8Showcase({ vehicle }: Readonly<{ vehicle: VehicleMenuEntry }>) {
  const [data, setData] = useState<ShowcaseData | null>(null);
  const [error, setError] = useState(false);
  const [activeSection, setActiveSection] = useState("overview");
  const [selectedColor, setSelectedColor] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([fetchVehicle(vehicle.catalogSlug!), fetchVehicle(PLUS_SLUG)])
      .then(([eco, plus]) => {
        if (!cancelled) setData({ eco, plus });
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => { cancelled = true; };
  }, [vehicle.catalogSlug]);

  useEffect(() => {
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible?.target.id) setActiveSection(visible.target.id);
      },
      { rootMargin: "-24% 0px -58%", threshold: [0.05, 0.35, 0.7] },
    );
    for (const [id] of SECTION_LINKS) {
      const section = document.getElementById(id);
      if (section) observer.observe(section);
    }
    return () => observer.disconnect();
  }, [data]);

  const items = useMemo(() => data?.eco.showcaseItems ?? [], [data]);
  const grouped = useMemo(() => ({
    colors: bySection(items, "colors").filter((item) => VISIBLE_COLOR_KEYS.has(item.key)),
    exterior: bySection(items, "exterior"),
    interior: bySection(items, "interior"),
    overview: bySection(items, "overview"),
    performance: bySection(items, "performance"),
    safety: bySection(items, "safety"),
    technology: bySection(items, "technology"),
    versions: bySection(items, "versions"),
  }), [items]);
  const hero = grouped.overview.find((item) => item.key === "overview.hero-wide") ?? grouped.overview[0];
  const selectedColorItem = grouped.colors[selectedColor] ?? grouped.colors[0];
  const promotionCount = new Set([
    ...(data?.eco.promotionIds ?? []),
    ...(data?.plus.promotionIds ?? []),
  ]).size;

  if (!data) {
    return (
      <div className="vf8-loading" role="status">
        {error ? <AlertTriangle aria-hidden="true" /> : <LoaderCircle aria-hidden="true" className="spin" />}
        <h1>VF 8</h1>
        <p>{error ? "Thông tin sản phẩm hiện chưa sẵn sàng. Vui lòng thử lại sau." : "Đang chuẩn bị trải nghiệm VF 8..."}</p>
      </div>
    );
  }

  return (
    <div className="vf8-page">
      <section className="vf8-hero" id="overview">
        <VehicleImage
          alt={hero?.mediaAlt ?? "VinFast VF 8"}
          className="vf8-hero-image"
          preload
          sizes="100vw"
          src={hero?.mediaUrl ?? vehicle.imageUrl}
        />
        <div className="vf8-hero-overlay">
          <span>SUV điện cao cấp</span>
          <h1>VF 8</h1>
          <p>{hero?.description}</p>
          <Link className="primary-button" href="/test-drive">Đăng ký lái thử</Link>
        </div>
      </section>

      <nav className="vf8-model-nav" aria-label="Điều hướng nội dung VF 8">
        <a className="vf8-model-mark" href="#overview" onClick={() => setActiveSection("overview")}>VF8</a>
        <div className="vf8-model-links">
          {SECTION_LINKS.map(([id, label]) => (
            <a className={activeSection === id ? "is-active" : ""} href={`#${id}`} key={id}>{label}</a>
          ))}
        </div>
      </nav>

      <section className="vf8-intro">
        <h2>Cá tính vượt trội</h2>
        <p>Thiết kế cân bằng giữa vẻ ngoài mạnh mẽ, không gian tiện nghi và khả năng vận hành linh hoạt cho từng hành trình.</p>
      </section>

      <section className="vf8-variants-preview">
        <VariantCard image={grouped.versions.find((item) => item.key.endsWith(".eco"))} vehicle={data.eco} />
        <VariantCard image={grouped.versions.find((item) => item.key.endsWith(".plus"))} vehicle={data.plus} />
      </section>

      <section className="vf8-color-section" id="colors">
        <header className="vf8-color-heading">
          <h2>Màu sắc tạo nên dấu ấn riêng</h2>
          <p>Khám phá bảng màu ngoại thất và chọn sắc màu thể hiện dấu ấn riêng của bạn.</p>
        </header>
        <VehicleImage
          alt={selectedColorItem?.mediaAlt ?? "Màu ngoại thất VF 8"}
          className="vf8-color-image"
          sizes="(max-width: 900px) 100vw, 64vw"
          src={selectedColorItem?.mediaUrl}
        />
        <div className="vf8-color-controls">
          <div className="vf8-color-list" role="list" aria-label="Màu ngoại thất VF 8">
            {grouped.colors.map((color, index) => (
              <button
                aria-label={color.title}
                aria-pressed={selectedColor === index}
                className={selectedColor === index ? "is-selected" : ""}
                key={color.id}
                onClick={() => setSelectedColor(index)}
                title={color.title}
                type="button"
              >
                <span style={{ backgroundImage: COLOR_SWATCH_GRADIENTS[color.key] }} />
              </button>
            ))}
          </div>
          <strong>{selectedColorItem?.title}</strong>
          <small>Màu sắc hiển thị có thể chênh lệch nhẹ tùy màn hình.</small>
        </div>
      </section>

      <MediaSection fourColumns id="exterior" items={grouped.exterior} title="Ngoại thất hiện đại và mạnh mẽ" />
      <MediaSection id="interior" items={grouped.interior} title="Nội thất hướng đến người lái" />

      <section className="vf8-performance" id="performance">
        <VehicleImage
          alt={grouped.performance[0]?.mediaAlt ?? "VF 8 trên hành trình"}
          className="vf8-performance-image"
          sizes="100vw"
          src={grouped.performance[0]?.mediaUrl}
        />
        <div className="vf8-performance-panel">
          <span><Zap aria-hidden="true" size={18} /> Phiên bản Eco</span>
          <h2>Sẵn sàng cho từng hành trình</h2>
          <div className="vf8-metric-grid">
            <div><Gauge aria-hidden="true" /><strong>{metric(data.eco.rangeKm, " km")}</strong><span>Quãng đường ({metric(spec(data.eco, "range_cycle"))})</span></div>
            <div><Sparkles aria-hidden="true" /><strong>{metric(spec(data.eco, "acceleration_0_100_seconds"), " giây")}</strong><span>Tăng tốc 0–100 km/h</span></div>
            <div><Zap aria-hidden="true" /><strong>{metric(spec(data.eco, "motor_power_kw"), " kW")}</strong><span>Công suất động cơ</span></div>
            <div><BatteryCharging aria-hidden="true" /><strong>{metric(data.eco.chargeMinutes, " phút")}</strong><span>Sạc nhanh {metric(spec(data.eco, "fast_charge_from_percent"), "%")}–{metric(spec(data.eco, "fast_charge_to_percent"), "%")}</span></div>
          </div>
        </div>
      </section>

      <MediaSection id="technology" items={grouped.technology} title="Công nghệ đồng hành" />
      <MediaSection id="safety" items={grouped.safety} title="An toàn chủ động và kết nối" />

      <section className="vf8-data-gap" id="offers">
        <Sparkles aria-hidden="true" />
        <div>
          <span>Ưu đãi dành cho VF 8</span>
          <h2>{promotionCount > 0 ? `${promotionCount} chương trình ưu đãi đang áp dụng` : "Khám phá chính sách dành riêng cho VF 8"}</h2>
          <p>Liên hệ tư vấn viên để được giới thiệu chính sách phù hợp với phiên bản và nhu cầu sở hữu của bạn.</p>
          <Link href="/consultation">Nhận tư vấn ưu đãi</Link>
        </div>
      </section>

      <section className="vf8-versions" id="versions">
        <header className="vf8-section-heading"><h2>Chọn VF 8 phù hợp với bạn</h2></header>
        <div className="vf8-version-table" role="table" aria-label="So sánh VF 8 Eco và Plus">
          <div className="vf8-version-row is-heading" role="row"><span>Thông số nổi bật</span><strong>Eco</strong><strong>Plus</strong></div>
          {[
            ["Giá", data.eco.priceVnd === null ? "Chưa có" : formatVnd(data.eco.priceVnd), data.plus.priceVnd === null ? "Chưa có" : formatVnd(data.plus.priceVnd)],
            ["Quãng đường", metric(data.eco.rangeKm, " km"), metric(data.plus.rangeKm, " km")],
            ["Công suất", metric(spec(data.eco, "motor_power_kw"), " kW"), metric(spec(data.plus, "motor_power_kw"), " kW")],
            ["Mô-men xoắn", metric(spec(data.eco, "torque_nm"), " Nm"), metric(spec(data.plus, "torque_nm"), " Nm")],
            ["Tăng tốc 0–100 km/h", metric(spec(data.eco, "acceleration_0_100_seconds"), " giây"), metric(spec(data.plus, "acceleration_0_100_seconds"), " giây")],
          ].map(([label, eco, plus]) => <div className="vf8-version-row" key={label} role="row"><span>{label}</span><strong>{eco}</strong><strong>{plus}</strong></div>)}
        </div>
      </section>

      <section className="vf8-final-cta">
        <ShieldCheck aria-hidden="true" />
        <h2>Khám phá VF 8 theo cách của bạn</h2>
        <p>Đặt lịch lái thử hoặc trò chuyện cùng trợ lý để tìm phiên bản phù hợp với bạn.</p>
        <div><Link className="primary-button" href="/test-drive">Đăng ký lái thử</Link><Link className="secondary-button" href="/consultation"><Cpu aria-hidden="true" size={17} /> Nhờ AI tư vấn</Link></div>
      </section>
    </div>
  );
}
