// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerProfilePage } from "@/components/customer360/customer-profile-page";
import * as agentApi from "@/lib/api/agent";
import * as assignmentsApi from "@/lib/api/assignments";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api/agent", () => ({
  listAdvisorConversations: vi.fn(),
  fetchCustomer360Meta: vi.fn(),
  fetchCustomerOverview: vi.fn(),
  moveSessionOpportunity: vi.fn(),
  sendInsightFeedback: vi.fn(),
}));
vi.mock("@/lib/api/assignments", () => ({
  fetchAdvisorCustomers: vi.fn(),
  fetchAssignmentHistory: vi.fn(),
  fetchTestDriveBookings: vi.fn(),
}));

const CONVERSATIONS = [
  {
    conversation_id: "11111111-aaaa-bbbb-cccc-000000000001",
    customer_id: "cust-1",
    customer_display: "Nguyễn An",
    status: "WAITING_ADVISOR",
    hitl_reasons: [],
    last_message_preview: "Cho em gặp tư vấn viên",
    last_activity_at: "2026-09-24T09:00:00Z",
    messages: [],
    slots: { vehicle_type: "CAR", budget_stated_vnd: 800_000_000 },
  },
  {
    conversation_id: "11111111-aaaa-bbbb-cccc-000000000002",
    customer_id: "cust-1",
    customer_display: "Nguyễn An",
    status: "COMPLETED",
    hitl_reasons: [],
    last_message_preview: "Hỏi bảo hành pin",
    last_activity_at: "2026-09-20T09:00:00Z",
    messages: [],
  },
];

async function renderPage(role: "advisor" | "admin") {
  await act(async () => {
    render(<CustomerProfilePage customerId="cust-1" readOnly={role === "admin"} role={role} />);
  });
}

