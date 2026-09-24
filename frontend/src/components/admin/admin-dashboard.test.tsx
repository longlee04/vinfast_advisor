// @vitest-environment jsdom

import { act, cleanup, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminDashboard } from "@/components/admin/admin-dashboard";
import * as agentApi from "@/lib/api/agent";
import * as assignmentsApi from "@/lib/api/assignments";
import { AuthProvider } from "@/store/auth-store";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/assignments", () => ({ fetchAdminDashboardMetrics: vi.fn() }));
vi.mock("@/lib/api/agent", () => ({
  fetchCustomer360Metrics: vi.fn(),
  listAdvisorConversations: vi.fn().mockResolvedValue({ items: [] }),
}));

async function renderDashboard() {
  await act(async () => {
    render(
      <AuthProvider>
        <AdminDashboard />
      </AuthProvider>,
    );
  });
}

describe("AdminDashboard", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(agentApi.listAdvisorConversations).mockResolvedValue({ items: [] });
  });

  it("API lỗi: không bao giờ hiện số bịa (2.480, 1.814, 74%...)", async () => {
    vi.mocked(assignmentsApi.fetchAdminDashboardMetrics).mockRejectedValue(new Error("500"));
    vi.mocked(agentApi.fetchCustomer360Metrics).mockRejectedValue(new Error("500"));

    await renderDashboard();

    for (const fake of ["2.480", "2.068", "1.814", "1.342", "318", "74% duyệt nguyên trạng"]) {
      expect(screen.queryByText(new RegExp(fake))).not.toBeInTheDocument();
    }
    expect(screen.getByRole("alert")).toHaveTextContent("Không tải được số liệu vận hành");
  });

  it("Customer 360: phễu 5 giai đoạn, độ nóng, rào cản vẽ từ số thật và có bảng dữ liệu", async () => {
    vi.mocked(assignmentsApi.fetchAdminDashboardMetrics).mockResolvedValue({
      total_conversations: 12,
      completed_profiles: 5,
      approved_reviews: 3,
      total_bookings: 1,
      funnel: [],
      quality_stats: { approved_original_pct: 60, edited_pct: 30, rejected_pct: 10 },
    });
    vi.mocked(agentApi.fetchCustomer360Metrics).mockResolvedValue({
      stages: { DISCOVER: 4, QUOTE: 2 },
      heat: { HOT: 1, WARM: 2, COLD: 3 },
      barriers: [{ code: "PRICE", count: 5 }],
      workload: [{ advisor_id: "adv-1", customers: 3, hot_customers: 1, waiting_sessions: 0 }],
      totals: { conversations: 12, customers: 6, open_opportunities: 6, test_drives: 1, needs_review: 2 },
    });

    await renderDashboard();

    const section = screen.getByRole("region", { name: "Khách hàng 360" });
    expect(within(section).getByRole("img", { name: "Phễu 5 giai đoạn (số cơ hội)" })).toBeInTheDocument();
    const funnel = within(section).getByRole("table", { name: "Phễu 5 giai đoạn (số cơ hội)" });
    expect(within(funnel).getByRole("rowheader", { name: "Báo giá" }).nextSibling).toHaveTextContent("2");
    expect(within(section).getByText("adv-1")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
  });
});
