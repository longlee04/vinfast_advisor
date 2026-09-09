"use client";

import { useEffect, useState } from "react";

/**
 * `?embed=1` = trang đang chạy TRONG cửa sổ hội thoại (iframe cùng domain):
 * header/dock/footer tự ẩn.
 *
 * KHÔNG dùng `useSearchParams`: hook đó bắt trang tĩnh phải bọc Suspense, và
 * đã làm `next build` prerender fail ở /motorbikes, /test-drive (moi13,
 * 2026-08-31). Đọc `window.location.search` sau mount: SSR luôn render đủ
 * chrome (đúng cho trang thường), trong iframe chrome biến mất ngay frame đầu
 * sau hydrate — chớp không đáng kể so với vỡ build.
 */
export function useEmbedMode(): boolean {
  const [embedded, setEmbedded] = useState(false);
  useEffect(() => {
    try {
      setEmbedded(new URLSearchParams(window.location.search).get("embed") === "1");
    } catch {
      setEmbedded(false);
    }
  }, []);
  return embedded;
}
