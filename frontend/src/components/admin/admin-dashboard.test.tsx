// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
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

    await renderDashboard();

    for (const fake of ["2.480", "2.068", "1.814", "1.342", "318", "74% duyệt nguyên trạng"]) {
      expect(screen.queryByText(new RegExp(fake))).not.toBeInTheDocument();
    }
    expect(screen.getByRole("alert")).toHaveTextContent("Không tải được số liệu vận hành");
  });

  it("Admin chỉ còn số kỹ thuật: không có phễu/độ nóng/rào cản bán hàng (đã sang Tổng quan của TVV)", async () => {
    vi.mocked(assignmentsApi.fetchAdminDashboardMetrics).mockResolvedValue({
      total_conversations: 12,
      completed_profiles: 5,
      approved_reviews: 3,
      total_bookings: 1,
      funnel: [],
      quality_stats: { approved_original_pct: 60, edited_pct: 30, rejected_pct: 10 },
    });

    await renderDashboard();

    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("60% duyệt nguyên trạng")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Khách hàng 360" })).not.toBeInTheDocument();
    expect(agentApi.fetchCustomer360Metrics).not.toHaveBeenCalled();
  });
});
