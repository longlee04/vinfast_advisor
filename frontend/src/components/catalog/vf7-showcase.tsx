"use client";

import { BatteryCharging, Gauge, LoaderCircle, ShieldCheck, Sparkles, Zap } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { VehicleImage } from "@/components/shared/vehicle-image";
import { fetchVehicle, type CatalogVehicle } from "@/lib/api/vehicles";
import { formatVnd } from "@/lib/format";
import type { VehicleMenuEntry } from "@/mocks/vehicle-menu";

const LINKS = [
  ["pricing", "Giá bán"], ["exterior", "Ngoại thất"], ["interior", "Nội thất"],
  ["performance", "Vận hành"], ["technology", "Tính năng"],
] as const;
const COLORS = [
  { key: "solar-ruby", label: "Solar Ruby", swatch: "#a80f26" },
  { key: "zenith-grey", label: "Zenith Grey", swatch: "#777b80" },
  { key: "urban-mint", label: "Urban Mint", swatch: "#8b927f" },
  { key: "infinity-blanc", label: "Infinity Blanc", swatch: "#f3f3ef" },
  { key: "jet-black", label: "Jet Black", swatch: "#111214" },
] as const;
const VARIANTS: ReadonlyArray<{
  name: string;
  note?: string;
  offer: number;
  list: number;
  range: number;
  power: number;
  torque: number;
  battery: number;
}> = [
  { name: "VF 7 Eco", offer: 703_000_000, list: 740_000_000, range: 440, power: 130, torque: 250, battery: 59.6 },
  { name: "VF 7 Plus", offer: 788_500_000, list: 830_000_000, range: 500.5, power: 150, torque: 310, battery: 70 },
  { name: "VF 7 Plus", note: "Trần kính toàn cảnh", offer: 807_500_000, list: 850_000_000, range: 500.5, power: 150, torque: 310, battery: 70 },
] as const;

