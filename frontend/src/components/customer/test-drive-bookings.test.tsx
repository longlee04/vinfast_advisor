import { render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { TestDriveBookings } from "@/components/customer/test-drive-bookings";
import * as bookingsApi from "@/lib/api/bookings";
import { BookingApiError } from "@/lib/api/bookings";

describe("TestDriveBookings", () => {
  it("renders the booking list from the API, newest first", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([
      {
        booking_id: "b1",
        customer_id: "c1",
        vehicle_id: "v1",
        vehicle_name: "VinFast VF 6 Eco",
        showroom: "VinFast Times City",
        scheduled_at: "2026-08-20T03:00:00Z",
        status: "REQUESTED",
        created_at: "2026-08-19T00:00:00Z",
      },
      {
        booking_id: "b2",
        customer_id: "c1",
        vehicle_id: "v2",
        vehicle_name: "VinFast VF 9",
        showroom: "VinFast Long Biên",
        scheduled_at: "2026-08-25T03:00:00Z",
        status: "CONFIRMED",
        created_at: "2026-08-20T00:00:00Z",
      },
    ]);

    render(<TestDriveBookings />);

    await waitFor(() => {
      expect(screen.getByText("VinFast VF 9")).toBeInTheDocument();
      expect(screen.getByText("VinFast VF 6 Eco")).toBeInTheDocument();
    });

    const items = screen.getAllByRole("heading", { level: 3 });
    expect(items[0]).toHaveTextContent("VinFast VF 9");
    expect(items[1]).toHaveTextContent("VinFast VF 6 Eco");

    expect(screen.getByText("Đã xác nhận")).toBeInTheDocument();
    expect(screen.getByText("Chờ xác nhận")).toBeInTheDocument();
  });

  it("empty state trỏ thẳng form /test-drive — không vòng qua màn chat", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);

    render(<TestDriveBookings />);

    await waitFor(() => {
      expect(screen.getByText("Bạn chưa có lịch lái thử nào.")).toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: /đặt lịch lái thử/i })).toHaveAttribute(
      "href",
      "/test-drive",
    );
  });

  it("shows an error state when the API call fails", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockRejectedValue(new BookingApiError("request_failed", 500));

    render(<TestDriveBookings />);

    await waitFor(() => {
      expect(screen.getByText(/không tải được lịch lái thử/i)).toBeInTheDocument();
    });
  });

  it("forwards the ref to the section so it can be focused/scrolled into view", async () => {
    vi.spyOn(bookingsApi, "fetchMyBookings").mockResolvedValue([]);
    const ref = createRef<HTMLElement>();

    render(<TestDriveBookings ref={ref} />);

    await waitFor(() => {
      expect(screen.getByText("Bạn chưa có lịch lái thử nào.")).toBeInTheDocument();
    });
    expect(ref.current).toBeInstanceOf(HTMLElement);
    expect(ref.current?.id).toBe("test-drive-bookings");
  });
});
