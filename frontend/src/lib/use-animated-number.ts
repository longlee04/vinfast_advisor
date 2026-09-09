"use client";

import { useEffect, useRef, useState } from "react";

const DEFAULT_DURATION_MS = 250;

/**
 * Số hiện trên màn hình "đếm" mượt từ giá trị cũ tới `target` bằng
 * `requestAnimationFrame`, KHÔNG dùng khi `disabled` (đúng lúc khách bật
 * `prefers-reduced-motion`) — trả thẳng `target`, nhảy số ngay, không có
 * khung hình nào chạy.
 *
 * Đích đổi giữa chừng lúc đang chạy (khách kéo thanh km liên tục) thì chặng
 * animation MỚI xuất phát từ đúng số đang hiện trên màn hình lúc đó, không
 * giật về từ đầu — nên `fromRef` đọc `displayRef.current` (số mới nhất đã
 * `setState`), không đọc `target` cũ.
 */
export function useAnimatedNumber(target: number, options: { readonly durationMs?: number; readonly disabled?: boolean } = {}): number {
  const { durationMs = DEFAULT_DURATION_MS, disabled = false } = options;
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(display);
  const frameRef = useRef<number | null>(null);

  // Đồng bộ ref sau mỗi lần render, KHÔNG trong lúc render (`react-hooks/refs`).
  // Khai báo TRƯỚC hiệu ứng chạy animation bên dưới: hiệu ứng chạy theo đúng
  // thứ tự khai báo, nên hiệu ứng dưới luôn đọc được số vừa render xong.
  useEffect(() => {
    displayRef.current = display;
  });

  useEffect(() => {
    if (disabled) {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      setDisplay(target);
      return undefined;
    }

    const from = displayRef.current;
    const delta = target - from;
    if (delta === 0) return undefined;

    const start = performance.now();
    function step(now: number): void {
      const progress = Math.min(1, (now - start) / durationMs);
      setDisplay(from + delta * progress);
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(step);
      } else {
        frameRef.current = null;
      }
    }
    frameRef.current = requestAnimationFrame(step);

    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    };
  }, [target, disabled, durationMs]);

  return disabled ? target : display;
}