function number(value: unknown, unit: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toLocaleString("vi-VN", { maximumFractionDigits: 2 })} ${unit}` : "—";
}

export function Vf7Showcase({ vehicle }: Readonly<{ vehicle: VehicleMenuEntry }>) {
  const [catalog, setCatalog] = useState<CatalogVehicle | null>(null);
  const [active, setActive] = useState("pricing");
  const [colorIndex, setColorIndex] = useState(0);
  const [selectedVariant, setSelectedVariant] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void fetchVehicle(vehicle.catalogSlug!)
      .then((value) => { if (!cancelled) setCatalog(value); })
      .catch(() => { if (!cancelled) setCatalog(null); });
    return () => { cancelled = true; };
  }, [vehicle.catalogSlug]);

  useEffect(() => {
    if (!("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target.id) setActive(visible.target.id);
    }, { rootMargin: "-22% 0px -62%", threshold: [0.1, 0.4] });
    LINKS.forEach(([id]) => { const element = document.getElementById(id); if (element) observer.observe(element); });
    return () => observer.disconnect();
  }, [catalog]);

  if (!catalog) {
    return <div className="vf7-loading" role="status"><LoaderCircle className="spin" /><strong>VF 7</strong></div>;
  }

  const selectedColor = COLORS[colorIndex];
  return (
    <div className="vf7-page">
      <section className="vf7-hero">
        <div className="vf7-hero-heading"><strong>VF7</strong><span>SÀNH ĐIỆU <em>ĐỘT PHÁ</em></span></div>
        <VehicleImage alt="VinFast VF 7 Solar Ruby" className="vf7-hero-image" preload sizes="100vw" src="/vehicles/vf7/hero.webp" />
      </section>

      <nav aria-label="Điều hướng nội dung VF 7" className="vf7-product-nav">
        <a className="vf7-wordmark" href="#pricing">VF7</a>
        <div>{LINKS.map(([id, label]) => <a className={active === id ? "is-active" : ""} href={`#${id}`} key={id}>{label}</a>)}</div>
      </nav>

      <section className="vf7-pricing" id="pricing">
        <h2>Tùy chọn cho ngân sách của bạn.</h2>
        <div className="vf7-price-grid">
          {VARIANTS.map((variant, index) => (
            <article className={selectedVariant === index ? "is-selected" : ""} key={`${variant.name}-${variant.note ?? "standard"}`}>
              <button aria-pressed={selectedVariant === index} onClick={() => setSelectedVariant(index)} type="button">
                <span>{variant.name}</span>{variant.note ? <small>{variant.note}</small> : null}
                <p>Giá bán từ</p>
                <strong>{formatVnd(variant.offer)}</strong>
                <del>{formatVnd(index === 0 ? catalog.priceVnd ?? variant.list : variant.list)}</del>
              </button>
            </article>
          ))}
        </div>
        <Link className="primary-button" href="/consultation">Nhận tư vấn</Link>
      </section>

      <section className="vf7-manifesto">
        <h2>VF 7 là một bước tiến đột phá trong thiết kế xe ô tô của VinFast.</h2>
        <p>Triết lý “Vũ trụ phi đối xứng” tạo nên một chiếc SUV điện tự do, cá tính, mạnh mẽ và thể thao.</p>
      </section>

      <section className="vf7-exterior" id="exterior">
        <header><span>Ngoại thất</span><h2>Kế thừa và đổi mới từ hơn trăm năm lịch sử của ngành ô tô.</h2></header>
        <VehicleImage alt={`VF 7 màu ${selectedColor.label}`} className="vf7-color-image" sizes="100vw" src={`/vehicles/vf7/${selectedColor.key}.webp`} />
        <div className="vf7-color-picker">
          <strong>{selectedColor.label}</strong>
          <div>{COLORS.map((color, index) => <button aria-label={color.label} aria-pressed={index === colorIndex} key={color.key} onClick={() => setColorIndex(index)} style={{ background: color.swatch }} type="button" />)}</div>
        </div>
        <div className="vf7-editorial-pair">
          <VehicleImage alt="Thiết kế ngoại thất VF 7" className="vf7-editorial-image" sizes="(max-width: 760px) 100vw, 54vw" src="/vehicles/vf7/exterior.webp" />
          <div><span>Vũ trụ phi đối xứng</span><h3>Phóng khoáng trong từng đường nét</h3><p>Dáng coupe, tay nắm cửa ẩn và đường gân dập nổi tạo nên bề mặt liền mạch, tối ưu khí động học và giàu cảm giác chuyển động.</p></div>
        </div>
      </section>

      <section className="vf7-interior" id="interior">
        <header><span>Nội thất</span><h2>Thiết kế hướng tới người lái.</h2></header>
        <VehicleImage alt="Nội thất VF 7 hướng tới người lái" className="vf7-interior-image" sizes="100vw" src="/vehicles/vf7/interior.webp" />
        <div><h3>Kiến tạo không gian trải nghiệm phóng khoáng</h3><p>Màn hình trung tâm 12,9 inch, khoang lái bố trí trực quan và không gian rộng rãi đưa mọi tiện nghi vào đúng tầm tay.</p></div>
      </section>

      <section className="vf7-performance" id="performance">
        <div><span>Vận hành</span><h2>Cầm lái với đam mê.</h2><div className="vf7-metrics">
          <div><Gauge /><strong>{number(VARIANTS[selectedVariant].range, "km")}</strong><span>Quãng đường</span></div>
          <div><Zap /><strong>{number(VARIANTS[selectedVariant].power, "kW")}</strong><span>Công suất tối đa</span></div>
          <div><Sparkles /><strong>{number(VARIANTS[selectedVariant].torque, "Nm")}</strong><span>Mô-men xoắn</span></div>
          <div><BatteryCharging /><strong>{number(VARIANTS[selectedVariant].battery, "kWh")}</strong><span>Dung lượng pin khả dụng</span></div>
        </div></div>
        <VehicleImage alt="VF 7 vận hành mạnh mẽ" className="vf7-performance-image" sizes="(max-width: 760px) 100vw, 50vw" src="/vehicles/vf7/performance.webp" />
      </section>

      <section className="vf7-technology" id="technology">
        <VehicleImage alt="Công nghệ hỗ trợ lái VF 7" className="vf7-technology-image" sizes="100vw" src="/vehicles/vf7/technology.webp" />
        <div><ShieldCheck /><span>Tính năng</span><h2>Đồng hành tự tin trên mọi hành trình.</h2><p>Hệ thống hỗ trợ lái và các tính năng an toàn chủ động giúp hành trình nhẹ nhàng, trực quan và an tâm hơn.</p><Link className="primary-button" href="/test-drive">Đăng ký lái thử</Link></div>
      </section>
    </div>
  );
}
