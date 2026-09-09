import { describe, expect, it } from "vitest";
import {
  deriveConversationTitle,
  detectIntent,
  detectVehicleModels,
  enrichConversation,
  filterConversations,
  formatItemTime,
  formatShortId,
  groupConversations,
  type EnrichedConversation,
} from "./conversation-helpers";

describe("conversation-helpers", () => {
  describe("detectVehicleModels", () => {
    it("detects single car models", () => {
      expect(detectVehicleModels("Tư vấn xe VF 7")).toEqual(["VF 7"]);
      expect(detectVehicleModels("So sánh vf8 và vf9")).toEqual(["VF 8", "VF 9"]);
    });

    it("detects motorbike models", () => {
      expect(detectVehicleModels("Tôi muốn tìm hiểu xe Klara S")).toEqual(["Klara S"]);
      expect(detectVehicleModels("Evo 200 giá bao nhiêu")).toEqual(["Evo 200"]);
    });
  });

  describe("detectIntent", () => {
    it("detects comparison intent", () => {
      expect(detectIntent("So sánh VF 6 và VF 7")).toBe("comparison");
    });

    it("detects charging station intent", () => {
      expect(detectIntent("Trạm sạc gần Hà Nội")).toBe("charging_station");
    });

    it("detects price intent", () => {
      expect(detectIntent("Giá xe VF 8 lăn bánh")).toBe("price");
      expect(detectIntent("Bảng giá xe VinFast 2026")).toBe("price");
    });

    it("detects test drive intent", () => {
      expect(detectIntent("Đăng ký lái thử VF 9")).toBe("test_drive");
    });

    it("detects showroom intent", () => {
      expect(detectIntent("Showroom VinFast gần nhất")).toBe("showroom");
    });

    it("detects policy intent", () => {
      expect(detectIntent("Chính sách thuê pin và bảo hành")).toBe("policy");
    });

    it("detects advisor intent", () => {
      expect(detectIntent("Tôi muốn gặp tư vấn viên trực tiếp")).toBe("advisor");
    });

    it("detects vehicle consultation intent", () => {
      expect(detectIntent("Tôi cần xe 5 chỗ, ngân sách 800 triệu")).toBe("vehicle_consultation");
    });
  });

  describe("deriveConversationTitle", () => {
    it("derives comparison title", () => {
      expect(deriveConversationTitle(null, "VF6 với VF7 xe nào tốt hơn?")).toBe("So sánh VF 6 và VF 7");
    });

    it("derives charging station title", () => {
      expect(deriveConversationTitle(null, "Trạm sạc gần Hà Nội ở đâu?")).toBe("Tìm trạm sạc Hà Nội");
    });

    it("derives test drive title", () => {
      expect(deriveConversationTitle(null, "Tôi muốn đăng ký lái thử VF 8")).toBe("Đăng ký lái thử VF 8");
    });

    it("derives consultation title with seats and budget", () => {
      expect(deriveConversationTitle(null, "Tôi muốn mua xe khoảng 800 triệu, 5 chỗ")).toBe("Tư vấn xe 5 chỗ (~800 triệu)");
    });

    it("cleans existing generic dates", () => {
      expect(deriveConversationTitle("Tư vấn ô tô điện (28/08/2026)", null)).toBe("Tư vấn ô tô điện");
    });
  });

  describe("formatShortId", () => {
    it("formats uuid to short 4-char ID", () => {
      expect(formatShortId("4f56b457-3e6c-4fd3-a216-1875f011dbb4")).toBe("#CV-4F56");
      expect(formatShortId("8f310000-0000-0000-0000-000000000000")).toBe("#CV-8F31");
    });
  });

  describe("formatItemTime", () => {
    it("formats today timestamp as HH:mm", () => {
      const now = new Date();
      now.setHours(10, 32, 0, 0);
      expect(formatItemTime(now.toISOString())).toBe("10:32");
    });
  });

  describe("groupConversations", () => {
    it("groups conversations into pinned, today, yesterday, last 7 days, and older", () => {
      const now = new Date();
      const todayDate = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 10, 0, 0);
      const yesterdayDate = new Date(todayDate.getTime() - 24 * 60 * 60 * 1000);
      const fourDaysAgo = new Date(todayDate.getTime() - 4 * 24 * 60 * 60 * 1000);
      const tenDaysAgo = new Date(todayDate.getTime() - 10 * 24 * 60 * 60 * 1000);

      const items: EnrichedConversation[] = [
        enrichConversation(
          {
            conversation_id: "c1",
            session_id: "s1",
            title: "Pinned chat",
            status: "ACTIVE",
            state: "ACTIVE",
            created_at: "2026-08-01T00:00:00Z",
            archived_at: null,
            assigned_advisor_id: null,
            last_activity_at: todayDate.toISOString(),
          },
          { isPinned: true },
        ),
        enrichConversation({
          conversation_id: "c2",
          session_id: "s2",
          title: "Today chat",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: todayDate.toISOString(),
        }),
        enrichConversation({
          conversation_id: "c3",
          session_id: "s3",
          title: "Yesterday chat",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: yesterdayDate.toISOString(),
        }),
        enrichConversation({
          conversation_id: "c4",
          session_id: "s4",
          title: "Last 7 days chat",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: fourDaysAgo.toISOString(),
        }),
        enrichConversation({
          conversation_id: "c5",
          session_id: "s5",
          title: "Older chat",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: tenDaysAgo.toISOString(),
        }),
      ];

      const groups = groupConversations(items);
      expect(groups.map((g) => g.key)).toEqual(["pinned", "today", "yesterday", "last7Days", "older"]);
      expect(groups.find((g) => g.key === "pinned")?.items[0].id).toBe("c1");
      expect(groups.find((g) => g.key === "today")?.items[0].id).toBe("c2");
      expect(groups.find((g) => g.key === "yesterday")?.items[0].id).toBe("c3");
      expect(groups.find((g) => g.key === "last7Days")?.items[0].id).toBe("c4");
      expect(groups.find((g) => g.key === "older")?.items[0].id).toBe("c5");
    });
  });

  describe("filterConversations", () => {
    it("filters conversations by keyword", () => {
      const items: EnrichedConversation[] = [
        enrichConversation({
          conversation_id: "c1",
          session_id: "s1",
          title: "Tư vấn VF 7",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: new Date().toISOString(),
        }),
        enrichConversation({
          conversation_id: "c2",
          session_id: "s2",
          title: "Tìm trạm sạc Hà Nội",
          status: "ACTIVE",
          state: "ACTIVE",
          created_at: "2026-08-01T00:00:00Z",
          archived_at: null,
          assigned_advisor_id: null,
          last_activity_at: new Date().toISOString(),
        }),
      ];

      expect(filterConversations(items, "VF 7").length).toBe(1);
      expect(filterConversations(items, "trạm sạc").length).toBe(1);
      expect(filterConversations(items, "không có").length).toBe(0);
    });
  });
});
