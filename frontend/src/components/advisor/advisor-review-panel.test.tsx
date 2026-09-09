// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdvisorReviewPanel } from "@/components/advisor/advisor-review-panel";
import type { OfferState, ReviewDetail } from "@/types/agent";

const { approveReview, claimReview, fetchReviewDetail, rejectReview, resolveReview } = vi.hoisted(
  () => ({
    approveReview: vi.fn(),
    claimReview: vi.fn(),
    fetchReviewDetail: vi.fn(),
    rejectReview: vi.fn(),
    resolveReview: vi.fn(),
  }),
);

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, approveReview, claimReview, fetchReviewDetail, rejectReview, resolveReview };
});

function detailFixture(overrides: Partial<ReviewDetail> = {}): ReviewDetail {
  return {
    review_id: "11111111-1111-1111-1111-111111111111",
    session_id: "s-1",
    run_id: "run-1",
    status: "PENDING",
    content: "Ban nhap tu API",
    edited_content: null,
    comparison_image_base64: null,
    profile_snapshot: {
      needs: ["Chở 7 người", "Đi tỉnh cuối tuần"],
      considered_vehicles: ["VF 8", "VF 9"],
      bottlenecks: [{ bottleneck: "PRICE", verbatim_quote: "Giá này hơi quá tầm em ạ" }],
      matched_promotions: [{ promotion_code: "KM-01", promotion_type: "FIXED_DISCOUNT" }],
      verified_number_tokens: [],
      offer_state: "BOTTLENECK_OFFER_AVAILABLE",
      unmet_demand_flag: false,
      unmet_bottleneck: null,
      color_preference: "Trắng",
    },
    offer_state: "BOTTLENECK_OFFER_AVAILABLE",
    matched_promotions: [{ promotion_code: "KM-01", promotion_type: "FIXED_DISCOUNT" }],
    adjustment_policies: [
      { promotion_type: "FIXED_DISCOUNT", adjust_min_vnd: 1_000_000, adjust_max_vnd: 5_000_000 },
    ],
    ...overrides,
  };
}

