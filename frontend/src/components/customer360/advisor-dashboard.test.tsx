// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdvisorDashboard, barrierCounts, todayTodos } from "@/components/customer360/advisor-dashboard";
import * as agentApi from "@/lib/api/agent";
import * as assignmentsApi from "@/lib/api/assignments";
import type { OpportunityListItem } from "@/lib/api/agent";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/assignments", () => ({
  fetchNoticeList: vi.fn().mockResolvedValue([]),
  markNoticeRead: vi.fn().mockResolvedValue(undefined),
}));
vi.mock("@/lib/api/agent", () => ({
  fetchCustomerPool: vi.fn(),
  fetchOpportunities: vi.fn(),
  fetchOpportunitySummary: vi.fn(),
}));

function row(overrides: Partial<OpportunityListItem>): OpportunityListItem {
  return {
    opportunity_id: "O",
    customer_id: "c",
    display_name: null,
    assigned_advisor_id: "adv-1",
    vehicle_type: "CAR",
    buyer_for: "SELF",
    status: "OPEN",
    stage: "DISCOVER",
    heat_score: 10,
    heat_band: "COLD",
    slots: {},
    barriers: [],
    needs_review: false,
    last_seen_at: "2026-09-24T09:00:00Z",
    ...overrides,
  };
}

const ROWS = [
  row({ opportunity_id: "O1", customer_id: "c1", display_name: "Khách Nóng", heat_score: 80, heat_band: "HOT", stage: "QUOTE", barriers: ["PRICE"], next_action: { code: "CALL_BACK", label: "Gọi lại khách (đang nóng)" } }),
  row({ opportunity_id: "O2", customer_id: "c2", display_name: "Khách Chờ", heat_score: 40, heat_band: "WARM", barriers: ["PRICE", "CHARGING"], next_action: { code: "TAKE_OVER", label: "Khách đang chờ tư vấn viên — tiếp quản ngay" } }),
  row({ opportunity_id: "O3", customer_id: "c3", display_name: "Khách Lạnh" }),
];

afterEach(cleanup);

describe("AdvisorDashboard (Tổng quan của tư vấn viên)", () => {
  it("việc cần làm: gấp trước (khách đang chờ > gọi lại), khách không có việc thì không hiện", () => {
    expect(todayTodos(ROWS).map((item) => item.customer_id)).toEqual(["c2", "c1"]);
    expect(barrierCounts(ROWS)).toEqual([
      { label: "Giá", value: 2 },
      { label: "Trạm sạc", value: 1 },
    ]);
  });

  it("ghép thẻ số, việc hôm nay, hàng chờ, phễu và rào cản từ API đã có", async () => {
    vi.mocked(agentApi.fetchOpportunitySummary).mockResolvedValue({ hot: 1, waiting: 1, test_drives_48h: 0, unanswered: 4 });
    vi.mocked(agentApi.fetchOpportunities).mockResolvedValue(ROWS);
    vi.mocked(agentApi.fetchCustomerPool).mockResolvedValue([
      { customer_id: "p1", display_name: null, phone: null, sessions_count: 1, last_seen_at: null, waiting: false, heat_band: null, heat_score: null, stage: null, slots: {} },
    ]);

    await act(async () => {
      render(<AdvisorDashboard />);
    });

    expect(agentApi.fetchOpportunities).toHaveBeenCalledWith({ limit: 200 });
    expect(screen.getByText("4")).toBeInTheDocument();
    const todo = within(screen.getByRole("region", { name: "Việc cần làm hôm nay" })).getAllByRole("listitem");
    expect(todo).toHaveLength(2);
    expect(todo[0]).toHaveTextContent("Khách Chờ");
    expect(within(todo[0]).getByRole("link", { name: "Mở hồ sơ Khách Chờ" })).toHaveAttribute("href", "/advisor/customers/c2");
    expect(within(screen.getByRole("region", { name: "Hàng chờ" })).getByText("1")).toBeInTheDocument();
    const funnel = screen.getByRole("table", { name: "Khách của tôi theo giai đoạn" });
    expect(within(funnel).getByRole("rowheader", { name: "Tìm hiểu" }).nextSibling).toHaveTextContent("2");
    expect(screen.getByRole("table", { name: "Khách của tôi hay lo gì" })).toBeInTheDocument();
  });

  it("thông báo nội bộ thật ngay trên Tổng quan: chưa đọc lên trước, bấm Đã đọc thì lưu", async () => {
    vi.mocked(agentApi.fetchOpportunitySummary).mockResolvedValue({ hot: 0, waiting: 0, test_drives_48h: 0, unanswered: 0 });
    vi.mocked(agentApi.fetchOpportunities).mockResolvedValue([]);
    vi.mocked(agentApi.fetchCustomerPool).mockResolvedValue([]);
    vi.mocked(assignmentsApi.fetchNoticeList).mockResolvedValue([
      { notice_id: "n1", title: "Bảng giá cũ", content: "", priority: "NORMAL", created_at: "2026-09-20T00:00:00Z", read: true },
      { notice_id: "n2", title: "Ưu đãi tháng 10", content: "Áp dụng từ 01/10.", priority: "HIGH", created_at: "2026-09-23T00:00:00Z", read: false },
    ]);

    await act(async () => {
      render(<AdvisorDashboard />);
    });

    const notices = within(screen.getByRole("region", { name: "Thông báo nội bộ" }));
    expect(notices.getByText("1 chưa đọc")).toBeInTheDocument();
    expect(notices.getAllByRole("listitem")[0]).toHaveTextContent("Ưu đãi tháng 10");
    await act(async () => {
      fireEvent.click(notices.getByRole("button", { name: "Đã đọc" }));
    });
    expect(assignmentsApi.markNoticeRead).toHaveBeenCalledWith("n2");
  });

  it("không tải được danh sách: báo lỗi, không vẽ số rỗng", async () => {
    vi.mocked(agentApi.fetchOpportunitySummary).mockRejectedValue(new Error("503"));
    vi.mocked(agentApi.fetchOpportunities).mockRejectedValue(new Error("503"));
    vi.mocked(agentApi.fetchCustomerPool).mockRejectedValue(new Error("503"));

    await act(async () => {
      render(<AdvisorDashboard />);
    });

    expect(screen.getByRole("alert")).toHaveTextContent("Không tải được danh sách khách của bạn.");
    expect(screen.queryByRole("region", { name: "Việc cần làm hôm nay" })).not.toBeInTheDocument();
  });
});
