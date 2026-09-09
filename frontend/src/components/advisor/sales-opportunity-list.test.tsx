// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  SalesOpportunityList,
  formatLastActive,
} from "@/components/advisor/sales-opportunity-list";
import type { SalesOpportunity } from "@/types/agent";

const { fetchSalesOpportunities } = vi.hoisted(() => ({ fetchSalesOpportunities: vi.fn() }));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchSalesOpportunities };
});

function opportunityFixture(overrides: Partial<SalesOpportunity> = {}): SalesOpportunity {
  return {
    session_id: "11111111-1111-1111-1111-111111111111",
    customer_id: "c-cu",
    bottlenecks: ["PRICE", "RANGE"],
    snapshot: {
      needs: ["Đi làm hằng ngày"],
      considered_vehicles: ["VF 5"],
      bottlenecks: [
        { bottleneck: "PRICE", verbatim_quote: "giá xe cao quá em ơi" },
        { bottleneck: "RANGE", verbatim_quote: "chạy được bao xa thôi" },
      ],
      matched_promotions: [],
      offer_state: "BOTTLENECK_NO_OFFER",
      unmet_demand_flag: false,
      unmet_bottleneck: null,
      color_preference: null,
    },
    last_active_at: "2026-08-19T09:00:00Z",
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SalesOpportunityList", () => {
  it("liệt kê phiên kèm nút thắt và nguyên văn câu khách, mới nhất trước", async () => {
    fetchSalesOpportunities.mockResolvedValue([
      opportunityFixture({
        session_id: "s-cu",
        customer_id: "khach-cu",
        last_active_at: "2026-08-19T08:00:00Z",
      }),
      opportunityFixture({
        session_id: "s-moi",
        customer_id: "khach-moi",
        last_active_at: "2026-08-19T09:30:00Z",
      }),
    ]);

    render(<SalesOpportunityList />);

    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(2);
    // Mới hoạt động xếp trước, bất kể thứ tự backend trả về.
    expect(within(cards[0]).getByRole("heading", { level: 3 })).toHaveTextContent("khach-moi");
    expect(within(cards[1]).getByRole("heading", { level: 3 })).toHaveTextContent("khach-cu");

    expect(within(cards[0]).getByText("Giá, Quãng đường")).toBeInTheDocument();
    expect(within(cards[0]).getByText("giá xe cao quá em ơi")).toBeInTheDocument();
    expect(within(cards[0]).getByText("chạy được bao xa thôi")).toBeInTheDocument();
    // Badge `offer_state` dùng đúng bảng chung của màn duyệt (D11).
    expect(
      within(cards[0]).getByText("Có nhu cầu — chưa có chương trình"),
    ).toBeInTheDocument();
  });

  it("nút Xem chi tiết mở phần hồ sơ đầy đủ", async () => {
    fetchSalesOpportunities.mockResolvedValue([opportunityFixture()]);
    render(<SalesOpportunityList />);

    const toggle = await screen.findByRole("button", { name: "Xem chi tiết" });
    expect(screen.queryByText("Đi làm hằng ngày")).not.toBeInTheDocument();

    await userEvent.click(toggle);

    expect(screen.getByText("Đi làm hằng ngày")).toBeInTheDocument();
    expect(screen.getByText("VF 5")).toBeInTheDocument();
    expect(
      screen.getByText("Không có chương trình nào khớp nút thắt của khách."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Thu gọn" })).toBeInTheDocument();
  });

  it("danh sách rỗng hiện empty state chứ không phải bảng trống", async () => {
    fetchSalesOpportunities.mockResolvedValue([]);
    render(<SalesOpportunityList />);

    expect(await screen.findByText("Chưa có cơ hội bán hàng")).toBeInTheDocument();
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("API lỗi hiện thông báo lỗi, không treo ở trạng thái đang tải", async () => {
    fetchSalesOpportunities.mockRejectedValue(new Error("boom"));
    render(<SalesOpportunityList />);

    await waitFor(() =>
      expect(screen.getByText("Không tải được cơ hội bán hàng")).toBeInTheDocument(),
    );
  });

  it("snapshot thiếu khoá vẫn render được (hàng cũ không có hồ sơ đầy đủ)", async () => {
    fetchSalesOpportunities.mockResolvedValue([
      { ...opportunityFixture(), bottlenecks: [], snapshot: {} },
    ]);
    render(<SalesOpportunityList />);

    expect(
      await screen.findByText("Chưa trích được nguyên văn câu khách nói."),
    ).toBeInTheDocument();
    expect(screen.getByText("Chưa rõ nút thắt")).toBeInTheDocument();
  });
});

describe("formatLastActive", () => {
  const now = Date.parse("2026-08-19T10:00:00Z");

  it("đọc được ngay trong vòng một ngày", () => {
    expect(formatLastActive("2026-08-19T09:59:30Z", now)).toBe("Vừa xong");
    expect(formatLastActive("2026-08-19T09:45:00Z", now)).toBe("15 phút trước");
    expect(formatLastActive("2026-08-19T07:00:00Z", now)).toBe("3 giờ trước");
  });

  it("xa hơn một ngày thì trả mốc ngày, chuỗi hỏng thì giữ nguyên", () => {
    expect(formatLastActive("2026-08-17T10:00:00Z", now)).not.toContain("giờ trước");
    expect(formatLastActive("khong-phai-ngay", now)).toBe("khong-phai-ngay");
  });
});
