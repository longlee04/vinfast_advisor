// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerSummary } from "@/components/customer360/customer-summary";
import { budgetText, needSummary, relativeAge } from "@/components/customer360/customer360-labels";
import { OpportunityOverview } from "@/components/customer360/opportunity-card";
import { OpportunityQueue } from "@/components/customer360/opportunity-queue";
import { SessionList } from "@/components/customer360/session-list";
import { StageBar } from "@/components/customer360/stage-bar";
import * as agentApi from "@/lib/api/agent";
import type { SessionRow } from "@/types/customer360";

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
  claimCustomer: vi.fn(),
  fetchCustomerPool: vi.fn(),
  fetchMyCustomers: vi.fn(),
  fetchOpportunitySummary: vi.fn(),
}));

const CUSTOMER = {
  customer_id: "cust-1",
  display_name: "Nguyễn An",
  phone_masked: "0912***678",
  phone: "0912345678",
  assigned_advisor_id: "adv-1",
  sessions_count: 2,
  last_seen_at: "2026-09-24T09:00:00Z",
  heat_band: "HOT" as const,
  heat_score: 70,
};

const SESSION: SessionRow = {
  session_id: "11111111-2222-3333-4444-555555555555",
  started_at: null,
  last_activity_at: "2026-09-24T09:00:00Z",
  status: "ACTIVE",
  kind: "UNASSIGNED",
  opportunity_id: null,
  needs_review: false,
  decided_by: null,
  turn_count: null,
  summary_excerpt: "Hỏi giá VF 6",
};

afterEach(cleanup);

