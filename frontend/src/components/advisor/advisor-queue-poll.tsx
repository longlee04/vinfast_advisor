"use client";

/**
 * T16.5 — hệ thống chủ động báo tư vấn viên có việc mới trong hàng chờ.
 *
 * Không phá D4 (cấm chat real-time advisor↔khách): đây là chiều hệ thống →
 * advisor, không phải khách → advisor. Cũng không dựng hạ tầng WS/SSE mới —
 * chỉ gọi lại đúng `GET /agent/reviews?status=pending` sau mỗi 30 giây.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchBottleneckSignals, fetchReviews } from "@/lib/api/agent";
import type { QueueEntry } from "@/types/agent";

/** Nhịp mặc định: 30 giây — đủ nhanh cho SLA 60 phút, đủ chậm để không spam. */
export const ADVISOR_POLL_INTERVAL_MS = 30_000;

/** Khoá `localStorage` giữ số mục chờ duyệt của lần poll trước. */
export const LAST_PENDING_COUNT_KEY = "advisor_last_pending_count";

/** Hỏng liên tiếp quá ngưỡng này thì im lặng dừng, không dựng error state. */
const MAX_CONSECUTIVE_FAILURES = 3;

const TAB_TITLE = "Advisor Queue";

export type AdvisorQueuePoll = {
  /** Danh sách chờ duyệt mới nhất, `null` khi chưa poll lần nào. */
  readonly entries: readonly QueueEntry[] | null;
  /** Số mục chờ duyệt hiện tại (0 khi chưa poll lần nào). */
  readonly pendingCount: number;
  /** Số mục MỚI cộng dồn kể từ lần tư vấn viên xác nhận gần nhất. */
  readonly newCount: number;
  /** Tư vấn viên đã nhìn hàng chờ — xoá badge tab và trả lại tiêu đề cũ. */
  readonly acknowledge: () => void;
};

// `localStorage` có thể ném (chế độ riêng tư, quota) — hỏng cache không được
// làm vỡ màn duyệt, nên mọi truy cập đều nuốt lỗi.
function readLastCount(): number | null {
  try {
    const raw = globalThis.localStorage?.getItem(LAST_PENDING_COUNT_KEY);
    if (raw === null || raw === undefined) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isNaN(parsed) ? null : parsed;
  } catch {
    return null;
  }
}

function writeLastCount(count: number): void {
  try {
    globalThis.localStorage?.setItem(LAST_PENDING_COUNT_KEY, String(count));
  } catch {
    // Mất cache chỉ làm lỡ một lần so sánh, không đáng để vỡ UI.
  }
}

/**
 * Poll hàng chờ mỗi `intervalMs`, dừng hẳn khi tab bị ẩn và chạy lại ngay khi
 * tab hiện lại. Ba lần lỗi liên tiếp thì dừng im lặng — tư vấn viên vẫn bấm
 * "Thử lại" trên bảng được.
 */
export function useAdvisorQueuePoll(
  intervalMs: number = ADVISOR_POLL_INTERVAL_MS,
): AdvisorQueuePoll {
  const [entries, setEntries] = useState<readonly QueueEntry[] | null>(null);
  const [newCount, setNewCount] = useState(0);
  const [signalCount, setSignalCount] = useState(0);
  const failuresRef = useRef(0);

  const acknowledge = useCallback(() => {
    setNewCount(0);
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    const stop = () => {
      if (timer === null) return;
      clearInterval(timer);
      timer = null;
    };

    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const [items, signals] = await Promise.all([
          fetchReviews({ status: "pending" }),
          fetchBottleneckSignals({ status: "pending" }),
        ]);
        if (cancelled) return;
        failuresRef.current = 0;
        setEntries(items);
        setSignalCount(signals.length);
        const total = items.length + signals.length;
        const previous = readLastCount();
        writeLastCount(total);
        // Lần đầu chưa có mốc thì chỉ ghi mốc, không báo "mục mới" giả.
        if (previous !== null && total > previous) {
          const delta = total - previous;
          setNewCount((current) => current + delta);
        }
      } catch {
        if (cancelled) return;
        failuresRef.current += 1;
        if (failuresRef.current >= MAX_CONSECUTIVE_FAILURES) stop();
      }
    };

    const start = () => {
      if (timer !== null) return;
      timer = setInterval(() => {
        void poll();
      }, intervalMs);
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        failuresRef.current = 0;
        void poll();
        start();
      } else {
        stop();
      }
    };

    // Lúc mount KHÔNG poll ngay: bảng đã tự tải lượt đầu, gọi thêm là thừa.
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [intervalMs]);

  const pendingCount = (entries?.length ?? 0) + signalCount;

  useEffect(() => {
    if (newCount <= 0) return;
    const previousTitle = document.title;
    document.title = `(${pendingCount}) ${TAB_TITLE}`;
    return () => {
      document.title = previousTitle;
    };
  }, [newCount, pendingCount]);

  return { entries, pendingCount, newCount, acknowledge };
}

/** Dải thông báo "có mục mới" — ẩn hẳn khi không có gì mới. */
export function AdvisorQueuePollToast({
  count,
  onDismiss,
}: Readonly<{ count: number; onDismiss: () => void }>) {
  if (count <= 0) return null;
  return (
    <div className="queue-demo-tools" role="status">
      <span>Có {count} mục mới trong hàng chờ</span>
      <button className="table-action" onClick={onDismiss} type="button">
        Đóng
      </button>
    </div>
  );
}