describe("CustomerProfilePage", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(agentApi.fetchCustomer360Meta).mockResolvedValue({ enabled: { ui: false, attach: false, extractor: false } });
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: CONVERSATIONS });
    vi.mocked(assignmentsApi.fetchTestDriveBookings).mockResolvedValue([
      {
        booking_id: "b1",
        customer_id: "cust-1",
        vehicle_id: "v1",
        vehicle_name: "VinFast VF 6",
        showroom: "Showroom Long Biên",
        scheduled_at: "2026-09-28T02:00:00Z",
        status: "REQUESTED",
        created_at: "2026-09-24T09:00:00Z",
      },
      { booking_id: "b2", customer_id: "cust-other", vehicle_id: "v2", showroom: "X", scheduled_at: "2026-09-28T02:00:00Z", status: "REQUESTED", created_at: "2026-09-24T09:00:00Z" },
    ]);
    vi.mocked(assignmentsApi.fetchAdvisorCustomers).mockResolvedValue({
      items: [
        {
          customer_id: "cust-1",
          advisor_id: "adv-1",
          assigned_at: "2026-09-01T00:00:00Z",
          status: "ACTIVE",
          profile_payload: { name: "Nguyễn An", phone: "0912***678" },
          active_conversations_count: 2,
        },
      ],
    });
    vi.mocked(assignmentsApi.fetchAssignmentHistory).mockResolvedValue({
      customer_id: "cust-1",
      items: [{ assignment_id: "a1", advisor_id: "adv-1", assigned_by: "admin", status: "ACTIVE", assigned_at: "2026-09-01T00:00:00Z" }],
    });
  });

  it("TVV: đầu hồ sơ, nút Vào chat/Tiếp quản trỏ vào phiên đang chờ, tab Phiên chat và Lái thử lọc đúng khách", async () => {
    await renderPage("advisor");

    expect(screen.getByText("Nguyễn An")).toBeInTheDocument();
    expect(screen.getByText("0912***678")).toBeInTheDocument();
    const waiting = `/advisor/conversations/${CONVERSATIONS[0].conversation_id}`;
    expect(screen.getByRole("link", { name: /Vào chat/ })).toHaveAttribute("href", waiting);
    expect(screen.getByRole("link", { name: /Tiếp quản/ })).toHaveAttribute("href", waiting);
    // Tổng quan: nhu cầu từ slot phiên gần nhất.
    expect(screen.getByText("800 triệu")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(2);

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Lái thử/ }));
    });
    expect(screen.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(screen.queryByText("cust-other")).not.toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("Admin (chỉ xem): không có nút thao tác, chỉ 'Phân công lại'; phiên mở sang trang trace", async () => {
    await renderPage("admin");

    expect(screen.queryByRole("link", { name: /Vào chat/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Tiếp quản/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Phân công lại/ })).toHaveAttribute("href", "/admin/assignments?customer=cust-1");
    expect(assignmentsApi.fetchAdvisorCustomers).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    expect(screen.getAllByRole("link", { name: /Xem/ })[0]).toHaveAttribute(
      "href",
      `/admin/chat-sessions/${CONVERSATIONS[0].conversation_id}`,
    );
  });

  it("TVV mở hồ sơ khách ngoài phạm vi: báo không có quyền, không dựng trang rỗng", async () => {
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: [] });
    vi.mocked(assignmentsApi.fetchAdvisorCustomers).mockResolvedValue({ items: [] });

    await renderPage("advisor");

    expect(screen.getByRole("alert")).toHaveTextContent("Không xem được hồ sơ này");
  });

  it("Cờ Customer 360 bật: MỘT lần gọi /overview — cơ hội có giai đoạn, độ nóng, gợi ý, việc cần làm; TVV tách phiên được", async () => {
    vi.mocked(agentApi.fetchCustomer360Meta).mockResolvedValue({ enabled: { ui: true, attach: true, extractor: true } });
    vi.mocked(agentApi.fetchCustomerOverview).mockResolvedValue({
      customer: {
        customer_id: "cust-1",
        display_name: "Nguyễn An",
        phone_masked: "0912***678",
        phone: "0912345678",
        assigned_advisor_id: "adv-1",
        heat_band: "HOT",
        heat_score: 70,
        sessions_count: 1,
        last_seen_at: "2026-09-24T09:00:00Z",
        fields: {},
      },
      opportunities: [
        {
          opportunity_id: "O1",
          vehicle_type: "CAR",
          buyer_for: "SELF",
          status: "OPEN",
          stage: "QUOTE",
          heat_score: 70,
          heat_band: "HOT",
          heat_breakdown: [{ code: "H1", points: 25, detail: "QUOTE" }],
          needs: {
            known: [{ slot: "budget_max_vnd", value: "850000000", history: [{ value: "700000000", at: "2026-09-20" }] }],
            missing: ["passenger_count"],
            evaded: ["passenger_count"],
          },
          barriers: [{ code: "PRICE", source: "BOTTLENECK", evidence_quote: "đắt quá", turn_index: 3, session_id: "s1", status: "CORRECT" }],
          insights: [
            { insight_id: "i1", field: "purchase_timeframe", value: "tháng này", source: "LLM", evidence_quote: "tháng này em chốt", at: "2026-09-24", history: [] },
          ],
          opening_hint: "Khách còn cân nhắc về giá — mở lời bằng tổng chi phí lăn bánh.",
          next_actions: [{ code: "REVIEW_ATTACH", label: "Xác nhận phiên thuộc nhu cầu nào (Tách/Gộp)" }],
        },
      ],
      sessions: [
        {
          session_id: "11111111-aaaa-bbbb-cccc-000000000009",
          started_at: null,
          last_activity_at: "2026-09-24T09:00:00Z",
          status: "ACTIVE",
          kind: "SALES",
          opportunity_id: "O1",
          needs_review: true,
          decided_by: "LLM",
          turn_count: 4,
          summary_excerpt: "Hỏi giá VF 6",
        },
      ],
      test_drives: [],
    });
    vi.mocked(agentApi.moveSessionOpportunity).mockResolvedValue({ session_id: "s", opportunity_id: "O2", decided_by: "ADVISOR" });

    await renderPage("advisor");

    expect(agentApi.listAdvisorConversations).not.toHaveBeenCalled();
    expect(agentApi.fetchCustomerOverview).toHaveBeenCalledWith("cust-1", "advisor");
    expect(screen.getByText("0912345678")).toBeInTheDocument();
    expect(screen.getByText(/mở lời bằng tổng chi phí/)).toBeInTheDocument();
    expect(screen.getByText("850 triệu")).toBeInTheDocument();
    expect(screen.getByText(/trước: 700 triệu/)).toBeInTheDocument();
    expect(screen.getByText(/Khách né:/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Báo sai/ })).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Tách thành nhu cầu mới/ }));
    });
    expect(agentApi.moveSessionOpportunity).toHaveBeenCalledWith("11111111-aaaa-bbbb-cccc-000000000009", { action: "SPLIT" });
  });
});
