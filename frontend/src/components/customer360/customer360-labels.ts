import type { BuyerFor, HeatBand, OpportunityStatus, SalesStage, SessionKind } from "@/types/customer360";

import type { BadgeTone } from "../advisor/offer-state-labels";

/**
 * Nhãn hiển thị cho hồ sơ khách 360 — cùng khuôn `offer-state-labels.ts`: `Record<Code, …>`
 * để TypeScript báo lỗi ngay khi backend thêm/bớt một mã mà nhãn chưa theo kịp.
 *
 * Màu: xanh chỉ dành cho CTA/đang chọn, đỏ chỉ cho lỗi (`frontend/DESIGN.md` §2, §3) —
 * nên độ nóng "Nóng" dùng tông cảnh báo, không dùng đỏ.
 */

export const SALES_STAGE_ORDER: readonly SalesStage[] = ["DISCOVER", "COMPARE", "QUOTE", "TEST_DRIVE", "CLOSE"];

export const SALES_STAGE_LABELS: Record<SalesStage, string> = {
  DISCOVER: "Tìm hiểu",
  COMPARE: "So sánh",
  QUOTE: "Báo giá",
  TEST_DRIVE: "Lái thử",
  CLOSE: "Chốt",
};

export const HEAT_BAND_BADGES: Record<HeatBand, { readonly tone: BadgeTone; readonly label: string }> = {
  HOT: { tone: "warning", label: "Nóng" },
  WARM: { tone: "neutral", label: "Ấm" },
  COLD: { tone: "neutral", label: "Lạnh" },
};

export const OPPORTUNITY_STATUS_LABELS: Record<OpportunityStatus, string> = {
  OPEN: "Đang mở",
  DORMANT: "Tạm lắng",
  WON: "Đã chốt",
  LOST: "Đã mất",
  REPLACED: "Đã gộp",
};

export const BUYER_FOR_LABELS: Record<BuyerFor, string> = {
  SELF: "Mua cho bản thân",
  FAMILY: "Mua cho người nhà",
  COMPANY: "Mua cho công ty",
  OTHER: "Mua cho người khác",
};

export const SESSION_KIND_LABELS: Record<SessionKind, string> = {
  SALES: "Tư vấn",
  SUPPORT: "Hỗ trợ",
  UNASSIGNED: "Chưa phân loại",
};

/** Nhãn slot hội thoại — khoá khớp `SlotName` (`src/agents/domain/values.py`). */
export const SLOT_LABELS: Record<string, string> = {
  vehicle_type: "Loại xe",
  interest_vehicle: "Mẫu quan tâm",
  budget_max_vnd: "Ngân sách tối đa",
  budget_min_vnd: "Ngân sách tối thiểu",
  budget_stated_vnd: "Ngân sách khách nói",
  purpose: "Mục đích",
  passenger_count: "Số người",
  required_range_km: "Quãng đường cần",
  home_charging: "Sạc tại nhà",
  registration_province: "Tỉnh đăng ký",
  max_load_kg: "Tải trọng",
  habit_need_tags: "Nhu cầu thêm",
};

const VEHICLE_TYPE_LABELS: Record<string, string> = { CAR: "Ô tô điện", ELECTRIC_MOTORBIKE: "Xe máy điện" };

/** Slot nội bộ, không hiện cho TVV. */
const HIDDEN_SLOTS = new Set(["purpose_bucket"]);

function formatVnd(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toLocaleString("vi-VN", { maximumFractionDigits: 2 })} tỷ`;
  if (value >= 1_000_000) return `${Math.round(value / 1_000_000).toLocaleString("vi-VN")} triệu`;
  return `${value.toLocaleString("vi-VN")} đ`;
}

/** Giá trị slot dạng đọc được. Không suy diễn — chỉ đổi cách viết. */
export function formatSlotValue(slot: string, value: unknown): string | null {
  if (value === null || value === undefined || value === "" || value === "__declined__") return null;
  if (Array.isArray(value)) return value.length ? value.join(", ") : null;
  if (slot === "vehicle_type") return VEHICLE_TYPE_LABELS[String(value)] ?? String(value);
  if (slot === "home_charging") return value === true || value === "true" ? "Có" : value === false || value === "false" ? "Không" : String(value);
  if (slot.endsWith("_vnd")) {
    const amount = Number(value);
    return Number.isFinite(amount) ? formatVnd(amount) : String(value);
  }
  if (slot === "passenger_count") return `${value} người`;
  if (slot === "required_range_km") return `${value} km`;
  return String(value);
}

/** Danh sách slot đã có, theo thứ tự `SLOT_LABELS`, bỏ slot nội bộ/rỗng. */
export function knownSlots(slots: Record<string, unknown> | undefined | null): { slot: string; label: string; value: string }[] {
  if (!slots) return [];
  const ordered = [...Object.keys(SLOT_LABELS), ...Object.keys(slots).filter((key) => !(key in SLOT_LABELS))];
  return ordered.flatMap((slot) => {
    if (HIDDEN_SLOTS.has(slot) || !(slot in slots)) return [];
    const value = formatSlotValue(slot, slots[slot]);
    return value === null ? [] : [{ slot, label: SLOT_LABELS[slot] ?? slot, value }];
  });
}

/** Một dòng tóm tắt nhu cầu từ slot thật — thay cho các khoá không tồn tại trước đây. */
export function needSummary(slots: Record<string, unknown> | undefined | null): string | null {
  const known = knownSlots(slots);
  // Con số khách NÓI RA thắng trần đã nới biên (xem `BUDGET_STATED_VND` ở backend).
  const hasStated = known.some((item) => item.slot === "budget_stated_vnd");
  const parts = known
    .filter((item) => ["interest_vehicle", "vehicle_type", "budget_stated_vnd", "budget_max_vnd", "purpose"].includes(item.slot))
    .filter((item) => !(hasStated && item.slot === "budget_max_vnd"))
    .slice(0, 3)
    .map((item) => `${item.label}: ${item.value}`);
  return parts.length ? parts.join(" · ") : null;
}

/** Nhãn field thông tin khách tự nói (`customer_insights.field`, backend `InsightField`). */
export const INSIGHT_FIELD_LABELS: Record<string, string> = {
  purchase_timeframe: "Thời điểm định mua",
  payment_method: "Hình thức thanh toán",
  current_vehicle: "Xe đang đi",
  trade_in: "Đổi xe cũ",
  decision_maker: "Người quyết định",
  competitor_brand: "Hãng đang cân nhắc",
  other_concern: "Băn khoăn khác",
  buyer_for: "Mua cho",
  customer_group: "Nhóm khách",
  registration_province: "Tỉnh đăng ký",
  home_charging: "Sạc tại nhà",
};
