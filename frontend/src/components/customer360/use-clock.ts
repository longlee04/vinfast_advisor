import { useSyncExternalStore } from "react";

function subscribe(onChange: () => void): () => void {
  const timer = window.setInterval(onChange, 30_000);
  return () => window.clearInterval(timer);
}

function snapshot(): number {
  return Math.floor(Date.now() / 30_000) * 30_000;
}

/** Đồng hồ làm tròn 30 giây cho nhãn "12 phút" — không gọi `Date.now()` trong render; server trả 0. */
export function useClock(): number {
  return useSyncExternalStore(subscribe, snapshot, () => 0);
}
