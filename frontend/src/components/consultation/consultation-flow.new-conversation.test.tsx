// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { AgentSessionProvider } from "@/store/agent-session";

const { sendTurn, fetchDeliveries, getSearchParams } = vi.hoisted(() => ({
  sendTurn: vi.fn(),
  fetchDeliveries: vi.fn(),
  getSearchParams: vi.fn(() => new URLSearchParams()),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/consultation",
  useSearchParams: () => getSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return {
    ...actual,
    sendTurn,
    fetchDeliveries,
    fetchCustomerConversations: vi.fn().mockResolvedValue([]),
    fetchAllConversationMessages: vi.fn().mockResolvedValue([]),
    fetchConversationMessages: vi.fn().mockResolvedValue({ items: [] }),
    turnEventsUrl: (sessionId: string) => `/events/${sessionId}`,
  };
});

class FakeEventSource {
  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  close(): void {}
}

const OLD_ID = "aaaaaaaa-1111-2222-3333-444444444444";
const OLD_MESSAGE = "Đây là hội thoại cũ của khách";

/** Phiên CŨ đã lưu, đúng hình `writeStoredSession` ghi: cả khoá chung lẫn khoá theo id. */
function storeOldSession(): void {
  const stored = JSON.stringify({
    sessionId: OLD_ID,
    phase: "idle",
    messages: [{ role: "assistant", text: OLD_MESSAGE }],
    panel: { open: false, navigate: null, selectedShowroomId: null },
    pendingSubmission: null,
    errorMessage: "",
    authRequired: false,
  });
  sessionStorage.setItem("p150.agent-session", stored);
  sessionStorage.setItem(`p150.agent-session.${OLD_ID}`, stored);
}

describe("Nút tạo cuộc trò chuyện mới", () => {
  beforeEach(() => {
    sessionStorage.clear();
    fetchDeliveries.mockResolvedValue({ items: [] });
    getSearchParams.mockReturnValue(new URLSearchParams(`conversation=${OLD_ID}`));
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "bbbbbbbb-5555-6666-7777-888888888888" });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  // Đo trên máy 2026-09-23 (Sếp báo): đang ở giữa một hội thoại, bấm "Cuộc trò
  // chuyện mới" hay dấu "+" thì KHÔNG có gì xảy ra. `handleNewConversation` có
  // chạy, nhưng `AgentSessionProvider` thấy `state.sessionId` vừa đổi nên chạy
  // lại hiệu ứng khôi phục, đọc `p150.agent-session.<id cũ>` (khoá này KHÔNG bị
  // xoá) và dispatch `restored` — hội thoại cũ quay về ngay lập tức.
  it("xoá sạch hội thoại cũ khi khách ở trong một hội thoại đã lưu", async () => {
    const user = userEvent.setup();
    storeOldSession();

    render(
      <AgentSessionProvider conversationId={OLD_ID}>
        <ConsultationFlow initialConversationId={OLD_ID} />
      </AgentSessionProvider>,
    );

    await screen.findByText(OLD_MESSAGE);
    await user.click(screen.getByLabelText("Bắt đầu cuộc trò chuyện mới"));

    await waitFor(() => expect(screen.queryByText(OLD_MESSAGE)).not.toBeInTheDocument());
    // Và không quay lại sau một nhịp render nữa.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText(OLD_MESSAGE)).not.toBeInTheDocument();
    expect(sessionStorage.getItem(`p150.agent-session.${OLD_ID}`)).toBeNull();
  });

  it("dấu + trên đầu danh sách cũng bắt đầu hội thoại mới", async () => {
    const user = userEvent.setup();
    storeOldSession();

    render(
      <AgentSessionProvider conversationId={OLD_ID}>
        <ConsultationFlow initialConversationId={OLD_ID} />
      </AgentSessionProvider>,
    );

    await screen.findByText(OLD_MESSAGE);
    const plusButtons = screen.getAllByLabelText("Tạo cuộc trò chuyện mới");
    await user.click(plusButtons[0]);

    await waitFor(() => expect(screen.queryByText(OLD_MESSAGE)).not.toBeInTheDocument());
  });
});
