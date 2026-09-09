// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BottleneckSignalPanel } from "@/components/advisor/bottleneck-signal-panel";
import { AgentApiError } from "@/lib/api/agent";
import type { BottleneckSignalDetail } from "@/types/agent";

const {
  claimBottleneckSignal,
  fetchBottleneckSignalDetail,
  sendBottleneckSignalOffer,
  sendBottleneckSignalVerdict,
} = vi.hoisted(() => ({
  claimBottleneckSignal: vi.fn(),
  fetchBottleneckSignalDetail: vi.fn(),
  sendBottleneckSignalOffer: vi.fn(),
  sendBottleneckSignalVerdict: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return {
    ...actual,
    claimBottleneckSignal,
    fetchBottleneckSignalDetail,
    sendBottleneckSignalOffer,
    sendBottleneckSignalVerdict,
  };
});

function detailFixture(overrides: Partial<BottleneckSignalDetail> = {}): BottleneckSignalDetail {
  return {
    signal_id: "signal-1",
    session_id: "session-1",
    client_turn_id: "turn-2",
    anchor_client_turn_id: "turn-1",
    label: "PRICE",
    evidence_quote: "Giá này hơi vượt ngân sách của tôi",
    status: "PENDING",
    claimed_by: null,
    claimed_at: null,
    lease_expires_at: null,
    advisor_id: null,
    decided_at: null,
    created_at: "2026-08-19T03:00:00Z",
    updated_at: "2026-08-19T03:00:00Z",
    matched_promotions: [],
    adjustment_policies: [],
    ...overrides,
  };
}

const correctDetail = detailFixture({
  status: "CORRECT",
  claimed_by: "advisor-1",
  lease_expires_at: "2026-08-19T03:15:00Z",
  matched_promotions: [{ promotion_code: "KM-01", promotion_type: "FIXED_DISCOUNT" }],
  adjustment_policies: [
    { promotion_type: "FIXED_DISCOUNT", adjust_min_vnd: 1_000_000, adjust_max_vnd: 5_000_000 },
  ],
});

beforeEach(() => {
  fetchBottleneckSignalDetail.mockResolvedValue(detailFixture());
  claimBottleneckSignal.mockResolvedValue(detailFixture({ claimed_by: "advisor-1" }));
  sendBottleneckSignalVerdict.mockResolvedValue(correctDetail);
  sendBottleneckSignalOffer.mockResolvedValue({ signal_id: "signal-1" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("BottleneckSignalPanel", () => {
  it("claim rồi xác nhận đúng; chỉ mở picker sau server refetch CORRECT", async () => {
    const user = userEvent.setup();
    fetchBottleneckSignalDetail.mockResolvedValueOnce(detailFixture()).mockResolvedValueOnce(correctDetail);
    render(<BottleneckSignalPanel signalId="signal-1" />);

    expect(await screen.findByText("Giá này hơi vượt ngân sách của tôi")).toBeInTheDocument();
    expect(screen.queryByLabelText("Chương trình ưu đãi")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Nhận xử lý" }));
    await user.click(screen.getByRole("button", { name: "Đúng" }));

    expect(await screen.findByLabelText("Chương trình ưu đãi")).toBeInTheDocument();
    expect(fetchBottleneckSignalDetail).toHaveBeenCalledTimes(2);
  });

  it("verdict sai giữ picker đóng và offer API không được gọi", async () => {
    const user = userEvent.setup();
    sendBottleneckSignalVerdict.mockResolvedValue(detailFixture({ status: "INCORRECT" }));
    render(<BottleneckSignalPanel signalId="signal-1" />);
    await screen.findByText("Giá này hơi vượt ngân sách của tôi");

    await user.click(screen.getByRole("button", { name: "Nhận xử lý" }));
    await user.click(screen.getByRole("button", { name: "Sai" }));

    expect(await screen.findByText(/đã đánh dấu sai/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Chương trình ưu đãi")).not.toBeInTheDocument();
    expect(sendBottleneckSignalOffer).not.toHaveBeenCalled();
  });

  it("vượt biên khóa gửi; giá trị hợp lệ chỉ submit một lần khi double-click", async () => {
    const user = userEvent.setup();
    fetchBottleneckSignalDetail.mockResolvedValue(correctDetail);
    sendBottleneckSignalOffer.mockReturnValue(new Promise(() => undefined));
    render(<BottleneckSignalPanel signalId="signal-1" />);

    await user.selectOptions(await screen.findByLabelText("Chương trình ưu đãi"), "KM-01");
    await user.type(screen.getByLabelText("Giá trị (VND)"), "9000000");
    expect(screen.getByText(/Giá trị vượt biên độ/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Gửi ưu đãi" })).toBeDisabled();

    await user.clear(screen.getByLabelText("Giá trị (VND)"));
    await user.type(screen.getByLabelText("Giá trị (VND)"), "3000000");
    const submit = screen.getByRole("button", { name: "Gửi ưu đãi" });
    await user.dblClick(submit);

    expect(sendBottleneckSignalOffer).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["signal_not_claimable_or_lease_invalid", 409, "Signal đang do tư vấn viên khác xử lý hoặc lease đã hết hạn."],
    ["promotion_expired", 409, "Chương trình ưu đãi đã hết hiệu lực — chọn chương trình khác."],
    ["adjustment_out_of_bounds", 422, "Ưu đãi vượt biên độ ADMIN cấu hình — chỉnh lại trong biên rồi gửi."],
  ])("lỗi %s hiện tiếng Việt recoverable", async (code, status, message) => {
    const user = userEvent.setup();
    if (code === "signal_not_claimable_or_lease_invalid") {
      claimBottleneckSignal.mockRejectedValue(new AgentApiError(code, status));
      render(<BottleneckSignalPanel signalId="signal-1" />);
      await user.click(await screen.findByRole("button", { name: "Nhận xử lý" }));
    } else {
      fetchBottleneckSignalDetail.mockResolvedValue(correctDetail);
      sendBottleneckSignalOffer.mockRejectedValue(new AgentApiError(code, status));
      render(<BottleneckSignalPanel signalId="signal-1" />);
      await user.selectOptions(await screen.findByLabelText("Chương trình ưu đãi"), "KM-01");
      await user.type(screen.getByLabelText("Giá trị (VND)"), "3000000");
      await user.click(screen.getByRole("button", { name: "Gửi ưu đãi" }));
    }

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Thử lại|Nhận xử lý|Gửi ưu đãi/ })).toBeEnabled();
  });

  it("lỗi tải 403 cho phép thử lại", async () => {
    const user = userEvent.setup();
    fetchBottleneckSignalDetail.mockRejectedValueOnce(new AgentApiError("forbidden", 403));
    render(<BottleneckSignalPanel signalId="signal-1" />);

    expect(await screen.findByText("Tài khoản này không có quyền xác nhận nút thắt.")).toBeInTheDocument();
    fetchBottleneckSignalDetail.mockResolvedValue(detailFixture());
    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    await waitFor(() => expect(screen.getByText("Giá này hơi vượt ngân sách của tôi")).toBeInTheDocument());
  });
});
