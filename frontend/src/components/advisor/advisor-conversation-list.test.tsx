// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdvisorConversationList } from "@/components/advisor/advisor-conversation-list";
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

describe("AdvisorConversationList Component", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: [] });
    vi.mocked(agentApi.fetchAdvisorConversation).mockResolvedValue({
      conversation_id: "preview-1",
      customer_id: "cust-01",
      status: "ACTIVE",
      hitl_reasons: [],
      last_message_preview: "",
      messages: [],
      last_activity_at: "2026-08-24T10:00:00Z",
    });
    vi.mocked(agentApi.closeAdvisorConversation).mockResolvedValue({ closed: true });
  });

  it("1. Empty state: KPIs hiển thị 0 và thông báo không tìm thấy phiên", async () => {
    await act(async () => {
      render(
        <AuthProvider>
          <AdvisorConversationList />
        </AuthProvider>,
      );
    });

    const kpiGrid = document.querySelector(".chat-kpi-grid") as HTMLElement;
    expect(within(kpiGrid).getByText("Tổng phiên")).toBeInTheDocument();
    expect(screen.getByText("Không tìm thấy phiên chat nào phù hợp.")).toBeInTheDocument();
  });

  it("2. Render đúng danh sách phiên và tính toán đúng KPIs", async () => {
    const mockItems: AdvisorConversationDetail[] = [
      {
        conversation_id: "session-1",
        customer_id: "cust-01",
        customer_display: "Nguyễn Văn A",
        status: "ACTIVE",
        hitl_reasons: [],
        last_message_preview: "Tư vấn xe VF 8",
        last_activity_at: "2026-08-24T10:00:00Z",
        assigned_advisor_id: "advisor@gmail.com",
        messages: [],
      },
      {
        conversation_id: "session-2",
        customer_id: "cust-02",
        customer_display: "Trần Thị B",
        status: "WAITING_ADVISOR",
        hitl_reasons: ["Báo giá đặc biệt"],
        last_message_preview: "Cần hỗ trợ trả góp",
        last_activity_at: "2026-08-24T11:00:00Z",
        assigned_advisor_id: "advisor@gmail.com",
        messages: [],
      },
      {
        conversation_id: "session-3",
        customer_id: "cust-03",
        customer_display: "Lê Văn C",
        status: "COMPLETED",
        hitl_reasons: [],
        last_message_preview: "Cảm ơn đã tư vấn",
        last_activity_at: "2026-08-24T09:00:00Z",
        assigned_advisor_id: "advisor@gmail.com",
        messages: [],
      },
    ];
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: mockItems,
    });

    await act(async () => {
      render(
        <AuthProvider>
          <AdvisorConversationList />
        </AuthProvider>,
      );
    });

    expect(screen.getByText("Nguyễn Văn A")).toBeInTheDocument();
    expect(screen.getByText("Trần Thị B")).toBeInTheDocument();
    expect(screen.getByText("Lê Văn C")).toBeInTheDocument();

    const kpiGrid = document.querySelector(".chat-kpi-grid") as HTMLElement;
    const totalCard = within(kpiGrid).getByText("Tổng phiên").closest("article")!;
    const activeCard = within(kpiGrid).getByText("Đang hoạt động").closest("article")!;
    const waitingCard = within(kpiGrid).getByText("Cần bạn xử lý").closest("article")!;

    expect(within(totalCard).getByText("3")).toBeInTheDocument();
    expect(within(activeCard).getByText("2")).toBeInTheDocument();
    expect(within(waitingCard).getByText("1")).toBeInTheDocument();
  });

  it("3. Click KPI card để lọc nhanh trạng thái và tìm kiếm", async () => {
    const mockItems: AdvisorConversationDetail[] = [
      {
        conversation_id: "session-active",
        customer_id: "cust-active",
        customer_display: "Khách Đang Chat",
        status: "ACTIVE",
        hitl_reasons: [],
        last_message_preview: "Hỏi giá VF 3",
        last_activity_at: "2026-08-24T10:00:00Z",
        messages: [],
      },
      {
        conversation_id: "session-waiting",
        customer_id: "cust-waiting",
        customer_display: "Khách Chờ Xử Lý",
        status: "WAITING_ADVISOR",
        hitl_reasons: ["Cần duyệt ưu đãi"],
        last_message_preview: "Hỏi chính sách cọc",
        last_activity_at: "2026-08-24T10:30:00Z",
        messages: [],
      },
      {
        conversation_id: "session-closed",
        customer_id: "cust-closed",
        customer_display: "Khách Đã Xong",
        status: "COMPLETED",
        hitl_reasons: [],
        last_message_preview: "Đã chốt cọc",
        last_activity_at: "2026-08-24T08:00:00Z",
        messages: [],
      },
    ];
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: mockItems,
    });

    await act(async () => {
      render(
        <AuthProvider>
          <AdvisorConversationList />
        </AuthProvider>,
      );
    });

    expect(screen.getByText("Khách Đang Chat")).toBeInTheDocument();
    expect(screen.getByText("Khách Chờ Xử Lý")).toBeInTheDocument();
    expect(screen.getByText("Khách Đã Xong")).toBeInTheDocument();

    // Click KPI "Cần bạn xử lý"
    const kpiGrid = document.querySelector(".chat-kpi-grid") as HTMLElement;
    const waitingCard = within(kpiGrid).getByText("Cần bạn xử lý").closest("article")!;
    await act(async () => {
      fireEvent.click(waitingCard);
    });

    expect(screen.queryByText("Khách Đang Chat")).not.toBeInTheDocument();
    expect(screen.getByText("Khách Chờ Xử Lý")).toBeInTheDocument();
    expect(screen.queryByText("Khách Đã Xong")).not.toBeInTheDocument();

    // Tìm kiếm text
    const totalCard = within(kpiGrid).getByText("Tổng phiên").closest("article")!;
    await act(async () => {
      fireEvent.click(totalCard);
    });
    const searchInput = screen.getByPlaceholderText("Tìm mã phiên, khách hàng...");
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "VF 3" } });
    });

    expect(screen.getByText("Khách Đang Chat")).toBeInTheDocument();
    expect(screen.queryByText("Khách Chờ Xử Lý")).not.toBeInTheDocument();
  });

  it("4. Thao tác đóng phiên: Mở popup xác nhận với thông tin an toàn và gọi closeAdvisorConversation", async () => {
    const mockItems: AdvisorConversationDetail[] = [
      {
        conversation_id: "session-to-close-1234",
        customer_id: "cust-01",
        customer_display: "Khách Cần Đóng",
        status: "ACTIVE",
        hitl_reasons: [],
        last_message_preview: "Đã tư vấn xong",
        last_activity_at: "2026-08-24T10:00:00Z",
        messages: [],
      },
    ];
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: mockItems,
    });

    await act(async () => {
      render(
        <AuthProvider>
          <AdvisorConversationList />
        </AuthProvider>,
      );
    });

    const closeBtn = screen.getByRole("button", { name: /^Đóng$/i });
    await act(async () => {
      fireEvent.click(closeBtn);
    });

    expect(screen.getByText(/Đóng phiên tư vấn này\?/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", { name: /Xác nhận kết thúc/i });
    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    expect(agentApi.closeAdvisorConversation).toHaveBeenCalledWith("session-to-close-1234");
  });
});
