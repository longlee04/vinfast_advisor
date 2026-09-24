// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PromotionManager } from "@/components/advisor/promotion-manager";
import * as promotionsApi from "@/lib/api/promotions";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));
vi.mock("@/lib/api/promotions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/promotions")>()),
  approveOffer: vi.fn(),
  fetchPendingOffers: vi.fn(),
  fetchPromotionStats: vi.fn(),
  fetchRuleSchema: vi.fn(),
  listPromotions: vi.fn(),
}));

afterEach(cleanup);

describe("PromotionManager (Ưu đãi của tư vấn viên)", () => {
  it("Chờ duyệt: liệt kê ưu đãi vượt hạn mức của đồng nghiệp; tự duyệt bị chặn thì báo rõ", async () => {
    vi.mocked(promotionsApi.listPromotions).mockResolvedValue([]);
    vi.mocked(promotionsApi.fetchPromotionStats).mockResolvedValue([]);
    vi.mocked(promotionsApi.fetchRuleSchema).mockResolvedValue({ fields: {}, operators: [], question_hints: {} });
    vi.mocked(promotionsApi.fetchPendingOffers).mockResolvedValue([
      {
        offer_id: "o1",
        opportunity_id: "O1",
        customer_id: "cust-1",
        display_name: "Nguyễn An",
        promotion_code: "T-HN",
        discount_vnd: 30_000_000,
        suggested_by: "adv-1",
        created_at: "2026-09-24T09:00:00Z",
      },
    ]);
    vi.mocked(promotionsApi.approveOffer).mockRejectedValueOnce(
      new promotionsApi.PromotionApiError("Không tự duyệt ưu đãi do chính mình đề xuất", 403),
    );

    await act(async () => {
      render(<PromotionManager />);
    });

    const pending = screen.getByRole("region", { name: "Chờ duyệt (1)" });
    expect(within(pending).getByRole("link", { name: "Nguyễn An" })).toHaveAttribute("href", "/advisor/customers/cust-1");
    expect(within(pending).getByText(/30\.000\.000 đ · đề xuất bởi adv-1/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(within(pending).getByRole("button", { name: "Duyệt" }));
    });
    expect(promotionsApi.approveOffer).toHaveBeenCalledWith("o1");
    expect(screen.getByRole("alert")).toHaveTextContent("Không tự duyệt ưu đãi do chính mình đề xuất");
  });
});
