"use client";

import { useEffect, useState } from "react";

export type UseTypewriterOptions = {
  /** ms giữa mỗi ký tự lúc gõ. */
  readonly typeMs?: number;
  /** ms giữa mỗi ký tự lúc xoá. */
  readonly deleteMs?: number;
  /** ms đứng yên sau khi gõ xong một câu, trước khi xoá. */
  readonly holdMs?: number;
  /** Tắt thì dừng hẳn và không lên lịch hẹn giờ nào nữa. */
  readonly active: boolean;
};

const DEFAULT_TYPE_MS = 45;
const DEFAULT_DELETE_MS = 25;
const DEFAULT_HOLD_MS = 1500;

/**
 * Máy trạng thái gõ chữ / xoá chữ / lặp qua từng câu trong `suggestions`.
 *
 * Trả về câu ĐANG HIỆN (một phần hoặc trọn vẹn) và câu TRỌN VẸN của lượt hiện
 * tại — chỗ gọi cần câu trọn vẹn để điền vào ô gõ khi khách bấm chọn giữa
 * chừng lúc chữ chưa gõ xong.
 *
 * Không nhận thẳng mảng `suggestions` vào dependency của bộ đếm giờ: mảng này
 * thường được dựng lại mỗi lần render ở nơi gọi (`.map(...)` mới mỗi lần), lấy
 * thẳng làm dependency sẽ khiến hiệu ứng chạy lại và animation giật lại từ đầu
 * liên tục. Đếm giờ chỉ phụ thuộc GIÁ TRỊ câu hiện tại (một chuỗi, so sánh theo
 * nội dung) và SỐ LƯỢNG câu, không phụ thuộc identity của mảng.
 */
export function useTypewriter(
  suggestions: readonly string[],
  options: UseTypewriterOptions,
): { readonly display: string; readonly current: string } {
  const { typeMs = DEFAULT_TYPE_MS, deleteMs = DEFAULT_DELETE_MS, holdMs = DEFAULT_HOLD_MS, active } = options;
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [charCount, setCharCount] = useState(0);
  const [phase, setPhase] = useState<"typing" | "deleting">("typing");

  const count = suggestions.length;
  const current = count > 0 ? suggestions[suggestionIndex % count] ?? "" : "";

  // Tạm dừng rồi chạy lại (khách xoá sạch ô gõ), hoặc số câu gợi ý đổi: gõ lại
  // từ đầu, từ câu đầu tiên.
  useEffect(() => {
    setSuggestionIndex(0);
    setCharCount(0);
    setPhase("typing");
  }, [active, count]);

  useEffect(() => {
    if (!active || count === 0) return undefined;

    if (phase === "typing") {
      if (charCount < current.length) {
        const timer = setTimeout(() => setCharCount((value) => value + 1), typeMs);
        return () => clearTimeout(timer);
      }
      const timer = setTimeout(() => setPhase("deleting"), holdMs);
      return () => clearTimeout(timer);
    }

    // phase === "deleting"
    if (charCount > 0) {
      const timer = setTimeout(() => setCharCount((value) => value - 1), deleteMs);
      return () => clearTimeout(timer);
    }
    setSuggestionIndex((index) => (index + 1) % count);
    setPhase("typing");
    return undefined;
  }, [active, count, phase, charCount, current, typeMs, deleteMs, holdMs]);

  return { display: current.slice(0, charCount), current };
}
