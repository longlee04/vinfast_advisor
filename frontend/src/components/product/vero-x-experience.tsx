"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import { useRef, useState } from "react";

import { ScrollReveal } from "@/components/shared/scroll-reveal";
import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";
import type { ProductExperienceData, ProductMedia } from "@/data/product-experience";

const VERO_MEDIA_ROOT = "/media/vinfast/motorbikes/vero-x";

const SMART_FEATURES = [
  {
    title: "Smart Key",
    description: "Chìa khóa thông minh thay thế hoàn toàn ổ khóa cơ truyền thống, dễ dàng bật/tắt máy.",
    icon: `${VERO_MEDIA_ROOT}/icon-smart-key.png`,
    side: "left" as const,
  },
  {
    title: "Tìm xe trong bãi đỗ",
    description: "Xe sẽ phát ra âm thanh, giúp bạn dễ dàng tìm xe ở những bãi đỗ rộng và đông đúc.",
    icon: `${VERO_MEDIA_ROOT}/icon-find-bike.png`,
    side: "left" as const,
  },
  {
    title: "Thiết kế",
    description: "Thiết kế góc cạnh, độc bản – không hòa lẫn, khẳng định cá tính.",
    icon: `${VERO_MEDIA_ROOT}/icon-design.png`,
    side: "right" as const,
  },
  {
    title: "Chống nước",
    description: "Tiêu chuẩn chống nước IP67. Động cơ có khả năng chống nước vượt trội ở mức nước ngập sâu 0,5m trong thời gian 30 phút.",
    icon: `${VERO_MEDIA_ROOT}/icon-waterproof.png`,
    side: "right" as const,
  },
];

const DETAIL_FEATURES: ProductMedia[] = [
  {
    src: `${VERO_MEDIA_ROOT}/feature-display.webp`,
    alt: "Màn hình TFT hiện đại trên VinFast Vero X",
    role: "detail",
    description: "Màn hình TFT hiện đại, đem tới độ phân giải và tương phản cao, giúp hiển thị thông số rõ ràng, sống động.",
  },
  {
    src: `${VERO_MEDIA_ROOT}/feature-storage.webp`,
    alt: "Cốp 35L của VinFast Vero X",
    role: "detail",
    description: "Thể tích cốp 35L đáp ứng mọi nhu cầu cất giữ các vật dụng cần thiết.",
  },
  {
    src: `${VERO_MEDIA_ROOT}/feature-footboard.webp`,
    alt: "Sàn để chân rộng rãi của VinFast Vero X",
    role: "detail",
    description: "Sàn để chân rộng rãi và vị trí để chân sau tách rời, giúp tư thế ngồi thư thái và thoải mái.",
  },
  {
    src: `${VERO_MEDIA_ROOT}/feature-suspension.webp`,
    alt: "Hệ thống giảm xóc VinFast Vero X",
    role: "detail",
    description: "Hệ thống giảm xóc với giảm chấn thủy lực, hỗ trợ xe di chuyển êm ái trên nhiều địa hình.",
  },
  {
    src: `${VERO_MEDIA_ROOT}/feature-brakes.webp`,
    alt: "Hệ thống phanh đĩa VinFast Vero X",
    role: "detail",
    description: "Hệ thống phanh đĩa bánh trước và phanh tang trống phía sau, đảm bảo an toàn trong mọi hành trình.",
  },
];

function VeroImage({ className, media, priority = false }: Readonly<{
  className: string;
  media: ProductMedia;
  priority?: boolean;
}>) {
  return <div className={className}><Image alt={media.alt} fill priority={priority} sizes="100vw" src={media.src} /></div>;
}

function VeroColorControls({ activeIndex, colors, onMove, onSelect }: Readonly<{
  activeIndex: number;
  colors: ProductMedia[];
  onMove: (direction: -1 | 1) => void;
  onSelect: (index: number) => void;
}>) {
  return (
    <div className="vf-color-controls">
      <button aria-label="Màu trước" className="vf-color-arrow" onClick={() => onMove(-1)} type="button"><ChevronLeft /></button>
      <div aria-label="Chọn màu xe" className="vf-color-swatches">
        {colors.map((color, index) => (
          <button
            aria-label={color.label}
            aria-pressed={activeIndex === index}
            key={color.src}
            onClick={() => onSelect(index)}
            style={{ backgroundColor: color.swatch }}
            type="button"
          />
        ))}
      </div>
      <button aria-label="Màu tiếp theo" className="vf-color-arrow" onClick={() => onMove(1)} type="button"><ChevronRight /></button>
    </div>
  );
}

