"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRef, useState } from "react";

import { OpenAgentDockButton } from "@/components/customer/open-agent-dock-button";
import { ScrollReveal } from "@/components/shared/scroll-reveal";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";
import { getProductExperience, type ProductMedia } from "@/data/product-experience";
import { formatVnd } from "@/lib/format";

import { VeroXExperience } from "./vero-x-experience";
import { EvoGrandExperience } from "./evo-grand-experience";

type ProductIdentity = {
  id: string;
  name: string;
  href: string;
  imageUrl: string;
  catalogSlug?: string;
};

function ProductImage({ media, className, priority = false }: Readonly<{ media: ProductMedia; className?: string; priority?: boolean }>) {
  return <div className={className}><Image alt={media.alt} fill priority={priority} sizes="100vw" src={media.src} /></div>;
}

function mediaLabel(media: ProductMedia): string {
  const labels: Partial<Record<ProductMedia["role"], string>> = {
    interior: "Nội thất",
    technology: "Công nghệ",
    battery: "Pin & vận hành",
    safety: "An toàn",
    detail: "Chi tiết",
  };
  return labels[media.role] ?? "Ngoại thất";
}

function mediaTitle(media: ProductMedia): string {
  if (media.title) return media.title;
  const titles: Partial<Record<ProductMedia["role"], string>> = {
    interior: "Không gian được mở ra từ bên trong.",
    technology: "Công nghệ hiện diện đúng lúc.",
    battery: "Năng lượng cho nhịp sống mỗi ngày.",
    safety: "Vững vàng trong từng chuyển động.",
    detail: "Tiện ích nằm trong từng chi tiết.",
  };
  return titles[media.role] ?? "Dáng vẻ tạo nên dấu ấn.";
}

function ColorControls({ activeIndex, colors, onMove, onSelect }: Readonly<{
  activeIndex: number;
  colors: ProductMedia[];
  onMove: (direction: -1 | 1) => void;
  onSelect: (index: number) => void;
}>) {
  return (
    <div className="vf-color-controls">
      <button aria-label="Màu trước" className="vf-color-arrow" onClick={() => onMove(-1)} type="button"><ChevronLeft /></button>
      <div className="vf-color-swatches" aria-label="Chọn màu xe">
        {colors.map((color, index) => (
          <button aria-label={color.label} aria-pressed={activeIndex === index} key={color.src} onClick={() => onSelect(index)} style={{ backgroundColor: color.swatch }} type="button" />
        ))}
      </div>
      <button aria-label="Màu tiếp theo" className="vf-color-arrow" onClick={() => onMove(1)} type="button"><ChevronRight /></button>
    </div>
  );
}

