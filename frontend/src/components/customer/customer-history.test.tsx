import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CustomerHistory } from "@/components/customer/customer-history";
import * as assignmentsApi from "@/lib/api/assignments";
import * as bookingsApi from "@/lib/api/bookings";
import { AuthProvider } from "@/store/auth-store";
import { DemoStoreProvider } from "@/store/demo-store";

// Component gọi router của Next; ngoài `next dev` thì không có router nào được
// gắn, nên `render` ném `invariant expected app router to be mounted`. Cùng
// khuôn mock đã dùng ở `agent-dock.test.tsx` và `consultation-flow.test.tsx`.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

describe("CustomerHistory", () => {
  it("renders dynamic summary metrics and activities from database", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);
    vi.spyOn(assignmentsApi, "fetchCustomerSummary").mockResolvedValue({
      session_count: 5,
      booking_count: 2,
      comparison_count: 3,
      approved_recommendations_count: 1,
      activities: [
        {
          id: "act-1",
          kind: "booking",
          date: "24/08/2026 · 14:30",
          title: "Đăng ký lái thử VinFast VF 6 Eco",
          description: "VinFast Times City · Lịch hẹn: 25/08/2026 lúc 10:00",
          status: "Chờ xác nhận",
          tone: "warning",
          icon: "calendar",
        },
        {
          id: "act-2",
          kind: "session",
          date: "23/08/2026 · 16:20",
          title: "Phiên tư vấn chọn ô tô điện",
          description: "Đã thực hiện 3 lượt hội thoại với Trợ lý AI.",
          status: "Đã hoàn thành",
          tone: "success",
          icon: "message",
        },
      ],
    });

    render(
      <AuthProvider>
        <DemoStoreProvider>
        <CustomerHistory />
      </DemoStoreProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();
      expect(screen.getByText("3")).toBeInTheDocument();
      expect(screen.getByText("Đăng ký lái thử VinFast VF 6 Eco")).toBeInTheDocument();
      expect(screen.getByText("Phiên tư vấn chọn ô tô điện")).toBeInTheDocument();
    });
  });

  it("handles empty activities gracefully", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);
    vi.spyOn(assignmentsApi, "fetchCustomerSummary").mockResolvedValue({
      session_count: 0,
      booking_count: 0,
      comparison_count: 0,
      approved_recommendations_count: 0,
      activities: [],
    });

    render(
      <AuthProvider>
        <DemoStoreProvider>
        <CustomerHistory />
      </DemoStoreProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Chưa có hoạt động nào được ghi nhận. Hãy bắt đầu phiên tư vấn hoặc đăng ký lái thử xe!")).toBeInTheDocument();
    });
  });

  it("focuses the test-drive bookings section when the summary tile is clicked", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);
    vi.spyOn(assignmentsApi, "fetchCustomerSummary").mockResolvedValue({
      session_count: 0,
      booking_count: 0,
      comparison_count: 0,
      approved_recommendations_count: 0,
      activities: [],
    });

    const user = userEvent.setup();
    render(
      <AuthProvider>
        <DemoStoreProvider>
          <CustomerHistory />
        </DemoStoreProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Bạn chưa có lịch lái thử nào.")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /xem lịch lái thử của bạn/i }));

    const section = document.getElementById("test-drive-bookings");
    expect(section).toHaveFocus();
  });
});


describe("CustomerHistory — phiên hết hạn (đợt vá UI 2026-08-31)", () => {
  it("401 từ summary: nói thẳng 'Phiên đã hết hạn' + mời đăng nhập lại, không im lặng", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);
    vi.spyOn(assignmentsApi, "fetchCustomerSummary").mockRejectedValue(
      new assignmentsApi.AssignmentApiError("unauthorized", 401),
    );

    render(
      <AuthProvider>
        <DemoStoreProvider>
          <CustomerHistory />
        </DemoStoreProvider>
      </AuthProvider>,
    );

    // Neo vào role=alert: chuỗi xuất hiện ở cả <strong> lẫn câu mô tả nên
    // findByText sẽ than "multiple elements".
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/phiên đã hết hạn/i);
    expect(screen.getByRole("link", { name: /đăng nhập lại/i })).toHaveAttribute("href", "/login?next=/account");
  });
});
