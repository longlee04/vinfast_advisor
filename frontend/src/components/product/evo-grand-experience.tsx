"use client";

import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";

import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";
import type { ProductExperienceData, ProductMedia } from "@/data/product-experience";

import styles from "./evo-grand-experience.module.css";

const EVO_MEDIA_ROOT = "/media/vinfast/motorbikes/evo-grand";
const TECHNICAL_SPECIFICATION_URL =
  "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwc7800e97/Document/Vinfast_EvoGrand_TSKT_FA_2025-07.pdf";

const FEATURE_SLIDES = [
  {
    description: "Thể tích cốp 35L tối ưu sức chứa – tối đa nhu cầu.",
    image: `${EVO_MEDIA_ROOT}/feature-storage.webp`,
  },
  {
    description: "Linh hoạt nâng cấp 02 pin kép, gấp đôi năng lượng, nâng tầm hiệu suất.",
    image: `${EVO_MEDIA_ROOT}/feature-dual-battery.webp`,
  },
  {
    description: "Trải nghiệm hành trình di chuyển lên tới 262km trong một lần sạc*.",
    image: `${EVO_MEDIA_ROOT}/feature-range.webp`,
  },
  {
    description: "Sử dụng Pin LFP với các ưu điểm vượt trội.",
    image: `${EVO_MEDIA_ROOT}/feature-lfp-led.webp`,
  },
  {
    description:
      "Hệ thống đèn chiếu sáng và đèn tín hiệu Full LED cho khả năng chiếu sáng mạnh mẽ, tăng khả năng quan sát.",
    image: `${EVO_MEDIA_ROOT}/feature-lfp-led.webp`,
  },
] as const;

function ArtDirectedImage({
  alt,
  className,
  desktopSrc,
  mobileSrc,
  priority = false,
}: Readonly<{
  alt: string;
  className: string;
  desktopSrc: string;
  mobileSrc: string;
  priority?: boolean;
}>) {
  return (
    <div className={className}>
      <Image alt={alt} className={styles.desktopImage} fill priority={priority} sizes="100vw" src={desktopSrc} />
      <Image alt="" aria-hidden className={styles.mobileImage} fill priority={priority} sizes="100vw" src={mobileSrc} />
    </div>
  );
}

function Price({ value }: Readonly<{ value: number | null }>) {
  if (value === null) return null;
  return <strong>{new Intl.NumberFormat("vi-VN").format(value)} VNĐ</strong>;
}

function ColorCarousel({
  colors,
  model,
}: Readonly<{
  colors: ProductMedia[];
  model: string;
}>) {
  const [activeColor, setActiveColor] = useState(0);
  const pointerStart = useRef<number | null>(null);
  const activeMedia = colors[activeColor];
  const trackStyle = {
    "--desktop-color-offset": `${activeColor * -66.666}%`,
    "--mobile-color-offset": `${activeColor * -100}%`,
  } as CSSProperties;

  const selectPrevious = () => setActiveColor((current) => (current - 1 + colors.length) % colors.length);
  const selectNext = () => setActiveColor((current) => (current + 1) % colors.length);

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointerStart.current = event.clientX;
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (pointerStart.current === null) return;
    const distance = event.clientX - pointerStart.current;
    pointerStart.current = null;
    if (Math.abs(distance) < 45) return;
    if (distance > 0) selectPrevious();
    else selectNext();
  };

  if (!activeMedia) return null;

  return (
    <div className={styles.colorStage}>
      <div
        className={styles.colorViewport}
        onPointerCancel={() => { pointerStart.current = null; }}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
      >
        <div className={styles.colorTrack} data-testid="evo-grand-color-track" style={trackStyle}>
          {colors.map((color) => (
            <figure className={styles.colorSlide} key={color.src}>
              <Image
                alt={color.alt}
                fill
                sizes="(max-width: 767px) 100vw, 66vw"
                src={color.src}
              />
            </figure>
          ))}
        </div>
      </div>

      <div className={styles.colorNavigation}>
        <button aria-label="Màu xe trước" onClick={selectPrevious} type="button">
          <ChevronLeft aria-hidden="true" />
        </button>
        <button aria-label="Màu xe tiếp theo" onClick={selectNext} type="button">
          <ChevronRight aria-hidden="true" />
        </button>
      </div>

      <div className={styles.colorControls}>
        <span className={styles.activeColorName}>{activeMedia.alt.split(" màu ").at(-1)}</span>
        <div aria-label={`Màu xe ${model}`} className={styles.swatches} role="group">
          {colors.map((color, index) => {
            const label = color.alt.split(" màu ").at(-1) ?? color.alt;
            return (
              <button
                aria-label={label}
                aria-pressed={index === activeColor}
                className={styles.swatch}
                key={color.src}
                onClick={() => setActiveColor(index)}
                style={{ "--swatch": color.swatch ?? "#dadada" } as CSSProperties}
                type="button"
              />
            );
          })}
        </div>
        <Link className={styles.buyButton} href="/test-drive">Mua Evo Grand</Link>
      </div>
    </div>
  );
}

