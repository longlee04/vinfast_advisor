// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdvisorQueueTable } from "@/components/advisor/advisor-queue-table";
import { LAST_PENDING_COUNT_KEY } from "@/components/advisor/advisor-queue-poll";
import type { BottleneckSignal, OfferState, QueueEntry } from "@/types/agent";

const { fetchBottleneckSignals, fetchReviews } = vi.hoisted(() => ({
  fetchBottleneckSignals: vi.fn(),
  fetchReviews: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchBottleneckSignals, fetchReviews };
});

let visibility: DocumentVisibilityState = "visible";
const storageValues = new Map<string, string>();
const testStorage: Storage = {
  get length() { return storageValues.size; },
  clear: () => storageValues.clear(),
  getItem: (key) => storageValues.get(key) ?? null,
  key: (index) => [...storageValues.keys()][index] ?? null,
  removeItem: (key) => { storageValues.delete(key); },
  setItem: (key, value) => { storageValues.set(key, value); },
};

function entryFixture(overrides: Partial<QueueEntry> = {}): QueueEntry {
  return {
    review_id: "11111111-1111-1111-1111-111111111111",
    session_id: "s-1",
    run_id: "run-1",
    status: "PENDING",
    content: "Ban nhap tu API",
    claimed_by: null,
    lease_expires_at: null,
    created_at: "2026-08-19T03:00:00Z",
    profile_snapshot: null,
    offer_state: "BOTTLENECK_OFFER_AVAILABLE",
    age_minutes: 5,
    handoff_requested: false,
    offer_suggestion_ignored: false,
    ...overrides,
  };
}

function entryWithOfferState(offerState: OfferState, index: number): QueueEntry {
  return entryFixture({
    review_id: `r-${index}`,
    content: `Ban nhap ${index}`,
    offer_state: offerState,
  });
}

function signalFixture(overrides: Partial<BottleneckSignal> = {}): BottleneckSignal {
  return {
    signal_id: "22222222-2222-2222-2222-222222222222",
    session_id: "s-2",
    client_turn_id: "turn-2",
    anchor_client_turn_id: "turn-1",
    label: "PRICE",
    evidence_quote: "Giá này vượt ngân sách của tôi",
    status: "PENDING",
    claimed_by: null,
    claimed_at: null,
    lease_expires_at: null,
    advisor_id: null,
    decided_at: null,
    created_at: "2026-08-19T03:00:00Z",
    updated_at: "2026-08-19T03:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  visibility = "visible";
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    get: () => visibility,
  });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: testStorage });
  globalThis.localStorage.clear();
  document.title = "Hang doi";
  fetchReviews.mockResolvedValue([]);
  fetchBottleneckSignals.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

function fireVisibilityChange(next: DocumentVisibilityState): void {
  visibility = next;
  document.dispatchEvent(new Event("visibilitychange"));
}

describe("AdvisorQueueTable — dữ liệu từ API thật", () => {
  it("render bảng từ response API, không phải dữ liệu cứng", async () => {
    fetchReviews.mockResolvedValue([
      entryWithOfferState("NONE_BOTTLENECK", 1),
      entryWithOfferState("BOTTLENECK_NO_OFFER", 2),
      entryWithOfferState("BOTTLENECK_OFFER_AVAILABLE", 3),
    ]);

    render(<AdvisorQueueTable />);

    expect(await screen.findByText("Ban nhap 1")).toBeInTheDocument();
    expect(fetchReviews).toHaveBeenCalledWith({ status: "pending" });
    // D11 — ba badge khác nhau, phân biệt bằng cả chữ lẫn màu.
    expect(screen.getByText("Chưa rõ nút thắt")).toHaveClass("status-neutral");
    expect(screen.getByText("Có nhu cầu — chưa có chương trình")).toHaveClass("status-warning");
    expect(screen.getByText("Có ưu đãi đề xuất")).toHaveClass("status-success");
  });

  it("offer_state null (hàng cũ) rơi về badge xám", async () => {
    fetchReviews.mockResolvedValue([entryFixture({ offer_state: null })]);

    render(<AdvisorQueueTable />);

    expect(await screen.findByText("Chưa rõ nút thắt")).toHaveClass("status-neutral");
  });

  it("cờ tuổi: >30 phút vàng, >60 phút đỏ, thiếu age_minutes thì để trống", async () => {
    fetchReviews.mockResolvedValue([
      entryFixture({ review_id: "r-a", content: "Moi vao", age_minutes: 10 }),
      entryFixture({ review_id: "r-b", content: "Hoi lau", age_minutes: 45 }),
      entryFixture({ review_id: "r-c", content: "Qua han", age_minutes: 95 }),
      entryFixture({ review_id: "r-d", content: "Khong ro", age_minutes: null }),
    ]);

    render(<AdvisorQueueTable />);

    await screen.findByText("Moi vao");
    expect(screen.getByText("10 phút")).not.toHaveClass("status-badge");
    expect(screen.getByText("45 phút")).toHaveClass("status-warning");
    expect(screen.getByText("1 giờ 35 phút")).toHaveClass("status-danger");
    const emptyAgeRow = screen.getByText("Khong ro").closest("tr") as HTMLElement;
    const ageCell = within(emptyAgeRow)
      .getAllByRole("cell")
      .find((cell) => cell.dataset.label === "Tuổi");
    expect(ageCell).toHaveTextContent("—");
  });

  it("render cờ handoff_requested và offer_suggestion_ignored", async () => {
    fetchReviews.mockResolvedValue([
      entryFixture({ handoff_requested: true, offer_suggestion_ignored: true }),
    ]);

    render(<AdvisorQueueTable />);

    expect(await screen.findByText("Chuyển tư vấn trực tiếp")).toBeInTheDocument();
    expect(screen.getByText("Bỏ qua ưu đãi đề xuất")).toBeInTheDocument();
  });

  it("chuyển tab gọi lại API với status tương ứng", async () => {
    const user = userEvent.setup();
    fetchReviews.mockResolvedValue([entryFixture({ status: "APPROVED" })]);

    render(<AdvisorQueueTable />);
    await screen.findByText("Ban nhap tu API");

    await user.click(screen.getByRole("button", { name: /Đã duyệt/ }));

    await waitFor(() => {
      expect(fetchReviews).toHaveBeenCalledWith({ status: "approved" });
    });
    expect(await screen.findByText("Đã duyệt", { selector: ".status-badge" })).toBeInTheDocument();
  });

  it("phân biệt signal xác nhận nút thắt với bản nháp nội dung", async () => {
    fetchReviews.mockResolvedValue([entryFixture()]);
    fetchBottleneckSignals.mockResolvedValue([signalFixture()]);

    render(<AdvisorQueueTable />);

    expect(await screen.findByText("Xác nhận nút thắt")).toBeInTheDocument();
    expect(screen.getByText("Duyệt nội dung")).toBeInTheDocument();
    expect(screen.getByText("Giá này vượt ngân sách của tôi")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Xác nhận/ })).toHaveAttribute(
      "href",
      "/advisor/bottleneck-signals/22222222-2222-2222-2222-222222222222",
    );
  });

  it("API rỗng thì hiện empty state theo tab", async () => {
    render(<AdvisorQueueTable />);

    expect(await screen.findByText("Không có mục chờ duyệt")).toBeInTheDocument();
  });

  it("API lỗi thì hiện error state và bấm Thử lại tải lại được", async () => {
    const user = userEvent.setup();
    fetchReviews.mockRejectedValueOnce(new Error("boom"));

    render(<AdvisorQueueTable />);
    expect(await screen.findByText("Không tải được hàng đợi duyệt.")).toBeInTheDocument();

    fetchReviews.mockResolvedValue([entryFixture()]);
    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    expect(await screen.findByText("Ban nhap tu API")).toBeInTheDocument();
  });
});

