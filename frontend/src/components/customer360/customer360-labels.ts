import type {
  BuyerFor,
  HeatBand,
  OpeningBasis,
  OpportunityStatus,
  SalesStage,
  SessionKind,
  VehicleInterestRole,
} from "@/types/customer360";

import { type BadgeTone, bottleneckLabel } from "../advisor/offer-state-labels";

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

// ---------------------------------------------------------------- Màn theo mockup (plan §13)

/** Nhãn rào cản — mã nút thắt dùng nhãn có sẵn; "OTHER" là băn khoăn khách tự nói (insight). */
export function barrierLabel(code: string): string {
  return code === "OTHER" ? "Băn khoăn khác" : bottleneckLabel(code);
}

/** Câu "Việc nên làm" — nhãn backend giữ mã rào cản thô, nên dịch mã ở đây. */
export function nextActionLabel(action: { readonly code: string; readonly label: string }): string {
  if (action.code.startsWith("RESOLVE_")) return `Xử lý băn khoăn: ${barrierLabel(action.code.slice("RESOLVE_".length)).toLowerCase()}`;
  return action.label;
}

const STAGE_BASIS_TEXT: Record<Exclude<OpeningBasis["kind"], "BARRIER" | "MISSING">, string> = {
  TEST_DRIVE: "Dựa trên lịch lái thử đã đặt.",
  QUOTE: "Dựa trên báo giá lăn bánh khách đã xem.",
  COMPARE: "Dựa trên các mẫu khách đang so sánh.",
  DEFAULT: "Dựa trên nhu cầu đã trao đổi.",
};

/** Dòng phụ "Dựa trên …" dưới gợi ý mở lời. */
export function openingBasisText(basis: OpeningBasis | undefined): string | null {
  if (!basis) return null;
  if (basis.kind === "BARRIER") return `Dựa trên rào cản chính (${barrierLabel(basis.code ?? "")}).`;
  if (basis.kind === "MISSING") return `Dựa trên thông tin còn thiếu (${(SLOT_LABELS[basis.code ?? ""] ?? basis.code ?? "").toLowerCase()}).`;
  return STAGE_BASIS_TEXT[basis.kind];
}

export function vehicleRoleLabel(role: VehicleInterestRole, rank: number | null): string {
  if (role === "CHOSEN") return "Khách đã chọn";
  if (role === "COMPARED") return "Khách đem ra so sánh";
  if (role === "MENTIONED") return "Khách có nhắc";
  return rank ? `AI đề xuất số ${rank}` : "AI đề xuất";
}

/** Ghi chú mốc Lái thử theo trạng thái lịch. */
export const BOOKING_NOTE_LABELS: Record<string, string> = {
  REQUESTED: "chưa xác nhận",
  CONFIRMED: "đã xác nhận",
};

/** Ai đang trả lời phiên đang mở (ownership của phiên). */
export const OWNERSHIP_LABELS: Record<string, string> = {
  AI: "AI đang trả lời",
  PENDING_HANDOFF: "Khách đang chờ tư vấn viên",
  ADVISOR: "Tư vấn viên đang trả lời",
};

/** Bộ lọc trong tab "Đã nhận". Khách chưa ai nhận là một TAB riêng, không phải bộ lọc (plan §20). */
export type QueueFilter = "ALL" | "HOT" | "WAITING" | "TEST_DRIVE";

export const QUEUE_FILTER_LABELS: Record<QueueFilter, string> = {
  ALL: "Tất cả",
  HOT: "Chỉ khách nóng",
  WAITING: "Chờ người thật",
  TEST_DRIVE: "Có lịch lái thử",
};

/** Hồ sơ khách được lưu KHI NÀO — hiện ngay trên trang Khách hàng để tư vấn viên khỏi đoán. */
export const PROFILE_SAVE_EXPLAINER =
  "Hồ sơ khách tự lưu: ngay khi khách đăng nhập (email), khi khách khai tên/SĐT/địa chỉ, và sau mỗi lượt chat (nhu cầu, độ nóng, rào cản). Khách mới nằm ở tab “Chưa nhận” — bấm Nhận khách thì chuyển sang “Đã nhận”.";

/** Khách đã nhận nhưng chưa có nhu cầu nào (chưa chat). */
export const QUEUE_NO_NEED = "Chưa có nhu cầu — nhắn/gọi hỏi khách cần xe gì";

