// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";

import { getLiveChatSession } from "@/lib/live-chat-session";

const STORAGE_KEY = "p150.agent-session";

function seedStoredSession(sessionId: string, texts: Array<{ role: "user" | "assistant"; text: string }>): void {
  window.sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({ sessionId, messages: texts, phase: "chatting", deliveredReviewIds: [] }),
  );
}

describe("getLiveChatSession", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });

  it("trả null khi chưa có phiên hoạt động", () => {
    expect(getLiveChatSession(undefined)).toBeNull();
  });

  it("dựng phiên live từ phiên customer đang hoạt động, đủ tin nhắn và số lượt AI", () => {
    seedStoredSession("live-abc", [
      { role: "user", text: "Tôi muốn mua VF 7" },
      { role: "assistant", text: "VF 7 phù hợp với nhu cầu của anh" },
    ]);

    const session = getLiveChatSession("khach@demo.vinfast.vn");

    expect(session).not.toBeNull();
    expect(session?.id).toBe("live-abc");
    expect(session?.status).toBe("ACTIVE");
    expect(session?.messageCount).toBe(2);
    expect(session?.aiTurnCount).toBe(1);
    expect(session?.traceCount).toBe(1);
    expect(session?.traces).toHaveLength(1);
    expect(session?.customer.email).toBe("khach@demo.vinfast.vn");
    expect(session?.messages.map((message) => message.role)).toEqual(["customer", "ai"]);
    expect(session?.messages[0].content).toBe("Tôi muốn mua VF 7");
    expect(session?.startedAt).toBe("Đang diễn ra");
    expect(session?.lastActivityAt).toBe("Trực tiếp");
  });

  it("trả null khi phiên lưu nhưng chưa có tin nhắn nào", () => {
    seedStoredSession("live-empty", []);

    expect(getLiveChatSession("a@a.vn")).toBeNull();
  });

  it("cache trả cùng tham chiếu khi dữ liệu không đổi, đổi email thì tính lại", () => {
    seedStoredSession("live-1", [{ role: "user", text: "Xin chào" }]);

    expect(getLiveChatSession("a@a.vn")).toBe(getLiveChatSession("a@a.vn"));
    expect(getLiveChatSession("a@a.vn")).not.toBe(getLiveChatSession("b@b.vn"));
    expect(getLiveChatSession("b@b.vn")?.customer.email).toBe("b@b.vn");
  });

  it("dùng email thay thế khi chưa đăng nhập", () => {
    seedStoredSession("live-2", [{ role: "assistant", text: "Chào anh" }]);

    expect(getLiveChatSession(undefined)?.customer.email).toBe("khach@demo.vinfast.vn");
  });
});