describe("AdvisorQueueTable — polling 30s + badge mục mới", () => {
  it("sau 30s thấy mục mới thì hiện toast và badge số trên tiêu đề tab", async () => {
    vi.useFakeTimers();
    globalThis.localStorage.setItem(LAST_PENDING_COUNT_KEY, "1");
    fetchReviews.mockResolvedValue([entryFixture()]);

    render(<AdvisorQueueTable />);
    await act(async () => {});

    fetchReviews.mockResolvedValue([
      entryFixture({ review_id: "r-1" }),
      entryFixture({ review_id: "r-2" }),
      entryFixture({ review_id: "r-3" }),
    ]);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    expect(screen.getByRole("status")).toHaveTextContent("Có 2 mục mới trong hàng chờ");
    expect(document.title).toBe("(3) Advisor Queue");
    expect(globalThis.localStorage.getItem(LAST_PENDING_COUNT_KEY)).toBe("3");
  });

  it("số mục không đổi thì không toast, không đổi tiêu đề", async () => {
    vi.useFakeTimers();
    globalThis.localStorage.setItem(LAST_PENDING_COUNT_KEY, "1");
    fetchReviews.mockResolvedValue([entryFixture()]);

    render(<AdvisorQueueTable />);
    await act(async () => {});
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(document.title).toBe("Hang doi");
  });

  it("tab ẩn thì dừng poll, hiện lại thì poll tiếp", async () => {
    vi.useFakeTimers();
    fetchReviews.mockResolvedValue([entryFixture()]);

    render(<AdvisorQueueTable />);
    await act(async () => {});
    const afterFirstLoad = fetchReviews.mock.calls.length;

    act(() => {
      fireVisibilityChange("hidden");
    });
    await act(async () => {
      vi.advanceTimersByTime(120_000);
    });
    expect(fetchReviews).toHaveBeenCalledTimes(afterFirstLoad);

    await act(async () => {
      fireVisibilityChange("visible");
    });
    expect(fetchReviews.mock.calls.length).toBeGreaterThan(afterFirstLoad);
  });

  it("unmount thì dọn interval, không gọi API nữa", async () => {
    vi.useFakeTimers();
    fetchReviews.mockResolvedValue([entryFixture()]);

    const view = render(<AdvisorQueueTable />);
    await act(async () => {});
    view.unmount();
    const afterUnmount = fetchReviews.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(120_000);
    });

    expect(fetchReviews).toHaveBeenCalledTimes(afterUnmount);
  });

  it("poll lỗi 3 lần liên tiếp thì im lặng dừng, bảng vẫn nguyên", async () => {
    vi.useFakeTimers();
    fetchReviews.mockResolvedValueOnce([entryFixture()]);

    render(<AdvisorQueueTable />);
    await act(async () => {});

    fetchReviews.mockRejectedValue(new Error("500"));
    for (let index = 0; index < 5; index += 1) {
      await act(async () => {
        vi.advanceTimersByTime(30_000);
      });
    }

    // Đúng 3 lần thử rồi thôi — không spam thêm, không dựng error state.
    expect(fetchReviews).toHaveBeenCalledTimes(4);
    expect(screen.getByText("Ban nhap tu API")).toBeInTheDocument();
    expect(screen.queryByText("Không tải được hàng đợi duyệt.")).not.toBeInTheDocument();
  });
});
