// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

vi.mock("@/lib/api/agent", () => ({
  joinAdvisorConversation: vi.fn(),
  releaseCustomer: vi.fn(),
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

const OPPORTUNITY = {
  opportunity_id: "O1",
  vehicle_type: "CAR",
  buyer_for: "SELF" as const,
  status: "OPEN" as const,
  stage: "QUOTE" as const,
  heat_score: 70,
  heat_band: "HOT" as const,
  heat_breakdown: [{ code: "H1", points: 25, detail: "QUOTE" }],
  needs: {
    known: [{ slot: "budget_max_vnd", value: "850000000", history: [{ value: "700000000", at: "2026-09-20" }] }],
    missing: ["passenger_count"],
    evaded: ["passenger_count"],
    evaded_detail: [{ slot: "passenger_count", ask_count: 3 }],
  },
  barriers: [
    {
      code: "PRICE",
      source: "BOTTLENECK" as const,
      evidence_quote: "đắt quá",
      turn_index: 3,
      session_id: "s1",
      status: "CORRECT",
      at: "2026-09-22T03:00:00Z",
    },
  ],
  insights: [
    { insight_id: "i1", field: "purchase_timeframe", value: "Tết", source: "LLM" as const, evidence_quote: "muốn có xe trước Tết", at: "2026-09-24", history: [] },
  ],
  opening_hint: "Khách còn cân nhắc về giá — mở lời bằng tổng chi phí lăn bánh.",
  opening_hint_basis: { kind: "BARRIER" as const, code: "PRICE" },
  next_actions: [{ code: "REVIEW_ATTACH", label: "Xác nhận phiên thuộc nhu cầu nào (Tách/Gộp)" }],
  stage_history: [
    { stage: "DISCOVER" as const, at: "2026-09-18T03:00:00Z" },
    { stage: "COMPARE" as const, at: "2026-09-20T03:00:00Z" },
  ],
  vehicles_of_interest: [{ vehicle_id: "v6", name: "VinFast VF 6", role: "CHOSEN" as const, rank: null, quote_sent_at: null, asked_features: [] }],
};

const OVERVIEW = {
  customer: {
    customer_id: "cust-1",
    display_name: "Nguyễn An",
    phone_masked: "0912***678",
    phone: "0912345678" as string | undefined,
    assigned_advisor_id: "adv-1",
    heat_band: "HOT" as const,
    heat_score: 70,
    sessions_count: 1,
    last_seen_at: "2026-09-24T09:00:00Z",
    fields: {},
    latest_summary: "Gia đình 4 người, nghiêng về VF 6.",
  },
  opportunities: [OPPORTUNITY],
  sessions: [
    {
      session_id: "11111111-aaaa-bbbb-cccc-000000000009",
      started_at: null,
      last_activity_at: "2026-09-24T09:00:00Z",
      status: "ACTIVE" as const,
      ownership: "AI",
      kind: "SALES" as const,
      opportunity_id: "O1",
      needs_review: true,
      decided_by: "LLM" as const,
      turn_count: 4,
      summary_excerpt: "Hỏi giá VF 6",
    },
  ],
  test_drives: [],
};

async function renderPage(role: "advisor" | "admin") {
  await act(async () => {
    render(<CustomerProfilePage customerId="cust-1" readOnly={role === "admin"} role={role} />);
  });
}

function enableCustomer360() {
  vi.mocked(agentApi.fetchCustomer360Meta).mockResolvedValue({ enabled: { ui: true, attach: true, extractor: true } });
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

  it("TVV: đầu hồ sơ, Xem hội thoại/Tiếp quản vào phiên đang chờ, tab Phiên chat và Lái thử lọc đúng khách", async () => {
    vi.mocked(agentApi.joinAdvisorConversation).mockResolvedValue({ joined: true, conversation_id: CONVERSATIONS[0].conversation_id });
    await renderPage("advisor");

    expect(screen.getByRole("heading", { name: "Nguyễn An" })).toBeInTheDocument();
    expect(screen.getByText("0912***678")).toBeInTheDocument();
    const waiting = `/advisor/conversations/${CONVERSATIONS[0].conversation_id}`;
    expect(screen.getByRole("link", { name: "Xem hội thoại" })).toHaveAttribute("href", waiting);
    // Tổng quan (nguồn dự phòng): chỉ còn lưới nhu cầu từ slot phiên gần nhất.
    expect(screen.getByText("800 triệu")).toBeInTheDocument();
    expect(screen.queryByText("Gợi ý mở lời")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Rào cản khách đã nói ra" })).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Tiếp quản hội thoại" }));
    });
    expect(agentApi.joinAdvisorConversation).toHaveBeenCalledWith(CONVERSATIONS[0].conversation_id);
    expect(push).toHaveBeenCalledWith(waiting);

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    expect(within(screen.getByRole("tabpanel")).getAllByRole("listitem")).toHaveLength(2);

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Lái thử/ }));
    });
    expect(screen.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(screen.queryByText("cust-other")).not.toBeInTheDocument();
    expect(within(screen.getByRole("tabpanel")).getAllByRole("listitem")).toHaveLength(1);
  });

  it("Admin (chỉ xem, lo kỹ thuật): không nhận/trả/phân công khách; phiên mở sang trang trace", async () => {
    await renderPage("admin");

    expect(screen.queryByRole("button", { name: /Tiếp quản/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Gọi khách" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Phân công lại/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Trả khách/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Phiên chat/ })).toHaveAttribute("href", "/admin/chat-sessions");
    expect(assignmentsApi.fetchAdvisorCustomers).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    expect(within(screen.getByRole("tabpanel")).getAllByRole("link", { name: /Xem/ })[0]).toHaveAttribute(
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

  it("Cờ Customer 360 bật: MỘT lần gọi /overview — bố cục mockup đủ khối, TVV gọi/tiếp quản/báo sai/tách phiên được", async () => {
    enableCustomer360();
    vi.mocked(agentApi.fetchCustomerOverview).mockResolvedValue(OVERVIEW);
    vi.mocked(agentApi.moveSessionOpportunity).mockResolvedValue({ session_id: "s", opportunity_id: "O2", decided_by: "ADVISOR" });

    await renderPage("advisor");

    expect(agentApi.listAdvisorConversations).not.toHaveBeenCalled();
    expect(agentApi.fetchCustomerOverview).toHaveBeenCalledWith("cust-1", "advisor");
    // Thẻ đầu: SĐT hiện bản che, số đầy đủ chỉ nằm trong nút gọi; tổng lượt; ai đang trả lời.
    expect(screen.getByText("0912***678")).toBeInTheDocument();
    expect(screen.queryByText("0912345678")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Gọi khách" })).toHaveAttribute("href", "tel:0912345678");
    expect(screen.getByText("1 phiên chat · 4 lượt")).toBeInTheDocument();
    expect(screen.getByText("AI đang trả lời")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Tiếp quản hội thoại" })).toBeInTheDocument();
    expect(screen.getByText("Báo giá · hiện tại")).toBeInTheDocument();
    expect(screen.getByText("20/09")).toBeInTheDocument();
    // Cột trái.
    expect(screen.getByText(/mở lời bằng tổng chi phí/)).toBeInTheDocument();
    expect(screen.getByText("Dựa trên rào cản chính (Giá).")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lượt 3 · 22/09" })).toHaveAttribute("href", "/advisor/conversations/s1#turn-3");
    expect(screen.getByText("850 triệu")).toBeInTheDocument();
    expect(screen.getByText(/trước: 700 triệu/)).toBeInTheDocument();
    expect(screen.getByText("Khách né · hỏi 3 lần")).toBeInTheDocument();
    expect(screen.getByText("Tết")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Báo sai/ })).toBeInTheDocument();
    // Cột phải.
    expect(screen.getByRole("checkbox", { name: /Tách\/Gộp/ })).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(screen.getByText("Khách đã chọn")).toBeInTheDocument();
    expect(screen.getByText("Gia đình 4 người, nghiêng về VF 6.")).toBeInTheDocument();
    // Một cơ hội → không có hàng chọn nhu cầu.
    expect(screen.queryByRole("group", { name: "Chọn nhu cầu mua" })).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Phiên chat/ }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Tách thành nhu cầu mới/ }));
    });
    expect(agentApi.moveSessionOpportunity).toHaveBeenCalledWith("11111111-aaaa-bbbb-cccc-000000000009", { action: "SPLIT" });
  });

  it("Admin chỉ xem (cờ bật): không Gọi/Tiếp quản/checkbox/Báo sai/Trả khách", async () => {
    enableCustomer360();
    vi.mocked(agentApi.fetchCustomerOverview).mockResolvedValue({ ...OVERVIEW, customer: { ...OVERVIEW.customer, phone: undefined } });

    await renderPage("admin");

    expect(agentApi.fetchCustomerOverview).toHaveBeenCalledWith("cust-1", "admin");
    expect(screen.queryByRole("link", { name: "Gọi khách" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Tiếp quản/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Báo sai/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Trả khách/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Xem hội thoại" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lượt 3 · 22/09" })).toHaveAttribute("href", "/admin/conversations/s1#turn-3");
  });

  it("TVV phụ trách trả khách về hàng chờ rồi quay lại danh sách", async () => {
    enableCustomer360();
    vi.mocked(agentApi.fetchCustomerOverview).mockResolvedValue(OVERVIEW);
    vi.mocked(agentApi.releaseCustomer).mockResolvedValue({ released: true });
    vi.spyOn(window, "confirm").mockReturnValue(true);

    await renderPage("advisor");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Trả khách về hàng chờ" }));
    });

    expect(agentApi.releaseCustomer).toHaveBeenCalledWith("cust-1");
    expect(push).toHaveBeenCalledWith("/advisor/customers");
  });

  it("Nhiều nhu cầu: mặc định nhu cầu nóng nhất, bấm chọn thì khối bên dưới đổi theo", async () => {
    enableCustomer360();
    vi.mocked(agentApi.fetchCustomerOverview).mockResolvedValue({
      ...OVERVIEW,
      opportunities: [
        OPPORTUNITY,
        {
          ...OPPORTUNITY,
          opportunity_id: "O2",
          vehicle_type: "ELECTRIC_MOTORBIKE",
          buyer_for: "FAMILY" as const,
          stage: "DISCOVER" as const,
          heat_band: "WARM" as const,
          heat_score: 52,
          opening_hint: "Hỏi thêm ngân sách để đề xuất đúng xe.",
          opening_hint_basis: { kind: "MISSING" as const, code: "budget_max_vnd" },
          stage_history: [],
        },
      ],
    });

    await renderPage("advisor");

    const switcher = screen.getByRole("group", { name: "Chọn nhu cầu mua" });
    expect(within(switcher).getByRole("button", { name: "Ô tô điện · mua cho bản thân · Nóng 70" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/mở lời bằng tổng chi phí/)).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(within(switcher).getByRole("button", { name: "Xe máy điện · mua cho người nhà · Ấm 52" }));
    });
    expect(screen.getByText("Hỏi thêm ngân sách để đề xuất đúng xe.")).toBeInTheDocument();
    expect(screen.getByText("Tìm hiểu · hiện tại")).toBeInTheDocument();
  });
});
