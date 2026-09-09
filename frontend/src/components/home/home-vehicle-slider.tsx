"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import styles from "@/components/home/home-experience.module.css";
import type { HomepageVehicle } from "@/data/homepage";

type HomeVehicleSliderProps = Readonly<{
  ariaLabel: string;
  dotLabel: string;
  initialIndex: number;
  items: readonly HomepageVehicle[];
  variant: "car" | "motorbike";
}>;

const AUTOPLAY_MS = 7_000;

export function HomeVehicleSlider({ ariaLabel, dotLabel, initialIndex, items, variant }: HomeVehicleSliderProps) {
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);

  const move = useCallback((direction: -1 | 1) => {
    setActiveIndex((current) => (current + direction + items.length) % items.length);
  }, [items.length]);

  useEffect(() => {
    if (paused) return;
    const timer = window.setInterval(() => move(1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [move, paused]);

  const active = items[activeIndex];

  return (
    <section
      aria-label={ariaLabel}
      aria-roledescription="carousel"
      className={`${styles.vehicleSection} ${variant === "car" ? styles.carSection : styles.motorbikeSection}`}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPaused(false);
      }}
      onFocusCapture={() => setPaused(true)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <h2 className="sr-only">{ariaLabel}</h2>
      <div className={styles.vehicleVisual} key={active.name}>
        <Image alt={active.name} fill sizes="(max-width: 760px) 100vw, 1000px" src={active.image} />
      </div>

      <button aria-label={`${ariaLabel}: mẫu trước`} className={`${styles.vehicleArrow} ${styles.vehicleArrowPrevious}`} onClick={() => move(-1)} type="button">
        <ChevronLeft aria-hidden="true" />
      </button>
      <button aria-label={`${ariaLabel}: mẫu tiếp theo`} className={`${styles.vehicleArrow} ${styles.vehicleArrowNext}`} onClick={() => move(1)} type="button">
        <ChevronRight aria-hidden="true" />
      </button>

      <dl className={styles.vehicleMetrics}>
        {active.metrics.map((metric, index) => (
          <div key={metric.label}>
            <dt>{metric.label}</dt>
            <dd>{metric.value}</dd>
            {index === active.metrics.length - 1 && active.originalPrice ? <del>{active.originalPrice}</del> : null}
          </div>
        ))}
      </dl>

      <div className={styles.vehicleActions}>
        <Link className={styles.primaryButton} href={active.href}>{active.primaryLabel}</Link>
        <Link className={styles.secondaryButton} href={active.href}>XEM CHI TIẾT</Link>
      </div>

      <div aria-label={`Chọn ${dotLabel}`} className={styles.vehicleDots}>
        {items.map((item, index) => (
          <button
            aria-label={`Xem ${dotLabel} ${index + 1}: ${item.name}`}
            aria-pressed={activeIndex === index}
            key={item.name}
            onClick={() => setActiveIndex(index)}
            type="button"
          />
        ))}
      </div>

      {variant === "car" ? (
        <p className={styles.vehicleDisclaimer}>(*) Mức giá ưu đãi mang tính chất tham khảo. Chương trình áp dụng theo điều khoản &amp; điều kiện.</p>
      ) : null}
    </section>
  );
}