beforeEach(() => {
  claimReview.mockResolvedValue({ granted: true, rejection: null });
  approveReview.mockResolvedValue({ review_id: "r-1" });
  rejectReview.mockResolvedValue({ review_id: "r-1" });
  resolveReview.mockResolvedValue({ review_id: "r-1" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AdvisorReviewPanel — hồ sơ 3 phần từ API", () => {
  it("render đúng dữ liệu API chứ không phải nội dung cứng", async () => {
    fetchReviewDetail.mockResolvedValue(detailFixture());

    render(<AdvisorReviewPanel reviewId="r-1" />);

    expect(await screen.findByText("Ban nhap tu API")).toBeInTheDocument();

    const needs = screen.getByLabelText("Tổng hợp nhu cầu");
    expect(within(needs).getByText("Chở 7 người")).toBeInTheDocument();
    expect(within(needs).getByText("VF 8, VF 9")).toBeInTheDocument();
    expect(within(needs).getByText("Trắng")).toBeInTheDocument();

    const offers = screen.getByLabelText("Đề xuất ưu đãi");
    expect(within(offers).getByText("KM-01")).toBeInTheDocument();
    expect(within(offers).getByText("Giảm tiền mặt")).toBeInTheDocument();

    const approach = screen.getByLabelText("Hướng tiếp cận");
    expect(within(approach).getByText("Giá")).toBeInTheDocument();
    expect(within(approach).getByText("Giá này hơi quá tầm em ạ")).toBeInTheDocument();
  });

  it("hiện trạng thái rỗng cho từng phần khi hồ sơ trống", async () => {
    fetchReviewDetail.mockResolvedValue(
      detailFixture({
        profile_snapshot: { offer_state: "NONE_BOTTLENECK" },
        matched_promotions: [],
        offer_state: "NONE_BOTTLENECK",
      }),
    );

    render(<AdvisorReviewPanel reviewId="r-1" />);

    expect(
      await screen.findByText("Chưa ghi nhận nhu cầu cụ thể trong phiên này."),
    ).toBeInTheDocument();
    expect(screen.getByText("Không có chương trình nào khớp nút thắt của khách.")).toBeInTheDocument();
    expect(
      screen.getByText("Khách chưa bộc lộ nút thắt nào — tiếp cận theo hướng giới thiệu chung."),
    ).toBeInTheDocument();
  });
});

describe("AdvisorReviewPanel — badge offer_state (D11)", () => {
  const cases: readonly [OfferState | null, string, string][] = [
    ["NONE_BOTTLENECK", "Chưa rõ nút thắt", "status-neutral"],
    ["BOTTLENECK_NO_OFFER", "Có nhu cầu — chưa có chương trình", "status-warning"],
    ["BOTTLENECK_OFFER_AVAILABLE", "Có ưu đãi đề xuất", "status-success"],
  ];

  it.each(cases)("trạng thái %s phân biệt bằng cả chữ lẫn màu", async (state, label, tone) => {
    fetchReviewDetail.mockResolvedValue(
      detailFixture({ offer_state: state, profile_snapshot: { offer_state: state } }),
    );

    render(<AdvisorReviewPanel reviewId="r-1" />);

    const badge = await screen.findByText(label);
    expect(badge).toHaveClass(tone);
  });

  it("hàng cũ không có offer_state rơi về badge xám", async () => {
    fetchReviewDetail.mockResolvedValue(
      detailFixture({ offer_state: null, profile_snapshot: null }),
    );

    render(<AdvisorReviewPanel reviewId="r-1" />);

    expect(await screen.findByText("Chưa rõ nút thắt")).toHaveClass("status-neutral");
  });
});

describe("AdvisorReviewPanel — cấp ưu đãi là tuỳ chọn (D12)", () => {
  it("duyệt nguyên trạng không cần chạm ưu đãi", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture());
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Duyệt nguyên trạng/ }));

    await waitFor(() => expect(approveReview).toHaveBeenCalledWith("r-1", undefined));
    expect(resolveReview).not.toHaveBeenCalled();
    expect(await screen.findByText(/Nội dung đã gửi tới phiên của khách/)).toBeInTheDocument();
  });

  it("khoá nút cấp ưu đãi khi hồ sơ không có chương trình khớp", async () => {
    fetchReviewDetail.mockResolvedValue(
      detailFixture({ matched_promotions: [], profile_snapshot: { offer_state: "NONE_BOTTLENECK" } }),
    );

    render(<AdvisorReviewPanel reviewId="r-1" />);

    expect(await screen.findByRole("button", { name: /Cấp ưu đãi/ })).toBeDisabled();
  });

  it("cấp ưu đãi trong biên thì gửi kèm gói điều chỉnh qua /resolve", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture());
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Cấp ưu đãi/ }));
    await user.selectOptions(screen.getByLabelText("Chương trình ưu đãi"), "KM-01");
    await user.type(screen.getByLabelText("Giá trị (VND)"), "3000000");
    await user.click(screen.getByRole("button", { name: /Duyệt & cấp ưu đãi/ }));

    await waitFor(() => expect(resolveReview).toHaveBeenCalled());
    expect(resolveReview.mock.calls[0][1]).toMatchObject({
      status: "APPROVED",
      handoff_requested: false,
      offer_adjustment: {
        promotion_code: "KM-01",
        promotion_type: "FIXED_DISCOUNT",
        adjustment_type: "VND",
        amount_vnd: 3_000_000,
        new_value: "3000000",
      },
    });
  });

  it("vượt biên thì cảnh báo và khoá nút gửi", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture());
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Cấp ưu đãi/ }));
    await user.selectOptions(screen.getByLabelText("Chương trình ưu đãi"), "KM-01");
    await user.type(screen.getByLabelText("Giá trị (VND)"), "9000000");

    expect(screen.getByText(/Giá trị vượt biên độ cho phép/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Duyệt & cấp ưu đãi/ })).toBeDisabled();
    expect(screen.getByLabelText("Giá trị (VND)")).toHaveAttribute("max", "5000000");
  });

  it("khoá hẳn field khi loại ưu đãi chưa có biên độ ADMIN cấu hình", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture({ adjustment_policies: [] }));
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Cấp ưu đãi/ }));
    await user.selectOptions(screen.getByLabelText("Chương trình ưu đãi"), "KM-01");

    expect(
      screen.getByText(/Chưa có biên độ ADMIN cấu hình cho loại ưu đãi này/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Giá trị (VND)")).toBeDisabled();
    expect(screen.getByRole("button", { name: /Duyệt & cấp ưu đãi/ })).toBeDisabled();
  });
});

describe("AdvisorReviewPanel — chuyển tư vấn trực tiếp (T19)", () => {
  it("từ chối kèm checkbox gửi handoff_requested=true", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture());
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByLabelText("Chuyển tư vấn trực tiếp"));
    await user.click(screen.getByRole("button", { name: /Từ chối/ }));

    await waitFor(() => expect(resolveReview).toHaveBeenCalled());
    expect(resolveReview.mock.calls[0][1]).toMatchObject({
      status: "REJECTED",
      handoff_requested: true,
      offer_adjustment: null,
    });
    expect(rejectReview).not.toHaveBeenCalled();
    expect(await screen.findByText(/liên hệ trực tiếp/)).toBeInTheDocument();
  });

  it("từ chối không tick checkbox đi đường /reject cũ", async () => {
    const user = userEvent.setup();
    fetchReviewDetail.mockResolvedValue(detailFixture());
    render(<AdvisorReviewPanel reviewId="r-1" />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Từ chối/ }));

    await waitFor(() => expect(rejectReview).toHaveBeenCalledWith("r-1"));
    expect(resolveReview).not.toHaveBeenCalled();
  });
});

describe("AdvisorReviewPanel — lỗi API", () => {
  it("API hỏng thì hiện trạng thái lỗi thay vì vỡ màn", async () => {
    fetchReviewDetail.mockRejectedValue(new Error("boom"));

    render(<AdvisorReviewPanel reviewId="r-1" />);

    expect(await screen.findByText("Không thực hiện được thao tác duyệt.")).toBeInTheDocument();
  });
});
