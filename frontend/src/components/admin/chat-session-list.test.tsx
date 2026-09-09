// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChatSessionList } from "@/components/admin/chat-session-list";
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
}));

const STORAGE_KEY = "p150.agent-session";

function seedLiveSession(id = "live-1234"): void {
  window.sessionStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      sessionId: id,
      messages: [
        { role: "user", text: "Tôi muốn mua xe điện 5 chỗ" },
        { role: "assistant", text: "VF 6 và VF 7 phù hợp với nhu cầu của anh" },
      ],
      phase: "chatting",
      deliveredReviewIds: [],
    }),
  );
}

describe("ChatSessionList & Dynamic KPIs", () => {
  beforeEach(() => {
    cleanup();
    window.sessionStorage.clear();
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: [] });
  });

  function getKpiCards() {
    const kpiGrid = document.querySelector(".chat-kpi-grid") as HTMLElement;
    const totalCard = within(kpiGrid).getByText("Tổng phiên").closest("article")!;
    const activeCard = within(kpiGrid).getByText("Đang hoạt động").closest("article")!;
    const waitingCard = within(kpiGrid).getByText("Chờ Advisor").closest("article")!;
    return { totalCard, activeCard, waitingCard };
  }

  it("1. Empty state: KPI hiển thị 0/0/0, không còn thẻ Lỗi AI hôm nay và không còn dữ liệu mock", async () => {
    await act(async () => {
      render(
        <AuthProvider>
          <ChatSessionList />
        </AuthProvider>,
      );
    });

    const { totalCard, activeCard, waitingCard } = getKpiCards();

    expect(totalCard).toBeInTheDocument();
    expect(activeCard).toBeInTheDocument();
    expect(waitingCard).toBeInTheDocument();

    expect(within(totalCard).getByText("0")).toBeInTheDocument();
    expect(within(activeCard).getByText("0")).toBeInTheDocument();
    expect(within(waitingCard).getByText("0")).toBeInTheDocument();

    // Không còn thẻ Lỗi AI hôm nay
    expect(screen.queryByText("Lỗi AI hôm nay")).not.toBeInTheDocument();

    // Không còn mock data cũ
    expect(screen.queryByText("1.284")).not.toBeInTheDocument();
    expect(screen.queryByText("customer.101@example.com")).not.toBeInTheDocument();
    expect(screen.queryByText("d79b229c")).not.toBeInTheDocument();

    // Hiển thị trạng thái rỗng
    expect(screen.getByText("Không tìm thấy phiên chat")).toBeInTheDocument();
    expect(screen.getByText("Chưa có phiên chat nào")).toBeInTheDocument();
  });

  it("2. Live session: ghi nhận 1 phiên live, cập nhật KPI và hiển thị đúng 1 dòng dữ liệu", async () => {
    seedLiveSession("live-1234");

    await act(async () => {
      render(
        <AuthProvider>
          <ChatSessionList />
        </AuthProvider>,
      );
    });

    // 1 header row + 1 data row = 2 rows
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(2);

    const dataRow = rows[1];
    expect(within(dataRow).getByText("live-1234")).toBeInTheDocument();
    expect(screen.getAllByText("Trực tiếp").length).toBeGreaterThan(0);
    expect(screen.getByText("Khách đang tư vấn")).toBeInTheDocument();

    // KPI biến đếm động
    const { totalCard, activeCard, waitingCard } = getKpiCards();

    expect(within(totalCard).getByText("1")).toBeInTheDocument();
    expect(within(activeCard).getByText("1")).toBeInTheDocument();
    expect(within(waitingCard).getByText("0")).toBeInTheDocument();
  });

  it("3. Backend sessions: tính toán đúng số lượng KPI theo trạng thái", async () => {
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: [
        {
          conversation_id: "sess-01",
          customer_id: "cust-01@gmail.com",
          status: "ACTIVE",
          hitl_reasons: [],
          last_message_preview: "Xin chào",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
        {
          conversation_id: "sess-02",
          customer_id: "cust-02@gmail.com",
          status: "WAITING_ADVISOR",
          hitl_reasons: [],
          last_message_preview: "Cần gặp tư vấn viên",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
        {
          conversation_id: "sess-03",
          customer_id: "cust-03@gmail.com",
          status: "CLOSED",
          hitl_reasons: [],
          last_message_preview: "Cảm ơn",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
      ],
    });

    await act(async () => {
      render(
        <AuthProvider>
          <ChatSessionList />
        </AuthProvider>,
      );
    });

    const rows = screen.getAllByRole("row");
    // 1 header + 3 data rows
    expect(rows).toHaveLength(4);

    // Kiểm tra các session ID xuất hiện
    expect(screen.getByText("sess-01")).toBeInTheDocument();
    expect(screen.getByText("sess-02")).toBeInTheDocument();
    expect(screen.getByText("sess-03")).toBeInTheDocument();

    const { totalCard, activeCard, waitingCard } = getKpiCards();

    expect(within(totalCard).getByText("3")).toBeInTheDocument();
    expect(within(activeCard).getByText("1")).toBeInTheDocument();
    expect(within(waitingCard).getByText("1")).toBeInTheDocument();
  });

  it("4. Deduplication: Live Session và Backend Session trùng ID không bị nhân đôi", async () => {
    seedLiveSession("sess-duplicate");

    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: [
        {
          conversation_id: "sess-duplicate",
          customer_id: "cust-dup@gmail.com",
          status: "ACTIVE",
          hitl_reasons: [],
          last_message_preview: "Hello",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
        {
          conversation_id: "sess-other",
          customer_id: "cust-other@gmail.com",
          status: "CLOSED",
          hitl_reasons: [],
          last_message_preview: "Done",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
      ],
    });

    await act(async () => {
      render(
        <AuthProvider>
          <ChatSessionList />
        </AuthProvider>,
      );
    });

    // 1 header + 2 unique sessions = 3 rows
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(3);

    // sess-duplicate chỉ xuất hiện 1 lần duy nhất trong bảng
    expect(screen.getAllByText("sess-duplicate")).toHaveLength(1);

    const { totalCard, activeCard, waitingCard } = getKpiCards();
    expect(within(totalCard).getByText("2")).toBeInTheDocument();
    expect(within(activeCard).getByText("1")).toBeInTheDocument();
    expect(within(waitingCard).getByText("0")).toBeInTheDocument();
  });

  it("5. KPI Independence: Tìm kiếm trong bảng lọc dữ liệu nhưng không thay đổi KPI", async () => {
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({
      items: [
        {
          conversation_id: "sess-vinfast-1",
          customer_id: "customer.alice@vinfast.vn",
          status: "ACTIVE",
          hitl_reasons: [],
          last_message_preview: "Tư vấn xe",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
        {
          conversation_id: "sess-vinfast-2",
          customer_id: "customer.bob@vinfast.vn",
          status: "ACTIVE",
          hitl_reasons: [],
          last_message_preview: "Báo giá",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
        {
          conversation_id: "sess-vinfast-3",
          customer_id: "customer.charlie@gmail.com",
          status: "WAITING_ADVISOR",
          hitl_reasons: [],
          last_message_preview: "Cần gặp nhân viên",
          last_activity_at: new Date().toISOString(),
          messages: [],
        },
      ],
    });

    await act(async () => {
      render(
        <AuthProvider>
          <ChatSessionList />
        </AuthProvider>,
      );
    });

    // Ban đầu có 3 sessions -> 4 rows (1 header + 3 data)
    expect(screen.getAllByRole("row")).toHaveLength(4);

    // Gõ tìm kiếm "charlie"
    const searchInput = screen.getByPlaceholderText("Tìm customer / session / trace...");
    await act(async () => {
      fireEvent.change(searchInput, { target: { value: "charlie" } });
    });

    // Bảng chỉ còn 1 kết quả (1 header + 1 data row)
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByText("sess-vinfast-3")).toBeInTheDocument();
    expect(screen.queryByText("sess-vinfast-1")).not.toBeInTheDocument();

    // KPI vẫn giữ nguyên số liệu toàn cục
    const { totalCard, activeCard, waitingCard } = getKpiCards();

    expect(within(totalCard).getByText("3")).toBeInTheDocument();
    expect(within(activeCard).getByText("2")).toBeInTheDocument();
    expect(within(waitingCard).getByText("1")).toBeInTheDocument();
  });
});