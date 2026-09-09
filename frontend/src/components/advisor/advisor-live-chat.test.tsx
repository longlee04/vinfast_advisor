// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdvisorLiveChat } from "@/components/advisor/advisor-live-chat";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
}));

const {
  fetchAdvisorConversation,
  sendAdvisorMessage,
  closeAdvisorConversation,
  deleteAdvisorConversation,
  handoffAdvisorConversation,
} = vi.hoisted(() => ({
  fetchAdvisorConversation: vi.fn().mockResolvedValue({
    session_id: "conversation-12345678",
    customer_id: "customer-1",
    status: "ACTIVE",
    messages: [
      { message_id: "m1", role: "USER", content: "Tôi quan tâm VF 7", created_at: new Date().toISOString() },
    ],
  }),
  sendAdvisorMessage: vi.fn().mockResolvedValue({ message_id: "m2" }),
  closeAdvisorConversation: vi.fn().mockResolvedValue({ closed: true }),
  deleteAdvisorConversation: vi.fn().mockResolvedValue({ deleted: true }),
  handoffAdvisorConversation: vi.fn().mockResolvedValue({ success: true }),
}));

vi.mock("@/lib/api/agent", () => ({
  fetchAdvisorConversation,
  sendAdvisorMessage,
  closeAdvisorConversation,
  deleteAdvisorConversation,
  handoffAdvisorConversation,
}));

describe("AdvisorLiveChat", () => {
  beforeEach(() => {
    Element.prototype.scrollTo = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
  });
  afterEach(() => {
    cleanup();
  });
  it("sends an advisor message and closes the live session", async () => {
    const user = userEvent.setup();
    render(<AdvisorLiveChat conversationId="conversation-12345678" />);

    await user.type(screen.getByRole("textbox", { name: "Tin nhắn gửi khách hàng" }), "Tôi sẽ kiểm tra VF 7 Plus.");
    await user.click(screen.getByRole("button", { name: "Gửi tin nhắn" }));

    expect(await screen.findByText("Tôi sẽ kiểm tra VF 7 Plus.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kết thúc" }));
    expect(screen.getByRole("dialog")).toHaveTextContent("Bạn có chắc muốn kết thúc phiên tư vấn?");
    await user.click(screen.getByRole("button", { name: "Kết thúc phiên" }));

    await waitFor(() => {
      expect(screen.getByText("Đã kết thúc")).toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: "Tin nhắn gửi khách hàng" })).toBeDisabled();
    });
  });
});
