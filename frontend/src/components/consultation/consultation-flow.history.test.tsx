// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { AgentSessionProvider } from "@/store/agent-session";

const OLD_ID = "22222222-2222-2222-2222-222222222222";

const { fetchAllConversationMessages, getSearchParams } = vi.hoisted(() => ({
  fetchAllConversationMessages: vi.fn(),
  getSearchParams: vi.fn(() => new URLSearchParams(`conversation=${"22222222-2222-2222-2222-222222222222"}`)),
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
    fetchAllConversationMessages,
    fetchDeliveries: vi.fn().mockResolvedValue({ items: [] }),
    sendTurn: vi.fn(),
    fetchCustomerConversations: vi.fn().mockResolvedValue([]),
    fetchConversations: vi.fn().mockResolvedValue({ items: [] }),
    turnEventsUrl: (sessionId: string) => `/events/${sessionId}`,
  };
});

class FakeEventSource {
  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  close(): void {}
}

describe("mở lại một hội thoại cũ", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
    fetchAllConversationMessages.mockResolvedValue([
      { message_id: "m1", role: "USER", content: "anh muốn tư vấn", created_at: "2026-08-01T00:00:00Z" },
      { message_id: "m2", role: "ASSISTANT", content: "Dạ ô tô điện hay xe máy điện ạ?", created_at: "2026-08-01T00:00:01Z" },
    ]);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("hiện lại đúng nội dung cũ chứ không phải khung chat trống", async () => {
    render(
      <AgentSessionProvider>
        <ConsultationFlow initialConversationId={OLD_ID} />
      </AgentSessionProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("anh muốn tư vấn")).toBeInTheDocument();
    });
    expect(screen.getByText("Dạ ô tô điện hay xe máy điện ạ?")).toBeInTheDocument();
  });
});