function FeatureCarousel() {
  const [activeFeature, setActiveFeature] = useState(0);
  const [previousFeature, setPreviousFeature] = useState<number | null>(null);
  const [direction, setDirection] = useState<"next" | "previous">("next");
  const [autoplay, setAutoplay] = useState(true);

  const changeFeature = (nextIndex: number, nextDirection: "next" | "previous", manual = true) => {
    setPreviousFeature(activeFeature);
    setDirection(nextDirection);
    setActiveFeature((nextIndex + FEATURE_SLIDES.length) % FEATURE_SLIDES.length);
    if (manual) setAutoplay(false);
  };

  useEffect(() => {
    if (previousFeature === null) return undefined;
    const timeout = window.setTimeout(() => setPreviousFeature(null), 660);
    return () => window.clearTimeout(timeout);
  }, [previousFeature]);

  useEffect(() => {
    const prefersReducedMotion = typeof window.matchMedia === "function"
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!autoplay || prefersReducedMotion) return undefined;
    const interval = window.setInterval(() => {
      setActiveFeature((current) => {
        setPreviousFeature(current);
        setDirection("next");
        return (current + 1) % FEATURE_SLIDES.length;
      });
    }, 3000);
    return () => window.clearInterval(interval);
  }, [autoplay]);

  const activeSlide = FEATURE_SLIDES[activeFeature];
  const previousSlide = previousFeature === null ? null : FEATURE_SLIDES[previousFeature];

  return (
    <section className={styles.features} data-effect="cube" data-testid="evo-grand-feature-stage" id="features">
      <div className={styles.featureVisual}>
        <div className={styles.cubeViewport}>
          {previousSlide ? (
            <div className={`${styles.cubeFace} ${direction === "next" ? styles.cubeOutNext : styles.cubeOutPrevious}`}>
              <Image alt="" aria-hidden fill sizes="(max-width: 900px) 92vw, 38vw" src={previousSlide.image} />
            </div>
          ) : null}
          <div
            className={`${styles.cubeFace} ${previousSlide ? direction === "next" ? styles.cubeInNext : styles.cubeInPrevious : ""}`}
            key={`${activeFeature}-${activeSlide.image}`}
          >
            <Image alt={`Minh họa tính năng Evo Grand: ${activeSlide.description}`} fill sizes="(max-width: 900px) 92vw, 38vw" src={activeSlide.image} />
          </div>
        </div>
      </div>

      <div className={styles.featureCopy}>
        <div aria-live="polite" className={styles.featureDescription} key={activeFeature}>
          <p>{activeSlide.description}</p>
        </div>
        <div className={styles.featureActions}>
          <a className={styles.specificationButton} href={TECHNICAL_SPECIFICATION_URL} rel="noreferrer" target="_blank">
            Xem thông số
          </a>
          <div className={styles.featureNavigation}>
            <button
              aria-label="Tính năng tiếp theo"
              onClick={() => changeFeature(activeFeature + 1, "next")}
              type="button"
            >
              <ChevronDown aria-hidden="true" />
            </button>
            <button
              aria-label="Tính năng trước"
              onClick={() => changeFeature(activeFeature - 1, "previous")}
              type="button"
            >
              <ChevronUp aria-hidden="true" />
            </button>
          </div>
        </div>
        <span className={styles.featureCounter}>0{activeFeature + 1} / 0{FEATURE_SLIDES.length}</span>
      </div>

      <div aria-hidden className={styles.featuresAccent}>
        <Image alt="" fill sizes="26vw" src={`${EVO_MEDIA_ROOT}/features-accent.webp`} />
      </div>
    </section>
  );
}

