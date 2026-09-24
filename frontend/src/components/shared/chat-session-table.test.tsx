// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSessionTable, computeChatSessionKpis, toChatSessionRow } from "@/components/shared/chat-session-table";
import type { AdvisorConversationDetail } from "@/lib/api/agent";
import * as agentApi from "@/lib/api/agent";
import { AuthProvider } from "@/store/auth-store";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api/agent", () => ({
  listAdvisorConversations: vi.fn(),
  fetchAdvisorConversation: vi.fn(),
  closeAdvisorConversation: vi.fn(),
}));

function item(overrides: Partial<AdvisorConversationDetail>): AdvisorConversationDetail {
  return {
    conversation_id: "sess-0000000000001",
    customer_id: "cust-1",
    customer_display: "Khách Một",
    status: "ACTIVE",
    hitl_reasons: [],
    last_message_preview: "",
    last_activity_at: "2026-09-24T09:00:00Z",
    assigned_advisor_id: null,
    messages: [],
    ...overrides,
  };
}

const ITEMS: AdvisorConversationDetail[] = [
  item({ conversation_id: "sess-aaaaaaaaaaaa1", customer_display: "An", assigned_advisor_id: "adv-1" }),
  item({ conversation_id: "sess-bbbbbbbbbbbb2", customer_display: "Bình", status: "WAITING_ADVISOR", assigned_advisor_id: "adv-2" }),
  item({ conversation_id: "sess-cccccccccccc3", customer_display: "Chi", status: "COMPLETED", assigned_advisor_id: "adv-1" }),
];

async function renderTable(scope: "mine" | "all") {
  await act(async () => {
    render(
      <AuthProvider>
        <ChatSessionTable scope={scope} />
      </AuthProvider>,
    );
  });
}

describe("ChatSessionTable", () => {
  beforeEach(() => {
    cleanup();
    window.sessionStorage.clear();
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: ITEMS });
  });

  it("scope=all có cột Advisor, bộ lọc Advisor và link sang trang trace; không có nút Đóng", async () => {
    await renderTable("all");

    expect(screen.getByRole("columnheader", { name: "Advisor" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Advisor" })).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /Xem trace/ });
    expect(links[0]).toHaveAttribute("href", "/admin/chat-sessions/sess-aaaaaaaaaaaa1");
    expect(screen.queryByRole("button", { name: /^Đóng$/ })).not.toBeInTheDocument();
  });

  it("scope=mine không lộ cột/bộ lọc Advisor, link vào phòng chat và có nút Đóng cho phiên chưa đóng", async () => {
    await renderTable("mine");

    expect(screen.queryByRole("columnheader", { name: "Advisor" })).not.toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Advisor" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Vào chat/ })[0]).toHaveAttribute(
      "href",
      "/advisor/conversations/sess-aaaaaaaaaaaa1",
    );
    // 2 phiên chưa đóng → 2 nút Đóng; phiên COMPLETED chỉ có "Xem lại".
    expect(screen.getAllByRole("button", { name: /^Đóng$/ })).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Xem lại/ })).toBeInTheDocument();
  });

  it("scope=all lọc theo Advisor mà KPI vẫn tính trên toàn bộ phiên", async () => {
    await renderTable("all");

    await act(async () => {
      fireEvent.change(screen.getByRole("combobox", { name: "Advisor" }), { target: { value: "adv-2" } });
    });

    const body = screen.getAllByRole("rowgroup")[1];
    expect(within(body).getAllByRole("row")).toHaveLength(1);
    expect(within(body).getByText("Bình")).toBeInTheDocument();
    const totalCard = within(document.querySelector(".chat-kpi-grid") as HTMLElement).getByText("Tổng phiên").closest("article")!;
    expect(within(totalCard).getByText("3")).toBeInTheDocument();
  });

  it("không còn nút đăng nhập nhanh bằng mật khẩu gõ sẵn — chỉ link sang trang đăng nhập nhân sự", async () => {
    await renderTable("mine");

    expect(screen.queryByText(/advisor@gmail\.com/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Đăng nhập/ })).toHaveAttribute("href", "/staff-login");
  });
});

describe("chuẩn hoá dòng và KPI", () => {
  it("gộp COMPLETED/CLOSED về CLOSED và đặt tên khách vãng lai", () => {
    expect(toChatSessionRow(item({ status: "COMPLETED" })).status).toBe("CLOSED");
    expect(toChatSessionRow(item({ status: "closed" })).status).toBe("CLOSED");
    expect(toChatSessionRow(item({ customer_id: "anon-9", customer_display: null })).customerName).toBe("Khách vãng lai");
  });

  it("'Đang hoạt động' giữ nghĩa riêng từng màn: TVV tính cả phiên chờ, Admin thì không", () => {
    const rows = ITEMS.map(toChatSessionRow);
    expect(computeChatSessionKpis(rows, "mine")).toEqual({ total: 3, active: 2, waiting: 1, closed: 1 });
    expect(computeChatSessionKpis(rows, "all")).toEqual({ total: 3, active: 1, waiting: 1, closed: 1 });
  });
});
