import type { ConversationSummary } from "@/types/agent";

export type ConversationIntent =
  | "vehicle_consultation"
  | "comparison"
  | "price"
  | "charging_station"
  | "showroom"
  | "test_drive"
  | "policy"
  | "advisor"
  | "general";

export interface EnrichedConversation {
  readonly id: string;
  readonly sessionId: string;
  readonly rawTitle: string | null;
  readonly title: string;
  readonly preview: string;
  readonly intent: ConversationIntent;
  readonly iconType: string;
  readonly shortId: string;
  readonly formattedTime: string;
  readonly rawTime: Date;
  readonly isPinned: boolean;
  readonly isAdvisorActive: boolean;
  readonly status: string;
  readonly messageCount?: number;
}

export type ConversationGroupKey = "pinned" | "today" | "yesterday" | "last7Days" | "older";

export interface ConversationGroup {
  readonly key: ConversationGroupKey;
  readonly label: string;
  readonly items: readonly EnrichedConversation[];
}

const PINNED_STORAGE_KEY = "p150.pinned-conversations";
const TITLES_STORAGE_KEY = "p150.custom-conversation-titles";
const PREVIEWS_STORAGE_KEY = "p150.cached-conversation-previews";

/** Read list of pinned conversation IDs from localStorage */
export function getPinnedConversationIds(): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.localStorage.getItem(PINNED_STORAGE_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(Array.isArray(parsed) ? parsed : []);
  } catch {
    return new Set();
  }
}

/** Set pin state for a conversation */
export function setPinnedConversation(id: string, isPinned: boolean): void {
  if (typeof window === "undefined") return;
  try {
    const current = getPinnedConversationIds();
    if (isPinned) {
      current.add(id);
    } else {
      current.delete(id);
    }
    window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(Array.from(current)));
  } catch {
    // ignore
  }
}