export const POOL_TEXT = {
  hint: "Khách chưa có tư vấn viên phụ trách — gồm cả khách mới đăng ký chưa chat. Nhận khách thì khách thuộc về bạn; tiếp quản hội thoại cũng tự nhận khách.",
  empty: "Không có khách nào đang chờ người nhận.",
  claim: "Nhận khách",
  taken: "Khách vừa được tư vấn viên khác nhận.",
  release: "Trả khách về hàng chờ",
} as const;

export const QUEUE_KPI_LABELS = {
  hot: { title: "Khách nóng", hint: "Nên gọi trong hôm nay", filter: "HOT" },
  waiting: { title: "Đang chờ người thật", hint: "Khách chủ động yêu cầu", filter: "WAITING" },
  test_drives_48h: { title: "Lái thử trong 48 giờ", hint: "Cần xác nhận lịch", filter: "TEST_DRIVE" },
  unanswered: { title: "Câu AI chưa trả lời được", hint: "7 ngày gần nhất", filter: null },
} as const satisfies Record<string, { title: string; hint: string; filter: QueueFilter | null }>;

/** Dòng không có việc nào cần làm ngay. */
export const QUEUE_NO_ACTION = "Theo dõi, chưa cần gọi";

export const QUEUE_FOOTNOTE =
  "Độ nóng tính từ tín hiệu hội thoại: để lại SĐT, đã nhận báo giá, đặt lái thử, thời điểm định mua, số lần quay lại.";

/** Ngân sách khách nói: con số khách NÓI RA thắng, rồi mới tới khoảng min–max. */
export function budgetText(slots: Record<string, unknown> | undefined | null): string | null {
  if (!slots) return null;
  const stated = formatSlotValue("budget_stated_vnd", slots.budget_stated_vnd);
  if (stated) return stated;
  const min = formatSlotValue("budget_min_vnd", slots.budget_min_vnd);
  const max = formatSlotValue("budget_max_vnd", slots.budget_max_vnd);
  if (min && max) return `${min} – ${max}`;
  if (max) return `Tối đa ${max}`;
  if (min) return `Từ ${min}`;
  return null;
}

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** Tuổi ngắn của một mốc ("12 phút", "2 giờ", "Hôm qua", "3 ngày"); `now = 0` (lúc render server) → rỗng. */
export function relativeAge(iso: string | null | undefined, now: number): string {
  if (!iso || !now) return "";
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return "";
  const elapsed = Math.max(0, now - at);
  if (elapsed < MINUTE) return "Vừa xong";
  if (elapsed < HOUR) return `${Math.floor(elapsed / MINUTE)} phút`;
  if (elapsed < DAY) return `${Math.floor(elapsed / HOUR)} giờ`;
  const days = Math.floor(elapsed / DAY);
  return days === 1 ? "Hôm qua" : `${days} ngày`;
}

/** "dd/mm" theo giờ Việt Nam — mốc giai đoạn, lượt rào cản. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return "";
  // Ghép từ phần ngày/tháng: dấu phân cách của "vi-VN" khác nhau giữa các bản ICU ("18/09" vs "18-09").
  const parts = new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" }).formatToParts(at);
  const part = (type: "day" | "month") => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("day")}/${part("month")}`;
}

/** Trang "Tổng quan" của tư vấn viên (plan §15). */
export const DASHBOARD_TEXT = {
  failed: "Không tải được danh sách khách của bạn.",
  todoTitle: "Việc cần làm hôm nay",
  todoHint: "Gấp trước, khách nóng trước",
  todoEmpty: "Chưa có việc nào cần làm ngay.",
  poolTitle: "Hàng chờ",
  poolUnit: "khách chưa ai nhận",
  poolLink: "Mở tab \"Chưa ai nhận\" để nhận khách",
  funnelTitle: "Khách của tôi theo giai đoạn",
  barrierTitle: "Khách của tôi hay lo gì",
  chartEmpty: "Chưa có khách nào.",
  barrierEmpty: "Chưa ghi nhận rào cản nào.",
} as const;

/** Độ gấp của "việc nên làm" — khách đang chờ người > lịch lái thử > gọi khách nóng > còn lại. */
const ACTION_PRIORITY: Record<string, number> = {
  TAKE_OVER: 0,
  CONFIRM_TEST_DRIVE: 1,
  CALL_BACK: 2,
  REVIEW_ATTACH: 3,
  ASK_MISSING: 5,
};

export function actionPriority(code: string): number {
  if (code in ACTION_PRIORITY) return ACTION_PRIORITY[code];
  return code.startsWith("RESOLVE_") ? 4 : 9;
}
