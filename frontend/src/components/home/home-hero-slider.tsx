"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import styles from "@/components/home/home-hero-slider.module.css";

const AUTOPLAY_MS = 6_000;
const SWIPE_THRESHOLD_PX = 48;

const slides = [
  {
    image: "/media/vinfast/home/campaign-income.webp",
    title: "Thu nhập hiệu quả dù ngày hay đêm",
    href: "/test-drive",
  },
  {
    image: "/media/vinfast/home/campaign-member.jpg",
    title: "Vingroup tri ân khách hàng nhân dịp sinh nhật 33 năm",
    href: "/vehicles",
  },
  {
    image: "/media/vinfast/home/campaign-vf2.jpg",
    title: "VF 2 - khởi đầu thông minh cho gia đình trẻ",
    href: "/vehicles/vf-2",
  },
  {
    image: "/media/vinfast/home/campaign-trade-in.jpg",
    title: "Lên đời xe điện - nhận voucher đến 80 triệu đồng",
    href: "/vehicles",
  },
  {
    image: "/media/vinfast/home/campaign-motorbike.jpg",
    title: "VinFast tri ân khách hàng xe máy điện",
    href: "/motorbikes",
  },
  {
    image: "/media/vinfast/home/campaign-mpv7.jpg",
    title: "VinFast MPV 7 - ưu đãi tài chính",
    href: "/vehicles/vf-mpv-7",
  },
] as const;

export function HomeHeroSlider() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const pointerStart = useRef<{ x: number; y: number } | null>(null);

  const selectSlide = useCallback((index: number) => {
    setActiveIndex((index + slides.length) % slides.length);
  }, []);

  const moveSlide = useCallback((direction: -1 | 1) => {
    setActiveIndex((current) => (current + direction + slides.length) % slides.length);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updatePreference = () => setReducedMotion(media.matches);
    updatePreference();
    media.addEventListener?.("change", updatePreference);
    return () => media.removeEventListener?.("change", updatePreference);
  }, []);

  useEffect(() => {
    if (paused || reducedMotion) return;
    const timer = window.setInterval(() => moveSlide(1), AUTOPLAY_MS);
    return () => window.clearInterval(timer);
  }, [moveSlide, paused, reducedMotion]);

  const activeSlide = slides[activeIndex];

  return (
    <section
      aria-label="Nội dung nổi bật"
      aria-roledescription="carousel"
      className={styles.slider}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setPaused(false);
      }}
      onFocusCapture={() => setPaused(true)}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onPointerDown={(event) => {
        pointerStart.current = { x: event.clientX, y: event.clientY };
      }}
      onPointerUp={(event) => {
        const start = pointerStart.current;
        pointerStart.current = null;
        if (!start) return;

        const deltaX = event.clientX - start.x;
        const deltaY = event.clientY - start.y;
        if (Math.abs(deltaX) >= SWIPE_THRESHOLD_PX && Math.abs(deltaX) > Math.abs(deltaY)) {
          moveSlide(deltaX < 0 ? 1 : -1);
        }
      }}
    >
      <div className={styles.slides}>
        {slides.map((slide, index) => (
          <div
            aria-hidden={activeIndex !== index}
            className={`${styles.slide} ${activeIndex === index ? styles.slideActive : ""}`}
            key={slide.image}
          >
            <Image
              alt={activeIndex === index ? slide.title : ""}
              fill
              priority={index === 0}
              sizes="100vw"
              src={slide.image}
            />
          </div>
        ))}
      </div>

      <h1 className="sr-only" key={activeSlide.title}>{activeSlide.title}</h1>
      <Link aria-label={activeSlide.title} className={styles.campaignLink} href={activeSlide.href} />

      <button aria-label="Slide trước" className={`${styles.arrow} ${styles.previous}`} onClick={() => moveSlide(-1)} type="button">
        <ChevronLeft aria-hidden="true" />
      </button>
      <button aria-label="Slide tiếp theo" className={`${styles.arrow} ${styles.next}`} onClick={() => moveSlide(1)} type="button">
        <ChevronRight aria-hidden="true" />
      </button>

      <div aria-label="Chọn nội dung nổi bật" className={styles.dots}>
        {slides.map((slide, index) => (
          <button
            aria-label={`Xem slide ${index + 1}: ${slide.title}`}
            aria-pressed={activeIndex === index}
            key={slide.image}
            onClick={() => selectSlide(index)}
            type="button"
          />
        ))}
      </div>
    </section>
  );
}
