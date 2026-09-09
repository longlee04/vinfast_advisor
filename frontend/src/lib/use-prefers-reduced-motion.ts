"use client";

import { useEffect, useState } from "react";

/**
 * Đổi ngay khi hệ điều hành đổi cờ `prefers-reduced-motion`, không chỉ đọc một
 * lần lúc mount — khách có thể bật/tắt cờ này trong lúc màn đang mở.
 *
 * Cùng khuôn với `HomeHeroSlider` (`components/home/home-hero-slider.tsx`),
 * tách ra dùng chung cho mọi chỗ cần tắt hiệu ứng theo cờ hệ thống.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return undefined;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    update();
    media.addEventListener?.("change", update);
    return () => media.removeEventListener?.("change", update);
  }, []);

  return reduced;
}