describe("CustomerSummary", () => {
  it("thẻ đầu hồ sơ: tên, độ nóng, SĐT luôn là bản đã che, số phiên/lượt, nút thao tác", () => {
    render(
      <CustomerSummary
        actions={<button type="button">Xem hội thoại</button>}
        customer={{ ...CUSTOMER, address: "12 Láng Hạ, Hà Nội" }}
        ownership="AI"
        turnsTotal={38}
      />,
    );

    expect(screen.getByRole("heading", { name: "Nguyễn An" })).toBeInTheDocument();
    expect(screen.getByLabelText("Độ nóng: Nóng · 70")).toBeInTheDocument();
    expect(screen.getByText("0912***678")).toBeInTheDocument();
    expect(screen.queryByText("0912345678")).not.toBeInTheDocument();
    expect(screen.getByText("2 phiên chat · 38 lượt")).toBeInTheDocument();
    expect(screen.getByText("AI đang trả lời")).toBeInTheDocument();
    expect(screen.getByText("12 Láng Hạ, Hà Nội")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Xem hội thoại" })).toBeInTheDocument();
  });
});

describe("StageBar", () => {
  it("bản gọn tô đúng số vạch theo giai đoạn", () => {
    const { container } = render(<StageBar stage="QUOTE" variant="compact" />);
    expect(container.querySelectorAll(".c360-stage-dots span[data-reached]")).toHaveLength(3);
    expect(screen.getByText("Báo giá")).toBeInTheDocument();
  });

  it("bản đầy đủ: mốc ngày chỉ khi có bằng chứng, giai đoạn hiện tại đánh dấu", () => {
    render(
      <StageBar
        history={[
          { stage: "DISCOVER", at: "2026-09-18T03:00:00Z" },
          { stage: "TEST_DRIVE", at: "2026-09-27T02:00:00Z", note: "REQUESTED" },
        ]}
        stage="TEST_DRIVE"
      />,
    );
    const steps = within(screen.getByRole("list", { name: "Giai đoạn mua" })).getAllByRole("listitem");
    expect(steps.filter((step) => step.hasAttribute("data-reached"))).toHaveLength(4);
    expect(screen.getByText("18/09")).toBeInTheDocument();
    expect(screen.getByText("27/09 · chưa xác nhận")).toBeInTheDocument();
    expect(screen.getByText("Lái thử · hiện tại")).toBeInTheDocument();
    expect(steps[1]).not.toHaveTextContent("/");
  });
});

describe("SessionList", () => {
  it("TVV mở phòng chat, Admin (readOnly) sang trang trace", () => {
    const { rerender } = render(<SessionList readOnly={false} role="advisor" sessions={[SESSION]} />);
    expect(screen.getByRole("link", { name: /Mở chat/ })).toHaveAttribute("href", `/advisor/conversations/${SESSION.session_id}`);

    rerender(<SessionList readOnly role="admin" sessions={[SESSION]} />);
    expect(screen.getByRole("link", { name: /Xem/ })).toHaveAttribute("href", `/admin/chat-sessions/${SESSION.session_id}`);
  });

  it("không có phiên thì nói rõ, không để trống", () => {
    render(<SessionList readOnly={false} role="advisor" sessions={[]} />);
    expect(screen.getByText("Chưa có phiên chat nào từ khách hàng này.")).toBeInTheDocument();
  });
});

describe("OpportunityOverview", () => {
  const slots = { vehicle_type: "CAR", budget_max_vnd: 900_000_000, budget_stated_vnd: 800_000_000, purpose_bucket: "FAMILY", purpose: "đưa con đi học" };

  it("đủ dữ liệu: gợi ý + lý do, rào cản trỏ đúng lượt, lưới nhu cầu có ô thiếu/khách né, xe quan tâm, việc cần làm", () => {
    render(
      <OpportunityOverview
        conversationHref="/advisor/conversations/s1"
        customerFields={{ payment_method: { value: "Trả góp", source: "LLM", at: "2026-09-24", history: [] } }}
        latestSummary="Gia đình 4 người, nghiêng về VF 6."
        opportunity={{
          title: "Ô tô điện",
          slots,
          missing: ["passenger_count", "home_charging"],
          evadedDetail: [{ slot: "home_charging", ask_count: 2 }],
          barriers: [
            { code: "CHARGING", evidence_quote: "hầm không cho sạc", session_id: "s1", turn_index: 7, at: "2026-09-20T03:00:00Z" },
            { code: "PRICE", evidence_quote: "hơi đắt, số em [SĐT]", session_id: "s1", turn_index: 24 },
          ],
          openingHint: "Khách lo chỗ sạc — hỏi nơi ở.",
          openingBasis: { kind: "BARRIER", code: "CHARGING" },
          nextActions: [{ code: "RESOLVE_PRICE", label: "Xử lý băn khoăn: PRICE" }],
          vehicles: [
            { vehicle_id: "v6", name: "VinFast VF 6", role: "RECOMMENDED", rank: 1, quote_sent_at: null, asked_features: ["sạc nhanh"] },
          ],
        }}
        readOnly={false}
        role="advisor"
      />,
    );

    expect(screen.getByText("Dựa trên rào cản chính (Trạm sạc).")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lượt 7 · 20/09" })).toHaveAttribute("href", "/advisor/conversations/s1#turn-7");
    expect(screen.getByText("hơi đắt, số em [SĐT]")).toBeInTheDocument();
    // Ngân sách khách NÓI RA thắng trần đã nới biên; slot nội bộ không hiện.
    expect(screen.getByText("800 triệu")).toBeInTheDocument();
    expect(screen.queryByText("900 triệu")).not.toBeInTheDocument();
    expect(screen.queryByText("FAMILY")).not.toBeInTheDocument();
    expect(screen.getByText("Khách né · hỏi 2 lần")).toBeInTheDocument();
    expect(screen.getAllByText("Chưa có").length).toBeGreaterThan(0);
    expect(screen.getByText("Trả góp")).toBeInTheDocument();
    expect(screen.getByText(/\/\d+ thông tin đã có/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Xử lý băn khoăn: giá" })).toBeInTheDocument();
    expect(screen.getByText("AI đề xuất số 1")).toBeInTheDocument();
    expect(screen.getByText("Hỏi về: sạc nhanh")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mở toàn bộ hội thoại" })).toHaveAttribute("href", "/advisor/conversations/s1");
  });

  it("nguồn dự phòng (thiếu dữ liệu): chỉ còn lưới nhu cầu, không hiện khung rỗng", () => {
    render(<OpportunityOverview opportunity={{ title: "Nhu cầu hiện tại", slots, barriers: [] }} readOnly={false} role="advisor" />);

    expect(screen.getByRole("heading", { name: "Nhu cầu" })).toBeInTheDocument();
    for (const name of ["Rào cản khách đã nói ra", "Việc cần làm", "Xe quan tâm", "Tóm tắt của AI", "Khách tự kể trong hội thoại"]) {
      expect(screen.queryByRole("heading", { name })).not.toBeInTheDocument();
    }
    expect(screen.queryByText("Gợi ý mở lời")).not.toBeInTheDocument();
  });

  it("chỉ xem (Admin): không checkbox, không nút Báo sai", () => {
    render(
      <OpportunityOverview
        onInsightFeedback={vi.fn()}
        opportunity={{
          title: "Ô tô điện",
          slots,
          barriers: [],
          nextActions: [{ code: "CALL_BACK", label: "Gọi lại khách (đang nóng)" }],
          insights: [{ insight_id: "i1", field: "purchase_timeframe", value: "tháng này", source: "LLM", at: "2026-09-24", history: [] }],
        }}
        readOnly
        role="admin"
      />,
    );
    expect(screen.getByText("Gọi lại khách (đang nóng)")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Báo sai/ })).not.toBeInTheDocument();
  });

  it("tóm tắt ưu tiên ngân sách khách nói hơn trần đã nới biên, không có slot thì trả null", () => {
    expect(needSummary(slots)).toBe("Loại xe: Ô tô điện · Ngân sách khách nói: 800 triệu · Mục đích: đưa con đi học");
    expect(needSummary({})).toBeNull();
    expect(budgetText({ budget_min_vnd: 850_000_000, budget_max_vnd: 1_000_000_000 })).toBe("850 triệu – 1 tỷ");
    expect(budgetText({})).toBeNull();
  });

  it("tuổi ngắn của mốc thời gian", () => {
    const now = Date.parse("2026-09-24T10:00:00Z");
    expect(relativeAge("2026-09-24T09:48:00Z", now)).toBe("12 phút");
    expect(relativeAge("2026-09-24T08:00:00Z", now)).toBe("2 giờ");
    expect(relativeAge("2026-09-23T08:00:00Z", now)).toBe("Hôm qua");
    expect(relativeAge("2026-09-21T08:00:00Z", now)).toBe("3 ngày");
    expect(relativeAge("2026-09-21T08:00:00Z", 0)).toBe("");
  });
});

describe("OpportunityQueue — Khách hàng: tab Đã nhận / Chưa nhận (plan §20)", () => {
  const MINE: agentApi.MyCustomerItem[] = [
    {
      customer_id: "cust-1",
      display_name: "Nguyễn An",
      email: null,
      assigned_at: "2026-09-20T00:00:00Z",
      opportunity_id: "O1",
      vehicle_type: "CAR",
      stage: "TEST_DRIVE",
      heat_score: 86,
      heat_band: "HOT",
      slots: { budget_stated_vnd: 700_000_000 },
      barriers: ["CHARGING", "PRICE"],
      needs_review: false,
      last_seen_at: "2026-09-24T09:00:00Z",
      sessions_count: 4,
      has_phone: true,
      waiting: false,
      has_test_drive: true,
      top_vehicle_name: "VinFast VF 6",
      next_action: { code: "CONFIRM_TEST_DRIVE", label: "Xác nhận lịch lái thử" },
    },
    {
      customer_id: "cust-2",
      display_name: null,
      email: "mi***@gmail.com",
      assigned_at: "2026-09-24T08:00:00Z",
      opportunity_id: null,
      vehicle_type: null,
      stage: null,
      heat_score: null,
      heat_band: null,
      slots: {},
      barriers: [],
      needs_review: false,
      last_seen_at: "2026-09-24T08:00:00Z",
      sessions_count: 0,
      has_phone: false,
      waiting: false,
      has_test_drive: false,
      top_vehicle_name: null,
      next_action: null,
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(agentApi.fetchOpportunitySummary).mockResolvedValue({ hot: 2, waiting: 1, test_drives_48h: 1, unanswered: 3 });
    vi.mocked(agentApi.fetchMyCustomers).mockResolvedValue(MINE);
    vi.mocked(agentApi.fetchCustomerPool).mockResolvedValue([
      {
        customer_id: "cust-9",
        display_name: "Khách Chờ",
        phone: "0912***678",
        sessions_count: 2,
        last_seen_at: "2026-09-24T09:00:00Z",
        waiting: true,
        heat_band: "HOT",
        heat_score: 72,
        stage: "QUOTE",
        slots: {},
      },
      {
        customer_id: "cust-new",
        display_name: null,
        phone: null,
        email: "zz***@gmail.com",
        sessions_count: 0,
        last_seen_at: null,
        waiting: false,
        heat_band: null,
        heat_score: null,
        stage: null,
        slots: {},
      },
    ]);
  });

  it("có dòng giải thích cơ chế lưu; tab Đã nhận gồm cả khách chưa có nhu cầu; bộ lọc gọi đúng tham số", async () => {
    await act(async () => {
      render(<OpportunityQueue />);
    });

    expect(screen.getByText(/Hồ sơ khách tự lưu: ngay khi khách đăng nhập/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Đã nhận (2)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Chưa nhận (2)" })).toBeInTheDocument();

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(3);
    const first = within(rows[1]);
    expect(first.getByLabelText("Độ nóng: Nóng · 86")).toBeInTheDocument();
    expect(first.getByText("4 phiên · để lại SĐT")).toBeInTheDocument();
    expect(first.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(first.getByText("Trạm sạc")).toBeInTheDocument();
    expect(first.getByText("+1")).toBeInTheDocument();
    expect(first.getByText("Xác nhận lịch lái thử")).toBeInTheDocument();
    // Khách vừa nhận, chưa chat: vẫn có mặt, tên hiện email đã che, nhắc hỏi nhu cầu.
    const fresh = within(rows[2]);
    expect(fresh.getByRole("link", { name: "mi***@gmail.com" })).toHaveAttribute("href", "/advisor/customers/cust-2");
    expect(fresh.getByText("Chưa chat")).toBeInTheDocument();
    expect(fresh.getByText(/Chưa có nhu cầu/)).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Chờ người thật" }));
    });
    expect(agentApi.fetchMyCustomers).toHaveBeenLastCalledWith({ waiting: true, limit: 500 });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Lái thử trong 48 giờ/ }));
    });
    expect(agentApi.fetchMyCustomers).toHaveBeenLastCalledWith({ hasTestDrive: true, limit: 500 });
  });

  it("tab Chưa nhận: có cả khách mới đăng ký chưa chat; Nhận khách xong sang hồ sơ, bị nhận trước thì báo", async () => {
    vi.mocked(agentApi.claimCustomer).mockResolvedValueOnce({ outcome: "CLAIMED", customer_id: "cust-9" });

    await act(async () => {
      render(<OpportunityQueue />);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: "Chưa nhận (2)" }));
    });

    expect(screen.getByText("Yêu cầu gặp người thật · 2 phiên · 0912***678")).toBeInTheDocument();
    expect(screen.getByText("zz***@gmail.com")).toBeInTheDocument();
    expect(screen.getAllByText("Chưa chat").length).toBeGreaterThan(0);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Nhận khách Khách Chờ" }));
    });
    expect(agentApi.claimCustomer).toHaveBeenCalledWith("cust-9");
    expect(push).toHaveBeenCalledWith("/advisor/customers/cust-9");
    expect(screen.getByRole("tab", { name: "Đã nhận (3)" })).toBeInTheDocument();

    cleanup();
    vi.mocked(agentApi.claimCustomer).mockRejectedValueOnce(Object.assign(new Error("conflict"), { status: 409 }));
    await act(async () => {
      render(<OpportunityQueue />);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("tab", { name: /Chưa nhận/ }));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Nhận khách Khách Chờ" }));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Khách vừa được tư vấn viên khác nhận.");
  });
});
