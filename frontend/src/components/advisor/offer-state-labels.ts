import type { BottleneckCode, OfferState, PromotionType } from "@/types/agent";

export type BadgeTone = "neutral" | "success" | "warning";

/**
 * D11 — ba trạng thái ưu đãi phải phân biệt được bằng CẢ chữ lẫn màu: tư vấn
 * viên đọc lướt theo màu, còn ảnh chụp màn/bản in đen trắng thì chỉ còn chữ.
 *
 * Đây là bảng dùng chung cho các màn advisor đọc `ProfileSnapshot`. Giá trị
 * trùng khít bảng đang nằm trong `advisor-review-panel.tsx`: MỘT bảng màu duy
 * nhất cho `offer_state`, không đẻ bảng thứ hai với tông/chữ khác. Panel duyệt
 * sẽ trỏ về đây khi file đó hết bị khoá bởi task song song.
 */
export const OFFER_STATE_BADGES: Record<
  OfferState,
  { readonly tone: BadgeTone; readonly label: string }
> = {
  NONE_BOTTLENECK: { tone: "neutral", label: "Chưa rõ nút thắt" },
  BOTTLENECK_NO_OFFER: { tone: "warning", label: "Có nhu cầu — chưa có chương trình" },
  BOTTLENECK_OFFER_AVAILABLE: { tone: "success", label: "Có ưu đãi đề xuất" },
};

export const BOTTLENECK_LABELS: Record<BottleneckCode, string> = {
  PRICE: "Giá",
  CHARGING: "Trạm sạc",
  BATTERY: "Pin",
  RANGE: "Quãng đường",
};

export const PROMOTION_TYPE_LABELS: Record<PromotionType, string> = {
  FIXED_DISCOUNT: "Giảm tiền mặt",
  PERCENT_DISCOUNT: "Giảm theo phần trăm",
  GIFT: "Quà tặng",
  FINANCING: "Hỗ trợ trả góp",
  REGISTRATION_SUPPORT: "Hỗ trợ đăng ký",
  OTHER: "Khác",
};

/**
 * Nhãn nút thắt cho chuỗi thô. Backend trả `bottlenecks` của một cơ hội bán
 * hàng dưới dạng `readonly string[]` (không hẹp về `BottleneckCode`), nên mã lạ
 * phải hiện nguyên trạng thay vì thành "undefined".
 */
export function bottleneckLabel(code: string): string {
  return BOTTLENECK_LABELS[code as BottleneckCode] ?? code;
}