export function EvoGrandExperience({
  experience,
  from,
}: Readonly<{
  experience: ProductExperienceData;
  from: string;
}>) {
  const colors = experience.gallery.filter((media) => media.role === "color");

  return (
    <article className={styles.page}>
      <h1 className="sr-only">{experience.model}</h1>
      <section className={styles.hero} id="overview">
        <ArtDirectedImage
          alt={experience.hero.alt}
          className={styles.heroMedia}
          desktopSrc={experience.hero.src}
          mobileSrc={`${EVO_MEDIA_ROOT}/campaign-hero-mobile.webp`}
          priority
        />
      </section>

      <section aria-label="Thông tin nổi bật Evo Grand" className={styles.overview}>
        <ArtDirectedImage
          alt="Evo Grand trên phố cùng khách hàng"
          className={styles.overviewMedia}
          desktopSrc={`${EVO_MEDIA_ROOT}/overview.webp`}
          mobileSrc={`${EVO_MEDIA_ROOT}/overview-mobile.webp`}
        />
        <div className={styles.metrics}>
          {experience.metrics.map((metric) => (
            <div key={metric.label}>
              <strong>{metric.value}</strong>
              <span>{metric.label}</span>
            </div>
          ))}
          <small>*Theo điều kiện kiểm thử của VinFast khi di chuyển 1 người 65 kg với tốc độ 30 km/h</small>
        </div>
        <div aria-hidden className={styles.overviewAccent}>
          <Image alt="" fill sizes="28vw" src={`${EVO_MEDIA_ROOT}/overview-accent.webp`} />
        </div>
      </section>

      <section className={styles.colors} id="colors">
        <header className={styles.colorHeader}>
          <div>
            <span>Evo Grand</span>
            <h2>Đa dạng tùy chọn màu sắc</h2>
          </div>
          <div className={styles.price}>
            <Price value={experience.priceVnd} />
            {experience.priceNote ? <small>{experience.priceNote}</small> : null}
          </div>
        </header>
        <ColorCarousel colors={colors} model={experience.model} />
      </section>

      <section className={styles.cityBanner}>
        <Image
          alt="Evo Grand đồng hành cùng nhịp sống đô thị"
          fill
          sizes="100vw"
          src={`${EVO_MEDIA_ROOT}/city-banner.webp`}
        />
      </section>

      <FeatureCarousel />

      <section className={styles.closingBanner}>
        <ArtDirectedImage
          alt="Evo Grand chinh phục hành trình đô thị"
          className={styles.closingBannerMedia}
          desktopSrc={`${EVO_MEDIA_ROOT}/closing-banner.webp`}
          mobileSrc={`${EVO_MEDIA_ROOT}/closing-banner-mobile.webp`}
        />
      </section>

      <section className={styles.specifications} id="specifications">
        <header className={styles.specificationHeader}>
          <span>Evo Grand</span>
          <h2>Thông số kỹ thuật</h2>
        </header>
        <div className={styles.specificationGrid}>
          {experience.specificationGroups.map((group) => (
            <div className={styles.specificationGroup} key={group.title}>
              <h3>{group.title}</h3>
              <dl>
                {group.items.map((item) => (
                  <div key={item.key}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
        {experience.specificationNotes?.map((note) => <small className={styles.specificationNote} key={note}>{note}</small>)}
        <div className={styles.specificationActions}>
          {experience.brochureUrl ? (
            <a href={experience.brochureUrl} rel="noreferrer" target="_blank">Tải brochure</a>
          ) : null}
          <Link href="/test-drive">Mua Evo Grand</Link>
        </div>
      </section>

      <VehicleSupportChoice anchorId="consultation" from={from} model={experience.model} />
    </article>
  );
}
