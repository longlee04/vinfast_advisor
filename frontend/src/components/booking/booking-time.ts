/** Múi giờ cố định của showroom — lịch lái thử luôn hiểu theo giờ Việt Nam. */
const VN_TIME_ZONE = "Asia/Ho_Chi_Minh";

/**
 * Dựng thời điểm lái thử từ ngày + khung giờ khách chọn.
 *
 * Ghim thẳng `+07:00` (Việt Nam không có DST nên offset cố định quanh năm).
 * Bản cũ dựng bằng `T14:30:00.000Z` — tức 14:30 UTC = 21:30 VN: advisor thấy
 * lịch lệch 7 tiếng so với giờ khách chọn.
 */
export function buildScheduledAt(date: string, timeSlot: string): string {
  return new Date(`${date}T${timeSlot}:00+07:00`).toISOString();
}

/**
 * "Ngày mai" mặc định của form, tính theo NGÀY Ở VIỆT NAM chứ không theo máy
 * khách/máy chủ. Bản cũ dùng `toISOString()` (UTC): lúc 01:00 sáng VN, UTC vẫn
 * là hôm trước → "ngày mai" bị lùi một ngày.
 */
export function defaultBookingDate(now: Date = new Date()): string {
  // `en-CA` cho thẳng dạng YYYY-MM-DD; cộng 1 ngày bằng Date.UTC thuần để không
  // dính múi giờ máy lần nữa.
  const todayVn = new Intl.DateTimeFormat("en-CA", { timeZone: VN_TIME_ZONE }).format(now);
  const [year, month, day] = todayVn.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day + 1)).toISOString().split("T")[0];
}