export function VeroXExperience({ experience, from }: Readonly<{
  experience: ProductExperienceData;
  from: string;
}>) {
  const colors = experience.gallery.filter((media) => media.role === "color");
  const [activeColor, setActiveColor] = useState(0);
  const colorPointerStart = useRef<{ x: number; y: number } | null>(null);
  const activeColorMedia = colors[activeColor] ?? experience.hero;
  const formattedPrice = experience.priceVnd
    ? `${new Intl.NumberFormat("vi-VN").format(experience.priceVnd)} VNĐ`
    : "Đang cập nhật";

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
    if (Math.abs(deltaX) > 45 && Math.abs(deltaX) > Math.abs(deltaY)) {
      selectColor(activeColor + (deltaX < 0 ? 1 : -1));
    }
  }

  return (
    <article className="vf-product-page is-motorcycle is-vero-x">
      <section className="vf-motorcycle-configurator vf-vero-hero" id="overview">
        <h1 className="vf-configurator-wordmark"><span aria-hidden="true">VINFAST</span><span>{experience.model}</span></h1>
        <div className="vf-configurator-intro"><span>{experience.heroEyebrow}</span></div>
        <div aria-label="Thông tin nổi bật" className="vf-configurator-metrics">
          {experience.metrics.map((metric) => <div key={metric.label}><strong>{metric.value}</strong><span>{metric.label}</span></div>)}
        </div>
        <div
          className="vf-configurator-vehicle"
          onPointerDown={(event) => { colorPointerStart.current = { x: event.clientX, y: event.clientY }; }}
          onPointerUp={(event) => finishColorSwipe(event.clientX, event.clientY)}
        >
          <VeroImage className="vf-configurator-media" key={activeColorMedia.src} media={activeColorMedia} priority />
        </div>
        <div className="vf-configurator-actions">
          <span>Giá niêm yết</span>
          <strong>{formattedPrice}</strong>
          {experience.priceNote ? <small>{experience.priceNote}</small> : null}
          <p aria-live="polite">{activeColorMedia.label}</p>
          <VeroColorControls activeIndex={activeColor} colors={colors} onMove={(direction) => selectColor(activeColor + direction)} onSelect={selectColor} />
        </div>
      </section>

      <section aria-label="Tiện ích thông minh Vero X" className="vf-vero-smart" id="features">
        <div className="vf-vero-smart-column">
          {SMART_FEATURES.filter((feature) => feature.side === "left").map((feature, index) => (
            <ScrollReveal delayMs={index * 200} desktopOnly direction="left" durationMs={300} key={feature.title} mirror>
              <article className="vf-vero-smart-item">
                <h2><Image alt="" aria-hidden height={24} src={feature.icon} width={24} />{feature.title}</h2>
                <p>{feature.description}</p>
              </article>
            </ScrollReveal>
          ))}
        </div>
        <VeroImage
          className="vf-vero-smart-media"
          media={{ src: `${VERO_MEDIA_ROOT}/smart-features.webp`, alt: "VinFast Vero X với thiết kế và tiện ích thông minh", role: "technology" }}
        />
        <div className="vf-vero-smart-column">
          {SMART_FEATURES.filter((feature) => feature.side === "right").map((feature, index) => (
            <ScrollReveal delayMs={index * 200} desktopOnly direction="right" durationMs={300} key={feature.title} mirror>
              <article className="vf-vero-smart-item">
                <h2><Image alt="" aria-hidden height={24} src={feature.icon} width={24} />{feature.title}</h2>
                <p>{feature.description}</p>
              </article>
            </ScrollReveal>
          ))}
        </div>
      </section>

      <section className="vf-vero-energy">
        <div className="vf-vero-energy-copy">
          <ScrollReveal desktopOnly direction="left" durationMs={300} mirror>
            <header><h2>Nạp năng lượng ấn tượng</h2><p>Thêm hành trình hứng khởi</p></header>
          </ScrollReveal>
          <ScrollReveal delayMs={150} desktopOnly direction="left" durationMs={300} mirror>
            <div><h3>Linh hoạt nâng cấp 02 pin</h3><p>Hệ thống 02 pin LFP tiên tiến với 01 pin cố định dưới sàn xe và 01 pin tháo rời đặt trong cốp.</p></div>
          </ScrollReveal>
          <ScrollReveal delayMs={300} desktopOnly direction="left" durationMs={300} mirror>
            <div><h3>Quãng đường di chuyển đầy ấn tượng</h3><p>Khẳng định ưu thế với quãng đường di chuyển đạt tới 262 km/lần sạc. Tốc độ tối đa 70 km/h, vận hành mạnh mẽ và tăng tốc từ 0 - 50 km/h chỉ trong 15 giây.</p></div>
          </ScrollReveal>
        </div>
        <ScrollReveal className="vf-vero-energy-media-reveal" desktopOnly direction="right" durationMs={300} mirror>
          <VeroImage
            className="vf-vero-energy-media"
            media={{ src: `${VERO_MEDIA_ROOT}/dual-battery.webp`, alt: "VinFast Vero X với hệ thống 02 pin linh hoạt", role: "battery" }}
          />
        </ScrollReveal>
      </section>

      <section aria-label="Chi tiết nổi bật Vero X" className="vf-vero-feature-grid">
        {DETAIL_FEATURES.map((feature, index) => (
          <ScrollReveal delayMs={index * 150} desktopOnly direction="right" durationMs={300} key={feature.src} mirror>
            <figure>
              <VeroImage className="vf-vero-feature-media" media={feature} />
              <figcaption>{feature.description}</figcaption>
            </figure>
          </ScrollReveal>
        ))}
      </section>

      <section className="vf-vero-battery">
        <div aria-hidden className="vf-vero-battery-wordmark">VERO X</div>
        <div className="vf-vero-battery-copy">
          <ScrollReveal desktopOnly direction="left" durationMs={300} mirror><h2>Công nghệ Pin tiên tiến</h2></ScrollReveal>
          <ScrollReveal delayMs={150} desktopOnly direction="left" durationMs={300} mirror>
            <div><h3>Công nghệ Pin LFP</h3><ul><li>Tăng công suất động cơ.</li><li>Giảm thiểu tiêu hao không cần thiết.</li><li>Ổn định &amp; an toàn hơn, chống cháy nổ trên mọi trường hợp.</li></ul></div>
          </ScrollReveal>
          <ScrollReveal delayMs={300} desktopOnly direction="left" durationMs={300} mirror>
            <div><h3>Thời gian vận hành</h3><ul><li>Thời gian sạc đầy: Khoảng 6h30 phút từ 0 - 100%.</li></ul></div>
          </ScrollReveal>
          <ScrollReveal delayMs={450} desktopOnly direction="left" durationMs={300} mirror>
            <div><h3>Cách bảo quản thông minh</h3><ul><li>Duy trì dung lượng trên 20% trong quá trình sử dụng.</li><li>Cắm sạc khi dung lượng pin thấp hơn 20%. Không nên sạc khi nhiệt độ pin cao hơn 45°C, hệ thống sẽ không nhận sạc khi pin nóng ở nhiệt độ 72°C.</li></ul></div>
          </ScrollReveal>
        </div>
        <ScrollReveal className="vf-vero-battery-media-reveal" desktopOnly direction="right" durationMs={300} mirror>
          <VeroImage
            className="vf-vero-battery-media"
            media={{ src: `${VERO_MEDIA_ROOT}/battery-technology.webp`, alt: "VinFast Vero X sử dụng công nghệ pin LFP tiên tiến", role: "battery" }}
          />
        </ScrollReveal>
      </section>

      <section className="vf-vero-secondary-configurator">
        <div className="vf-vero-secondary-copy">
          <h2>Vero X</h2>
          <div className="vf-vero-price-bar">Giá niêm yết: {formattedPrice}</div>
          <p>{experience.priceNote}</p>
        </div>
        <div
          className="vf-vero-secondary-stage"
          onPointerDown={(event) => { colorPointerStart.current = { x: event.clientX, y: event.clientY }; }}
          onPointerUp={(event) => finishColorSwipe(event.clientX, event.clientY)}
        >
          <VeroImage className="vf-vero-secondary-media" key={activeColorMedia.src} media={activeColorMedia} />
          <div className="vf-vero-secondary-arrows">
            <button aria-label="Màu trước ở phần thông số" onClick={() => selectColor(activeColor - 1)} type="button"><ChevronLeft /></button>
            <button aria-label="Màu tiếp theo ở phần thông số" onClick={() => selectColor(activeColor + 1)} type="button"><ChevronRight /></button>
          </div>
        </div>
      </section>

      <section className="vf-vero-specifications" id="specifications">
        <header><h2>Thông số sản phẩm</h2>{experience.brochureUrl ? <a href={experience.brochureUrl} rel="noreferrer" target="_blank">Tải Brochure</a> : null}</header>
        <div className="vf-vero-spec-columns">
          {experience.specificationGroups.map((group) => (
            <section key={group.title}>
              <h3 className="sr-only">{group.title}</h3>
              <dl>{group.items.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
            </section>
          ))}
        </div>
        {experience.specificationNotes?.length ? <div className="vf-vero-spec-notes"><strong>(*)Lưu ý:</strong><ul>{experience.specificationNotes.map((note) => <li key={note}>{note}</li>)}</ul></div> : null}
      </section>

      <VehicleSupportChoice anchorId="consultation" from={from} model={experience.model} />
    </article>
  );
}