/** Read map of custom conversation titles from localStorage */
export function getCustomConversationTitles(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(TITLES_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

/** Save custom title for a conversation */
export function setCustomConversationTitle(id: string, title: string): void {
  if (typeof window === "undefined") return;
  try {
    const current = getCustomConversationTitles();
    if (title.trim()) {
      current[id] = title.trim();
    } else {
      delete current[id];
    }
    window.localStorage.setItem(TITLES_STORAGE_KEY, JSON.stringify(current));
  } catch {
    // ignore
  }
}

/** Read cached previews from localStorage */
export function getCachedPreviews(): Record<string, { preview: string; messageCount?: number; intent?: string }> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(PREVIEWS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null ? parsed : {};
  } catch {
    return {};
  }
}

/** Cache preview and message count for a conversation */
export function setCachedPreview(
  id: string,
  preview: string,
  messageCount?: number,
  intent?: string,
): void {
  if (typeof window === "undefined") return;
  try {
    const current = getCachedPreviews();
    current[id] = { preview: preview.trim(), messageCount, intent };
    window.localStorage.setItem(PREVIEWS_STORAGE_KEY, JSON.stringify(current));
  } catch {
    // ignore
  }
}

/** Remove all custom data for a deleted conversation */
export function clearConversationCustomData(id: string): void {
  if (typeof window === "undefined") return;
  try {
    const pinned = getPinnedConversationIds();
    pinned.delete(id);
    window.localStorage.setItem(PINNED_STORAGE_KEY, JSON.stringify(Array.from(pinned)));

    const titles = getCustomConversationTitles();
    delete titles[id];
    window.localStorage.setItem(TITLES_STORAGE_KEY, JSON.stringify(titles));

    const previews = getCachedPreviews();
    delete previews[id];
    window.localStorage.setItem(PREVIEWS_STORAGE_KEY, JSON.stringify(previews));
  } catch {
    // ignore
  }
}

/** Detect known VinFast vehicle models from text in order of appearance */
export function detectVehicleModels(text: string): string[] {
  const normalized = text.toLowerCase();
  const matches: Array<{ index: number; name: string }> = [];

  const patterns: Array<{ regex: RegExp; name: string }> = [
    { regex: /\bvf\s*9\b/i, name: "VF 9" },
    { regex: /\bvf\s*8\b/i, name: "VF 8" },
    { regex: /\bvf\s*7\b/i, name: "VF 7" },
    { regex: /\bvf\s*6\b/i, name: "VF 6" },
    { regex: /\bvf\s*5\b/i, name: "VF 5" },
    { regex: /\bvf\s*3\b/i, name: "VF 3" },
    { regex: /\bvf\s*e34\b/i, name: "VF e34" },
    { regex: /\bminio\b/i, name: "Minio" },
    { regex: /\bklaras?\b|\bklara\s*s\b/i, name: "Klara S" },
    { regex: /\bfelizs?\b|\bfeliz\s*s\b/i, name: "Feliz S" },
    { regex: /\bevo\s*200\b|\bevo\b/i, name: "Evo 200" },
    { regex: /\bventos?\b|\bvento\s*s\b/i, name: "Vento S" },
    { regex: /\btheons?\b|\btheon\s*s\b/i, name: "Theon S" },
    { regex: /\bdrgnfly\b|\bdragonfly\b/i, name: "DrgnFly" },
  ];

  for (const item of patterns) {
    const match = item.regex.exec(normalized);
    if (match) {
      matches.push({ index: match.index, name: item.name });
    }
  }

  matches.sort((a, b) => a.index - b.index);
  const result: string[] = [];
  for (const m of matches) {
    if (!result.includes(m.name)) {
      result.push(m.name);
    }
  }
  return result;
}

/** Detect intent category from text or summary metadata */
export function detectIntent(text: string): ConversationIntent {
  const lower = text.toLowerCase();

  // 1. Comparison
  if (
    lower.includes("so sánh") ||
    lower.includes("vs") ||
    lower.includes("khác nhau") ||
    lower.includes("so voi") ||
    lower.includes("hơn hay") ||
    lower.includes("nên mua xe nào") ||
    lower.includes("xe nào tốt hơn")
  ) {
    return "comparison";
  }

  // 2. Charging station
  if (
    lower.includes("trạm sạc") ||
    lower.includes("sạc pin") ||
    lower.includes("sạc nhanh") ||
    lower.includes("trụ sạc") ||
    lower.includes("cổng sạc") ||
    lower.includes("sạc ở đâu")
  ) {
    return "charging_station";
  }

  // 3. Showroom / Location
  if (
    lower.includes("showroom") ||
    lower.includes("đại lý") ||
    lower.includes("cửa hàng") ||
    lower.includes("bản đồ") ||
    lower.includes("xưởng dịch vụ")
  ) {
    return "showroom";
  }

  // 4. Test drive
  if (
    lower.includes("lái thử") ||
    lower.includes("đăng ký lái") ||
    lower.includes("hẹn lịch lái") ||
    lower.includes("trải nghiệm xe")
  ) {
    return "test_drive";
  }

  // 5. Advisor / Live support
  if (
    lower.includes("tư vấn viên") ||
    lower.includes("nhân viên") ||
    lower.includes("chuyên viên") ||
    lower.includes("người thật") ||
    lower.includes("hỗ trợ trực tiếp")
  ) {
    return "advisor";
  }

  // 6. Policy / Warranty / Software
  if (
    lower.includes("chính sách") ||
    lower.includes("bảo hành") ||
    lower.includes("thuê pin") ||
    lower.includes("mua pin") ||
    lower.includes("ưu đãi") ||
    lower.includes("khuyến mãi") ||
    lower.includes("estore") ||
    lower.includes("phần mềm") ||
    lower.includes("tài liệu")
  ) {
    return "policy";
  }

  // 7. Vehicle Consultation (e.g. "xe 5 chỗ, ngân sách 800 triệu", "tư vấn xe")
  if (
    lower.includes("tư vấn") ||
    lower.includes("chọn xe") ||
    lower.includes("cần xe") ||
    lower.includes("mua xe") ||
    lower.includes("5 chỗ") ||
    lower.includes("7 chỗ") ||
    lower.includes("suv") ||
    lower.includes("sedan") ||
    lower.includes("xe máy") ||
    lower.includes("ô tô")
  ) {
    return "vehicle_consultation";
  }

  // 8. Price / TCO / Installment (pure pricing questions)
  if (
    lower.includes("giá") ||
    lower.includes("lăn bánh") ||
    lower.includes("báo giá") ||
    lower.includes("bảng giá") ||
    lower.includes("chi phí") ||
    lower.includes("trả góp") ||
    lower.includes("ngân sách") ||
    lower.includes("triệu") ||
    lower.includes("tỷ") ||
    lower.includes("tco")
  ) {
    return "price";
  }

  if (detectVehicleModels(text).length > 0) {
    return "vehicle_consultation";
  }

  return "general";
}

/** Rule-based title derivation from first message or original title */
export function deriveConversationTitle(
  rawTitle: string | null | undefined,
  firstMessageText?: string | null,
  intent?: ConversationIntent,
): string {
  // If raw title is custom or meaningful (not starting with generic "Phiên tư vấn")
  if (rawTitle && rawTitle.trim()) {
    const cleaned = rawTitle.replace(/\s*\(\d{2}\/\d{2}\/\d{4}\)$/, "").trim();
    if (
      cleaned &&
      !cleaned.toLowerCase().startsWith("phiên tư vấn") &&
      !cleaned.toLowerCase().startsWith("phiên chat")
    ) {
      return cleaned;
    }
  }

  const textToAnalyze = (firstMessageText?.trim() || rawTitle?.trim() || "").replace(/\s+/g, " ");
  if (!textToAnalyze) return "Cuộc trò chuyện mới";

  const models = detectVehicleModels(textToAnalyze);
  const derivedIntent = intent || detectIntent(textToAnalyze);

  // Extract budget mentions (e.g. 800 triệu, 1 tỷ, 500tr)
  const budgetMatch = textToAnalyze.match(/(\d+(?:[.,]\d+)?\s*(?:triệu|tr|tỷ|ty|trieu|vnd|đ))/i);
  const budgetStr = budgetMatch ? budgetMatch[0].trim() : null;

  // Extract seats mentions (e.g. 5 chỗ, 7 chỗ)
  const seatsMatch = textToAnalyze.match(/(\d+\s*chỗ)/i);
  const seatsStr = seatsMatch ? seatsMatch[0].trim() : null;

  // 1. Comparison
  if (derivedIntent === "comparison") {
    if (models.length >= 2) {
      return `So sánh ${models[0]} và ${models[1]}`;
    }
    if (models.length === 1) {
      return `So sánh ${models[0]}`;
    }
    return "So sánh dòng xe";
  }

  // 2. Charging station
  if (derivedIntent === "charging_station") {
    if (textToAnalyze.toLowerCase().includes("hà nội")) return "Tìm trạm sạc Hà Nội";
    if (
      textToAnalyze.toLowerCase().includes("hồ chí minh") ||
      textToAnalyze.toLowerCase().includes("tp.hcm") ||
      textToAnalyze.toLowerCase().includes("sài gòn")
    ) {
      return "Tìm trạm sạc TP.HCM";
    }
    if (textToAnalyze.toLowerCase().includes("đà nẵng")) return "Tìm trạm sạc Đà Nẵng";
    if (models.length > 0) return `Trạm sạc cho ${models.join(", ")}`;
    return "Tìm kiếm trạm sạc";
  }

  // 3. Showroom
  if (derivedIntent === "showroom") {
    if (textToAnalyze.toLowerCase().includes("hà nội")) return "Showroom tại Hà Nội";
    if (
      textToAnalyze.toLowerCase().includes("hồ chí minh") ||
      textToAnalyze.toLowerCase().includes("tp.hcm")
    ) {
      return "Showroom tại TP.HCM";
    }
    return "Tìm showroom & đại lý";
  }

  // 4. Test drive
  if (derivedIntent === "test_drive") {
    if (models.length > 0) return `Đăng ký lái thử ${models.join(", ")}`;
    return "Đăng ký lái thử xe";
  }

  // 5. Price
  if (derivedIntent === "price") {
    if (models.length > 0) {
      if (textToAnalyze.toLowerCase().includes("lăn bánh")) {
        return `Giá lăn bánh ${models.join(", ")}`;
      }
      return `Bảng giá ${models.join(", ")}`;
    }
    if (budgetStr) return `Xe tầm giá ${budgetStr}`;
    return "Báo giá xe VinFast";
  }

  // 6. Policy
  if (derivedIntent === "policy") {
    if (textToAnalyze.toLowerCase().includes("thuê pin") || textToAnalyze.toLowerCase().includes("pin")) {
      return "Chính sách thuê pin";
    }
    if (textToAnalyze.toLowerCase().includes("estore") || textToAnalyze.toLowerCase().includes("phần mềm")) {
      return "Chính sách VF eStore";
    }
    if (textToAnalyze.toLowerCase().includes("bảo hành")) {
      return "Chính sách bảo hành";
    }
    if (models.length > 0) return `Chính sách ${models.join(", ")}`;
    return "Chính sách & ưu đãi";
  }

  // 7. Advisor
  if (derivedIntent === "advisor") {
    return "Tư vấn viên trực tiếp";
  }

  // 8. Vehicle Consultation
  if (derivedIntent === "vehicle_consultation") {
    if (models.length > 0) {
      return `Tư vấn ${models.join(", ")}`;
    }
    if (seatsStr && budgetStr) {
      return `Tư vấn xe ${seatsStr} (~${budgetStr})`;
    }
    if (seatsStr) {
      return `Tư vấn xe ${seatsStr}`;
    }
    if (budgetStr) {
      return `Tư vấn xe tầm ${budgetStr}`;
    }
    if (textToAnalyze.toLowerCase().includes("xe máy")) {
      return "Tư vấn xe máy điện";
    }
    if (textToAnalyze.toLowerCase().includes("ô tô") || textToAnalyze.toLowerCase().includes("suv")) {
      return "Tư vấn ô tô điện";
    }
    return "Tư vấn chọn xe";
  }

  const cleaned = textToAnalyze.replace(/\s*\(\d{2}\/\d{2}\/\d{4}\)$/, "").trim();
  return cleaned || "Tư vấn VinFast AI";
}

/** Format short ID: #CV-XXXX */
export function formatShortId(id: string): string {
  const cleaned = id.replace(/-/g, "");
  return `#CV-${cleaned.slice(0, 4).toUpperCase()}`;
}

/** Format timestamp for 3rd line of item */
export function formatItemTime(dateInput: string | Date): string {
  const date = typeof dateInput === "string" ? new Date(dateInput) : dateInput;
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isSameDay) {
    return new Intl.DateTimeFormat("vi-VN", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date);
  }

  const isSameYear = date.getFullYear() === now.getFullYear();
  if (isSameYear) {
    return new Intl.DateTimeFormat("vi-VN", {
      day: "2-digit",
      month: "2-digit",
    }).format(date);
  }

  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

/** Enrich a ConversationSummary with calculated metadata */
export function enrichConversation(
  summary: ConversationSummary,
  options?: {
    isPinned?: boolean;
    customTitle?: string;
    cachedPreview?: string;
    messageCount?: number;
  },
): EnrichedConversation {
  const rawDate = new Date(summary.last_activity_at);
  const isAdvisor = Boolean(summary.assigned_advisor_id);
  const customTitle = options?.customTitle || getCustomConversationTitles()[summary.conversation_id];
  const isPinned = options?.isPinned ?? getPinnedConversationIds().has(summary.conversation_id);

  const cached = getCachedPreviews()[summary.conversation_id];
  const preview =
    options?.cachedPreview ||
    cached?.preview ||
    (isAdvisor
      ? "Tư vấn viên đang phụ trách cuộc trò chuyện..."
      : "Tra cứu thông tin và trao đổi cùng trợ lý ảo VinFast...");

  const intent = detectIntent(`${summary.title ?? ""} ${customTitle || ""} ${preview}`);
  const title = customTitle?.trim() || deriveConversationTitle(summary.title ?? null, preview, intent);
  const shortId = formatShortId(summary.conversation_id);
  const formattedTime = formatItemTime(rawDate);

  return {
    id: summary.conversation_id,
    sessionId: summary.session_id ?? summary.conversation_id,
    rawTitle: summary.title ?? null,
    title,
    preview,
    intent,
    iconType: intent,
    shortId,
    formattedTime,
    rawTime: rawDate,
    isPinned,
    isAdvisorActive: isAdvisor,
    status: summary.status ?? summary.state,
    messageCount: options?.messageCount || cached?.messageCount,
  };
}

/** Group enriched conversations by time & pinned status */
export function groupConversations(
  conversations: readonly EnrichedConversation[],
): readonly ConversationGroup[] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
  const startOf7DaysAgo = startOfToday - 6 * 24 * 60 * 60 * 1000;

  const pinnedItems: EnrichedConversation[] = [];
  const todayItems: EnrichedConversation[] = [];
  const yesterdayItems: EnrichedConversation[] = [];
  const last7DaysItems: EnrichedConversation[] = [];
  const olderItems: EnrichedConversation[] = [];

  for (const item of conversations) {
    if (item.isPinned) {
      pinnedItems.push(item);
      continue;
    }

    const time = item.rawTime.getTime();
    if (Number.isNaN(time)) {
      olderItems.push(item);
    } else if (time >= startOfToday) {
      todayItems.push(item);
    } else if (time >= startOfYesterday) {
      yesterdayItems.push(item);
    } else if (time >= startOf7DaysAgo) {
      last7DaysItems.push(item);
    } else {
      olderItems.push(item);
    }
  }

  const groups: ConversationGroup[] = [];

  if (pinnedItems.length > 0) {
    groups.push({ key: "pinned", label: "ĐÃ GHIM", items: pinnedItems });
  }
  if (todayItems.length > 0) {
    groups.push({ key: "today", label: "HÔM NAY", items: todayItems });
  }
  if (yesterdayItems.length > 0) {
    groups.push({ key: "yesterday", label: "HÔM QUA", items: yesterdayItems });
  }
  if (last7DaysItems.length > 0) {
    groups.push({ key: "last7Days", label: "7 NGÀY QUA", items: last7DaysItems });
  }
  if (olderItems.length > 0) {
    groups.push({ key: "older", label: "CŨ HƠN", items: olderItems });
  }

  return groups;
}

/** Filter conversations in realtime based on search query */
export function filterConversations(
  conversations: readonly EnrichedConversation[],
  searchQuery: string,
): readonly EnrichedConversation[] {
  const query = searchQuery.trim().toLowerCase();
  if (!query) return conversations;

  return conversations.filter((item) => {
    return (
      item.title.toLowerCase().includes(query) ||
      item.preview.toLowerCase().includes(query) ||
      item.shortId.toLowerCase().includes(query) ||
      (item.rawTitle && item.rawTitle.toLowerCase().includes(query)) ||
      detectVehicleModels(query).some(
        (m) =>
          item.title.toLowerCase().includes(m.toLowerCase()) ||
          item.preview.toLowerCase().includes(m.toLowerCase()),
      )
    );
  });
}
