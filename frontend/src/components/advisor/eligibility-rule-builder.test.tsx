// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EligibilityRuleBuilder, groupToRules, rulesToGroup } from "@/components/advisor/eligibility-rule-builder";
import { EligibleOfferList } from "@/components/customer360/eligible-offer-list";
import * as promotionsApi from "@/lib/api/promotions";

vi.mock("@/lib/api/promotions", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/promotions")>()),
  fetchEligibleOffers: vi.fn(),
  proposeOffer: vi.fn(),
}));

const FIELD_TYPES = { registration_province: "str", budget_max_vnd: "number", customer_group: "enum" };

afterEach(cleanup);

describe("EligibilityRuleBuilder", () => {
  it("luật phẳng ⇄ bảng: không mất thông tin, số vẫn là số, 'in' vẫn là danh sách", () => {
    const rules = {
      all: [
        { field: "registration_province", in: ["HN", "HCM"] },
        { field: "budget_max_vnd", gte: 500_000_000 },
      ],
    };
    const group = rulesToGroup(rules);
    expect(group?.rows).toHaveLength(2);
    expect(groupToRules(group!, FIELD_TYPES)).toEqual(rules);
    expect(rulesToGroup({ all: [{ any: [] }] })).toBeNull();
    expect(groupToRules({ combinator: "all", rows: [] }, FIELD_TYPES)).toEqual({});
  });

  it("thêm điều kiện qua bảng phát ra đúng DSL; luật lồng nhau mở chế độ JSON", () => {
    const onChange = vi.fn();
    const { rerender } = render(<EligibilityRuleBuilder fieldTypes={FIELD_TYPES} onChange={onChange} value={{}} />);

    fireEvent.click(screen.getByRole("button", { name: /Thêm điều kiện/ }));
    expect(onChange).toHaveBeenLastCalledWith({ all: [{ field: "registration_province", eq: "" }] });

    rerender(
      <EligibilityRuleBuilder fieldTypes={FIELD_TYPES} onChange={onChange} value={{ all: [{ any: [{ field: "customer_group", eq: "VNPOST" }] }] }} />,
    );
    // Giữ trạng thái bảng của lần render trước — dựng lại component mới để thấy chế độ JSON.
    cleanup();
    render(
      <EligibilityRuleBuilder fieldTypes={FIELD_TYPES} onChange={onChange} value={{ all: [{ any: [{ field: "customer_group", eq: "VNPOST" }] }] }} />,
    );
    expect(screen.getByRole("textbox", { name: "Luật (JSON)" })).toBeInTheDocument();
    expect(screen.getByText(/chỉ sửa được bằng JSON/)).toBeInTheDocument();
  });
});

describe("EligibleOfferList", () => {
  it("TVV: phù hợp có nút Đề xuất và báo chờ quản lý khi vượt ngưỡng; cần thêm thông tin có câu hỏi gợi ý", async () => {
    vi.mocked(promotionsApi.fetchEligibleOffers).mockResolvedValue({
      eligible: [
        {
          promotion_code: "HN-10",
          title: "Ưu đãi Hà Nội",
          promotion_type: "FIXED_DISCOUNT",
          discount_amount_vnd: 10_000_000,
          discount_percent: null,
          stackable: false,
          advisor_max_discount_vnd: 5_000_000,
          reasons: ["Tỉnh đăng ký HN thuộc {HN}"],
        },
      ],
      need_info: [
        {
          promotion_code: "CAQD",
          title: "Công an quân đội",
          promotion_type: "PERCENT_DISCOUNT",
          discount_amount_vnd: null,
          discount_percent: 4,
          stackable: false,
          advisor_max_discount_vnd: null,
          missing_fields: ["customer_group"],
          question_hints: ["Anh/chị có thuộc nhóm được ưu đãi riêng không ạ?"],
        },
      ],
    });
    vi.mocked(promotionsApi.proposeOffer).mockResolvedValue({
      offer_id: "o1",
      opportunity_id: "O1",
      promotion_code: "HN-10",
      status: "SUGGESTED",
      discount_vnd: 10_000_000,
      needs_manager_approval: true,
    });

    await act(async () => {
      render(<EligibleOfferList opportunityId="O1" readOnly={false} />);
    });

    expect(screen.getByText(/10\.000\.000 đ/)).toBeInTheDocument();
    expect(screen.getByText(/Tỉnh đăng ký HN/)).toBeInTheDocument();
    expect(screen.getByText(/Anh\/chị có thuộc nhóm được ưu đãi riêng/)).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Đề xuất" }));
    });
    expect(promotionsApi.proposeOffer).toHaveBeenCalledWith("O1", "HN-10");
    expect(screen.getByRole("status")).toHaveTextContent("chờ một tư vấn viên khác duyệt");
  });

  it("chỉ xem (Admin): không có nút Đề xuất", async () => {
    vi.mocked(promotionsApi.fetchEligibleOffers).mockResolvedValue({ eligible: [], need_info: [] });
    await act(async () => {
      render(<EligibleOfferList opportunityId="O1" readOnly />);
    });
    expect(screen.getByText("Chưa có ưu đãi phù hợp.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đề xuất" })).not.toBeInTheDocument();
  });
});