export function ProductExperience({ category, categoryLabel, vehicle }: Readonly<{
  category: "car" | "motorcycle";
  categoryLabel: string;
  vehicle: ProductIdentity;
}>) {
  const authored = getProductExperience(vehicle.id);
  const experience = authored ?? {
    slug: vehicle.id,
    model: vehicle.name,
    category,
    tagline: category === "car" ? "Khám phá theo cách của bạn." : "Linh hoạt trong từng hành trình.",
    statement: "Thông tin sản phẩm được trình bày cô đọng với hình ảnh chính thức.",
    hero: { src: vehicle.imageUrl, alt: `VinFast ${vehicle.name}`, role: "hero" as const },
    gallery: [],
    priceVnd: null,
    metrics: [],
    specificationGroups: [],
  };
  const colors = experience.gallery.filter((media) => media.role === "color");
  const stories = experience.gallery.filter((media) => media.role !== "color");
  const [activeColor, setActiveColor] = useState(0);
  const colorPointerStart = useRef<{ x: number; y: number } | null>(null);
  const activeColorMedia = colors[activeColor] ?? experience.hero;
  const leadStories = category === "car" ? stories.slice(0, 2) : stories.slice(0, 1);
  const galleryStories = stories.slice(leadStories.length);
  const isCampaignMotorcycle = category === "motorcycle" && experience.motorcycleLayout === "campaign";
  const navItems = [
    ["overview", "Tổng quan"],
    ...(colors.length && category === "car" ? [["colors", "Màu sắc"]] : []),
    ...(stories.length ? [["design", category === "car" ? "Thiết kế" : "Tiện ích"]] : []),
    ["specifications", "Thông số"],
  ];

  function selectColor(index: number): void {
    if (!colors.length) return;
    setActiveColor((index + colors.length) % colors.length);
  }

  function finishColorSwipe(clientX: number, clientY: number): void {
    const start = colorPointerStart.current;
    colorPointerStart.current = null;
    if (!start) return;
    const deltaX = clientX - start.x;
    const deltaY = clientY - start.y;
    if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY)) selectColor(activeColor + (deltaX < 0 ? 1 : -1));
  }

  const chatPrompt = `Tư vấn giúp tôi về ${experience.model}`;

  if (experience.motorcycleLayout === "vero") {
    return <VeroXExperience experience={experience} from={vehicle.href} />;
  }

  if (experience.motorcycleLayout === "evo-grand") {
    return <EvoGrandExperience experience={experience} from={vehicle.href} />;
  }

  return (
    <article className={`vf-product-page is-${category}`}>
      {category === "car" ? <nav className="vf-product-nav" aria-label={`Điều hướng ${vehicle.name}`}>
        <strong>{vehicle.name}</strong>
        <div>{navItems.map(([id, label]) => <a href={`#${id}`} key={id}>{label}</a>)}</div>
      </nav> : null}

      {isCampaignMotorcycle ? (
        <>
          <section className="vf-motorcycle-campaign-hero" id="overview">
            <h1 className="sr-only">{experience.model}</h1>
            <ProductImage className="vf-motorcycle-campaign-media" media={experience.hero} priority />
          </section>
          <ScrollReveal><section className="vf-motorcycle-color-showcase" id="colors">
            <header>
              <h2>Đa dạng tùy chọn màu sắc</h2>
              <p>Giá từ <strong>{experience.priceVnd ? formatVnd(experience.priceVnd) : "Đang cập nhật"}</strong></p>
            </header>
            <div className="vf-motorcycle-color-stage" onPointerDown={(event) => { colorPointerStart.current = { x: event.clientX, y: event.clientY }; }} onPointerUp={(event) => finishColorSwipe(event.clientX, event.clientY)}>
              <ProductImage className="vf-motorcycle-color-media" key={activeColorMedia.src} media={activeColorMedia} />
            </div>
            <div className="vf-motorcycle-color-toolbar">
              <p aria-live="polite">{activeColorMedia.label}</p>
              <ColorControls activeIndex={activeColor} colors={colors} onMove={(direction) => selectColor(activeColor + direction)} onSelect={selectColor} />
              <Link href="/test-drive">Đăng ký lái thử</Link>
            </div>
          </section></ScrollReveal>
          <ScrollReveal><section className="vf-motorcycle-capacity">
            <div className="vf-motorcycle-capacity-visual" aria-hidden="true">
              <div className="vf-motorcycle-capacity-image"><ProductImage key={activeColorMedia.src} media={activeColorMedia} /></div>
              <strong>35L</strong>
            </div>
            <div><span>Tiện ích rộng mở</span><h2>Thể tích cốp 35 lít tối ưu sức chứa – tối đa nhu cầu.</h2><p>{experience.statement}</p></div>
          </section></ScrollReveal>
        </>
      ) : category === "motorcycle" ? (
        <section className="vf-motorcycle-configurator" id="overview">
          <h1 className="vf-configurator-wordmark"><span aria-hidden="true">VINFAST</span><span>{experience.model}</span></h1>
          <div className="vf-configurator-intro"><span>{experience.heroEyebrow ?? categoryLabel}</span></div>
          {experience.metrics.length ? <div className="vf-configurator-metrics" aria-label="Thông tin nổi bật">{experience.metrics.slice(0, 3).map((metric) => <div key={metric.label}><strong>{metric.value}</strong><span>{metric.label}</span></div>)}</div> : null}
          <div className="vf-configurator-vehicle" onPointerDown={(event) => { colorPointerStart.current = { x: event.clientX, y: event.clientY }; }} onPointerUp={(event) => finishColorSwipe(event.clientX, event.clientY)}>
            <ProductImage className="vf-configurator-media" key={activeColorMedia.src} media={activeColorMedia} priority />
          </div>
          <div className="vf-configurator-actions">
            <span>Giá niêm yết</span>
            <strong>{experience.priceVnd ? formatVnd(experience.priceVnd) : "Đang cập nhật"}</strong>
            {experience.priceNote ? <small>{experience.priceNote}</small> : null}
            {colors.length ? <><p aria-live="polite">{activeColorMedia.label}</p><ColorControls activeIndex={activeColor} colors={colors} onMove={(direction) => selectColor(activeColor + direction)} onSelect={selectColor} /></> : null}
          </div>
        </section>
      ) : (
        <section className={`vf-product-hero ${stories.length ? "has-editorial-media" : "is-cutout"}`} id="overview">
          <ProductImage className="vf-product-hero-media" media={experience.hero} priority />
          <div className="vf-product-hero-shade" />
          <div className="vf-product-hero-copy"><span>{categoryLabel}</span><h1>{experience.model}</h1><p>{experience.tagline}</p><div><Link href="/test-drive">Đặt lịch lái thử</Link><OpenAgentDockButton prompt={chatPrompt}>Tư vấn</OpenAgentDockButton></div></div>
          {experience.metrics.length ? <div className="vf-product-hero-metrics" aria-label="Thông tin nổi bật">{experience.metrics.map((metric) => <div key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>)}</div> : null}
        </section>
      )}

      {!isCampaignMotorcycle ? <ScrollReveal><section className={`vf-product-statement is-${category}`}><span>{category === "car" ? "Thuần điện VinFast" : "Khác biệt trong từng chuyển động"}</span><h2>{experience.statement}</h2></section></ScrollReveal> : null}

      {colors.length && category === "car" ? (
        <ScrollReveal><section className="vf-color-gallery" id="colors">
          <header className="vf-color-heading"><span>Ngoại thất</span><h2>Một sắc màu cho dấu ấn riêng.</h2></header>
          <div className="vf-color-stage" onPointerDown={(event) => { colorPointerStart.current = { x: event.clientX, y: event.clientY }; }} onPointerUp={(event) => finishColorSwipe(event.clientX, event.clientY)}><ProductImage className="vf-color-media" key={activeColorMedia.src} media={activeColorMedia} /></div>
          <div className="vf-color-toolbar"><p aria-live="polite">{activeColorMedia.label}</p><ColorControls activeIndex={activeColor} colors={colors} onMove={(direction) => selectColor(activeColor + direction)} onSelect={selectColor} /></div>
        </section></ScrollReveal>
      ) : null}

      {stories.length ? <section className={`vf-product-stories ${experience.storyLayout === "details-first" ? "is-details-first" : ""}`} id="design">
        {leadStories.map((media, index) => <ScrollReveal key={media.src}><article className={`vf-product-story is-${media.role} ${media.role === "interior" ? "is-cinematic" : ""} ${index % 2 ? "is-reversed" : ""}`}><ProductImage className="vf-product-story-media" media={media} /><div><span>{mediaLabel(media)}</span><h2>{mediaTitle(media)}</h2><p>{media.description ?? "Khung hình tập trung đúng vào chi tiết và tỷ lệ nguyên bản của sản phẩm."}</p></div></article></ScrollReveal>)}
        {galleryStories.length ? <ScrollReveal><div className="vf-product-detail-gallery"><header><span>Khám phá chi tiết</span><h2>Nổi bật chinh phục mọi hành trình.</h2></header><div>{galleryStories.map((media) => <figure key={media.src}><ProductImage className="vf-product-detail-media" media={media} /><figcaption><span>{mediaLabel(media)}</span><p>{mediaTitle(media)}</p></figcaption></figure>)}</div></div></ScrollReveal> : null}
      </section> : null}

      <ScrollReveal><section className="vf-specifications" id="specifications">
        <div className="vf-spec-heading"><span>Thông số sản phẩm</span><h2>Thông số, trình bày rõ ràng.</h2><p>Dữ liệu hiển thị trực tiếp từ cấu hình local của từng mẫu xe.</p></div>
        {experience.specificationGroups.length ? category === "motorcycle" ? (
          <dl className="vf-spec-matrix">{experience.specificationGroups.flatMap((group) => group.items).map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
        ) : (
          <div className="vf-spec-groups">{experience.specificationGroups.map((group, index) => <details key={group.title} open={index === 0}><summary>{group.title}<span>+</span></summary><dl>{group.items.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl></details>)}</div>
        ) : null}
      </section></ScrollReveal>

      <VehicleSupportChoice anchorId="consultation" from={vehicle.href} model={experience.model} />
    </article>
  );
}
