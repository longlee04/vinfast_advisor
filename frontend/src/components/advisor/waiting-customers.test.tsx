// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WaitingCustomers, isWaiting } from "@/components/advisor/waiting-customers";
import * as agentApi from "@/lib/api/agent";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/api/agent", () => ({ joinAdvisorConversation: vi.fn(), listAdvisorConversations: vi.fn() }));

function conv(id: string, overrides: Partial<agentApi.AdvisorConversationDetail>): agentApi.AdvisorConversationDetail {
  return {
    conversation_id: id,
    customer_id: `cust-${id}`,
    status: "ACTIVE",
    hitl_reasons: [],
    last_message_preview: "",
    last_activity_at: "2026-09-24T09:00:00Z",
    messages: [],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Khách đang chờ gặp tư vấn viên (plan §18)", () => {
  it("chỉ phiên chờ người thật, chưa đóng", () => {
    expect(isWaiting(conv("1", { status: "WAITING_ADVISOR" }))).toBe(true);
    expect(isWaiting(conv("2", { ownership: "PENDING_HANDOFF" }))).toBe(true);
    expect(isWaiting(conv("3", { ownership: "AI" }))).toBe(false);
    expect(isWaiting(conv("4", { status: "COMPLETED", ownership: "PENDING_HANDOFF" }))).toBe(false);
  });

  it("chờ lâu nhất lên đầu; Tiếp quản nhận phiên rồi vào chat; khách vãng lai không có link hồ sơ", async () => {
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: [
        conv("a", { ownership: "AI", customer_display: "Khách AI" }),
        conv("b", { status: "WAITING_ADVISOR", customer_display: "Khách Mới", last_activity_at: "2026-09-24T09:30:00Z" }),
        conv("c", { status: "WAITING_ADVISOR", customer_id: "anon-9", last_activity_at: "2026-09-24T08:00:00Z", last_message_preview: "cho gặp người thật" }),
      ],
    });
    vi.mocked(agentApi.joinAdvisorConversation).mockResolvedValue({ joined: true, conversation_id: "b" });

    await act(async () => {
      render(<WaitingCustomers />);
    });

    const section = screen.getByRole("region", { name: /Khách đang chờ gặp tư vấn viên \(2\)/ });
    const rows = within(section).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Khách vãng lai");
    expect(rows[0]).toHaveTextContent("cho gặp người thật");
    expect(within(rows[0]).queryByRole("link", { name: "Hồ sơ" })).not.toBeInTheDocument();
    expect(within(rows[1]).getByRole("link", { name: "Hồ sơ" })).toHaveAttribute("href", "/advisor/customers/from-session/b");
    expect(screen.queryByText("Khách AI")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tiếp quản Khách Mới" }));
    });
    expect(agentApi.joinAdvisorConversation).toHaveBeenCalledWith("b");
    expect(push).toHaveBeenCalledWith("/advisor/conversations/b");
  });

  it("không ai chờ thì không hiện gì", async () => {
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: [conv("a", { ownership: "AI" })] });
    const { container } = render(<WaitingCustomers />);
    await act(async () => undefined);
    expect(container).toBeEmptyDOMElement();
  });
});
