"use client";

import {
  Armchair,
  BatteryCharging,
  BatteryFull,
  Cpu,
  Gauge,
  Palette,
  ShieldCheck,
  Sparkles,
  UsersRound,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { VehicleImage } from "@/components/shared/vehicle-image";
import { fetchVehicle, type CatalogVehicle } from "@/lib/api/vehicles";
import type { CarEditorial } from "@/lib/car-editorial";
import { formatVnd } from "@/lib/format";
import type { VehicleMenuEntry } from "@/mocks/vehicle-menu";

const SECTION_LINKS = [
  ["overview", "Tổng quan"],
  ["colors", "Màu sắc"],
  ["exterior", "Ngoại thất"],
  ["interior", "Nội thất"],
  ["performance", "Vận hành"],
  ["safety", "An toàn"],
  ["offers", "Ưu đãi"],
] as const;

function metric(value: unknown, suffix: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return `${String(value)}${suffix}`;
  return `${numeric.toLocaleString("vi-VN", { maximumFractionDigits: 3 })}${suffix}`;
}

function resolveHero(vehicle: VehicleMenuEntry, catalog: CatalogVehicle | null): string {
  return catalog?.showcaseItems.find((item) => item.section === "overview")?.mediaUrl
    ?? vehicle.imageUrl
    ?? catalog?.imageUrl
    ?? "";
}

export function CarShowcase({
  editorial,
  vehicle,
}: Readonly<{
  editorial: CarEditorial | null;
  vehicle: VehicleMenuEntry;
}>) {
  const [catalog, setCatalog] = useState<CatalogVehicle | null>(null);
  const [activeSection, setActiveSection] = useState("overview");
  const [selectedColor, setSelectedColor] = useState(0);

  useEffect(() => {
    let cancelled = false;
    if (!vehicle.catalogSlug) {
      return;
    }
    void fetchVehicle(vehicle.catalogSlug)
      .then((value) => { if (!cancelled) setCatalog(value); })
      .catch(() => { if (!cancelled) setCatalog(null); });
    return () => { cancelled = true; };
  }, [vehicle.catalogSlug]);

  useEffect(() => {
    if (!("IntersectionObserver" in window)) return;
    const sections = SECTION_LINKS
      .map(([id]) => document.getElementById(id))
      .filter((section): section is HTMLElement => section !== null);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (visible?.target.id) setActiveSection(visible.target.id);
      },
      { rootMargin: "-24% 0px -58%", threshold: [0.08, 0.25, 0.5] },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const promotionCount = new Set(catalog?.promotionIds ?? []).size;
  const colorOptions = ["Solar Ruby", "Zenith Grey", "Urban Mint", "Infinity Blanc", "Jet Black"];
  const swatches = ["#a80f26", "#777b80", "#8b927f", "#f3f3ef", "#111214"];
  const summary = editorial?.summary
    || (vehicle.categoryId === "service"
      ? "Giải pháp di chuyển được phát triển cho nhu cầu vận hành dịch vụ chuyên nghiệp."
      : "Thiết kế hiện đại, vận hành linh hoạt và sẵn sàng đồng hành cùng mọi nhịp sống.");

  return (
    <div className="car-showcase-page">
      <nav aria-label={`Điều hướng ${vehicle.name}`} className="car-showcase-nav">
        <strong>{vehicle.name}</strong>
        <div>
          {SECTION_LINKS.map(([id, label]) => (
            <a aria-current={activeSection === id ? "location" : undefined} className={activeSection === id ? "is-active" : ""} href={`#${id}`} key={id}>{label}</a>
          ))}
        </div>
      </nav>

      <section className="car-showcase-hero" id="overview">
        <VehicleImage
          alt={`VinFast ${vehicle.name}`}
          className="car-showcase-hero-image"
          preload
          sizes="100vw"
          src={resolveHero(vehicle, catalog)}
        />
        <div className="car-showcase-hero-copy">
          <span>{vehicle.categoryLabel}</span>
          <h1>{vehicle.name}</h1>
          <p>{summary}</p>
          <div className="car-showcase-actions">
            <Link className="primary-button" href="/consultation"><Cpu aria-hidden="true" size={17} /> Nhờ AI tư vấn</Link>
            <Link className="secondary-button" href="/test-drive">Đăng ký lái thử</Link>
          </div>
        </div>
      </section>

      <section className="car-showcase-intro">
        <span className="eyebrow">Thiết kế hướng tới trải nghiệm</span>
        <h2>Một lựa chọn VinFast dành cho nhịp sống hiện đại</h2>
        <p>{summary}</p>
      </section>

      <section className="car-showcase-colors" id="colors">
        <header><Palette aria-hidden="true" /><span className="eyebrow">Màu sắc</span><h2>Dấu ấn riêng trong từng sắc màu</h2></header>
        <VehicleImage alt={`${vehicle.name} — ${colorOptions[selectedColor]}`} className="car-showcase-color-image" sizes="100vw" src={resolveHero(vehicle, catalog)} />
        <div className="car-showcase-color-picker"><strong>{colorOptions[selectedColor]}</strong><div>{colorOptions.map((color, index) => <button aria-label={color} aria-pressed={selectedColor === index} key={color} onClick={() => setSelectedColor(index)} style={{ background: swatches[index] }} type="button" />)}</div></div>
      </section>

      <section className="car-showcase-story" id="exterior">
        <VehicleImage alt={`Ngoại thất ${vehicle.name}`} className="car-showcase-story-image" sizes="(max-width: 760px) 100vw, 52vw" src={resolveHero(vehicle, catalog)} />
        <div><span className="eyebrow">Ngoại thất</span><h2>Thiết kế tạo nên dấu ấn</h2><p>{editorial?.exterior || summary}</p></div>
      </section>

      <section className="car-showcase-story is-reversed" id="interior">
        <div><Armchair aria-hidden="true" /><span className="eyebrow">Nội thất</span><h2>Không gian dành cho trải nghiệm</h2><p>{editorial?.interior || "Khoang xe được bố trí trực quan, thuận tiện cho người lái và hành khách trên mọi hành trình."}</p></div>
        <VehicleImage alt={`Không gian ${vehicle.name}`} className="car-showcase-story-image" sizes="(max-width: 760px) 100vw, 52vw" src={catalog?.showcaseItems.find((item) => item.section === "interior")?.mediaUrl ?? resolveHero(vehicle, catalog)} />
      </section>

      <section className="car-showcase-performance" id="performance">
        <div>
          <span>Phiên bản {catalog?.variant || vehicle.name}</span>
          <h2>Sẵn sàng cho nhịp sống mỗi ngày</h2>
          {catalog ? (
            <div className="car-showcase-metrics">
              <div><Gauge /><strong>{metric(catalog.rangeKm, " km")}</strong><span>Quãng đường</span></div>
              <div><Zap /><strong>{metric(catalog.specs.motor_power_kw, " kW")}</strong><span>Công suất động cơ</span></div>
              <div><BatteryFull /><strong>{metric(catalog.batteryCapacityKwh, " kWh")}</strong><span>Dung lượng pin</span></div>
              <div><BatteryCharging /><strong>{metric(catalog.chargeMinutes, " phút")}</strong><span>Thời gian sạc</span></div>
              <div><UsersRound /><strong>{metric(catalog.seats, " chỗ")}</strong><span>Cấu hình ghế</span></div>
              <div><ShieldCheck /><strong>{metric(catalog.specs.torque_nm, " Nm")}</strong><span>Mô-men xoắn</span></div>
            </div>
          ) : <p>{editorial?.performance || "Khả năng vận hành được cân chỉnh cho nhu cầu di chuyển hằng ngày."}</p>}
        </div>
      </section>

      <section className="car-showcase-safety" id="safety"><ShieldCheck aria-hidden="true" /><div><span className="eyebrow">An toàn</span><h2>An tâm trên mỗi hành trình</h2><p>{editorial?.safety || "Các hệ thống hỗ trợ được thiết kế để người lái tự tin hơn trong phố và trên những hành trình dài."}</p></div></section>

      <section className="car-showcase-offers" id="offers">
        <Sparkles aria-hidden="true" size={30} />
        <div>
          <span className="eyebrow">Chính sách hiện hành</span>
          <h2>{promotionCount > 0 ? `${promotionCount} chương trình ưu đãi đang áp dụng` : "Khám phá chính sách dành cho bạn"}</h2>
          <p>Liên hệ tư vấn viên để nhận thông tin giá và chính sách phù hợp với phiên bản bạn quan tâm.</p>
        </div>
        <strong>{catalog?.priceVnd ? formatVnd(catalog.priceVnd) : "Liên hệ tư vấn"}</strong>
      </section>
    </div>
  );
}
