import { describe, expect, it } from "vitest";

import { buildScheduledAt, defaultBookingDate } from "@/components/booking/booking-time";

describe("buildScheduledAt — thời điểm lái thử luôn theo giờ Việt Nam", () => {
  it("14:30 khách chọn là 14:30 GIỜ VN (07:30Z), không phải 14:30 UTC như trước", () => {
    // Lỗi cũ: dựng bằng `T14:30:00.000Z` — advisor thấy lịch lệch 7 tiếng.
    expect(buildScheduledAt("2026-09-01", "14:30")).toBe("2026-09-01T07:30:00.000Z");
  });

  it("giờ sáng sớm không trôi sang ngày khác: 08:30 VN = 01:30Z cùng ngày", () => {
    expect(buildScheduledAt("2026-09-01", "08:30")).toBe("2026-09-01T01:30:00.000Z");
  });
});

describe("defaultBookingDate — 'ngày mai' tính theo Asia/Ho_Chi_Minh", () => {
  it("giữa trưa VN: ngày mai là ngày kế tiếp", () => {
    // 2026-08-29T05:00:00Z = 12:00 VN ngày 29 → ngày mai VN là 30.
    expect(defaultBookingDate(new Date("2026-08-29T05:00:00Z"))).toBe("2026-08-30");
  });

  it("01:30 SÁNG GIỜ VN (18:30Z hôm trước): ngày mai vẫn tính theo VN, ra 31", () => {
    // Máy chủ/trình duyệt ở UTC lúc 2026-08-29T18:30Z: ở VN đã là 01:30 ngày 30
    // → ngày mai của KHÁCH là 31. Bản cũ dùng toISOString (UTC) sẽ ra 30 — sai.
    expect(defaultBookingDate(new Date("2026-08-29T18:30:00Z"))).toBe("2026-08-31");
  });
});
