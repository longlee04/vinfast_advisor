"use client";

import { useEffect, useRef, useState } from "react";

type ScrollRevealProps = Readonly<{
  children: React.ReactNode;
  className?: string;
  delayMs?: number;
  desktopOnly?: boolean;
  direction?: "left" | "right" | "up";
  durationMs?: number;
  mirror?: boolean;
}>;

export function ScrollReveal({
  children,
  className = "",
  delayMs = 0,
  desktopOnly = false,
  direction = "up",
  durationMs = 620,
  mirror = false,
}: ScrollRevealProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const element = ref.current;
    const canMatchMedia = typeof window.matchMedia === "function";
    const animationDisabled = (canMatchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches)
      || (desktopOnly && canMatchMedia && window.matchMedia("(max-width: 1199px)").matches);
    if (!element || animationDisabled || !("IntersectionObserver" in window)) {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      setVisible(entry.isIntersecting);
      if (entry.isIntersecting && !mirror) {
        observer.disconnect();
      }
    }, mirror
      ? { rootMargin: "0px", threshold: 0 }
      : { rootMargin: "0px 0px -8%", threshold: 0.12 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [desktopOnly, mirror]);

  return (
    <div
      className={`vf-reveal from-${direction} ${visible ? "is-visible" : ""} ${className}`}
      ref={ref}
      style={{
        "--vf-reveal-delay": `${delayMs}ms`,
        "--vf-reveal-duration": `${durationMs}ms`,
      } as React.CSSProperties}
    >
      {children}
    </div>
  );
}
