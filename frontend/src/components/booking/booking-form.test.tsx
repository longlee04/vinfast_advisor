// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookingForm } from "@/components/booking/booking-form";
import { buildScheduledAt, defaultBookingDate } from "@/components/booking/booking-time";
import * as assignmentsApi from "@/lib/api/assignments";
import { DemoStoreProvider } from "@/store/demo-store";

const { push } = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push }),
}));

vi.mock("@/store/auth-store", () => ({
  useAuth: () => ({
    user: { id: "u1", email: "khach@gmail.com", role: "customer", state: "active" },
    profile: { full_name: "Nguyễn Văn A", phone_number: "0912345678" },
  }),
}));

// Mock bản đồ: Leaflet không sống nổi trong jsdom, và form chỉ render map khi
// showroom có toạ độ — test toạ độ dùng vai đóng thế này.
vi.mock("@/components/consultation/tour-map", () => ({
  default: ({ showrooms }: { showrooms: readonly { name: string }[] }) => (
    <div data-testid="booking-map">{showrooms.map((s) => s.name).join(",")}</div>
  ),
}));

const OPTIONS = {
  vehicles: [
    {
      id: "v1",
      name: "VinFast VF 6 Plus",
      model: "VF 6",
      variant: "Plus",
      vehicle_type: "car",
      image_url: "/media/vf6.webp",
    },
  ],
  showrooms: [{ id: "s1", name: "VinFast Times City", address: "458 Minh Khai", city: "Hà Nội" }],
};

//: Bộ options CÓ toạ độ cho các test bản đồ/GPS: Times City (HN) và Thảo Điền (SG).
const OPTIONS_WITH_COORDS = {
  vehicles: OPTIONS.vehicles,
  showrooms: [
    { id: "s1", name: "VinFast Times City", address: "458 Minh Khai", city: "Hà Nội", lat: 20.995, lng: 105.868 },
    { id: "s2", name: "VinFast Thảo Điền", address: "12 Quốc Hương", city: "TP HCM", lat: 10.803, lng: 106.73 },
  ],
};

function renderForm() {
  return render(
    <DemoStoreProvider>
      <BookingForm />
    </DemoStoreProvider>,
  );
}

describe("BookingForm", () => {
  beforeEach(() => cleanup());
  afterEach(() => {
    push.mockClear();
    vi.restoreAllMocks();
  });

  it("fetch options lỗi: hiện khối lỗi + nút thử lại, submit bị khoá vì chưa có xe", async () => {
    const fetchOptions = vi
      .spyOn(assignmentsApi, "fetchBookingOptions")
      .mockRejectedValueOnce(new Error("network"))
      .mockResolvedValueOnce(OPTIONS);

    renderForm();

    expect(await screen.findByText(/không tải được danh sách xe\/showroom/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /xác nhận đặt lịch lái thử/i })).toBeDisabled();

    // Nút thử lại gọi lại đúng API; thành công thì form dùng được.
    await userEvent.click(screen.getByRole("button", { name: /thử lại/i }));
    await waitFor(() => expect(fetchOptions).toHaveBeenCalledTimes(2));
    // Tên xe hiện ở cả <option> lẫn thẻ tóm tắt — neo vào heading tóm tắt.
    expect(await screen.findByRole("heading", { name: "VinFast VF 6 Plus" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /xác nhận đặt lịch lái thử/i })).toBeEnabled();
  });

  it("đặt thành công: gửi giờ VN (+07:00) và đẩy dữ liệu THẬT sang /test-drive/success qua query", async () => {
    vi.spyOn(assignmentsApi, "fetchBookingOptions").mockResolvedValue(OPTIONS);
    const create = vi
      .spyOn(assignmentsApi, "createTestDriveBooking")
      .mockResolvedValue({} as never);

    renderForm();
    expect(await screen.findByRole("heading", { name: "VinFast VF 6 Plus" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /xác nhận đặt lịch lái thử/i }));

    const expectedDate = defaultBookingDate();
    await waitFor(() => expect(create).toHaveBeenCalledTimes(1));
    // 14:30 khách chọn phải là 14:30 GIỜ VN, không phải 14:30 UTC.
    expect(create.mock.calls[0][0].scheduled_at).toBe(buildScheduledAt(expectedDate, "14:30"));

    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    const target = push.mock.calls[0][0] as string;
    expect(target.startsWith("/test-drive/success?")).toBe(true);
    const params = new URLSearchParams(target.split("?")[1]);
    expect(params.get("vehicle")).toBe("VinFast VF 6 Plus");
    expect(params.get("showroom")).toBe("VinFast Times City");
    expect(params.get("date")).toBe(expectedDate);
    expect(params.get("time")).toBe("14:30");
  });

  it("chọn dòng xe bằng MỘT Ô select (Sếp 2026-08-31), xe đầu được chọn sẵn", async () => {
    vi.spyOn(assignmentsApi, "fetchBookingOptions").mockResolvedValue(OPTIONS);
    renderForm();

    const select = await screen.findByRole("combobox");
    expect(select).toHaveValue("v1");
    expect(screen.getByRole("option", { name: "VinFast VF 6 Plus" })).toBeInTheDocument();
  });

  it("hồ sơ đã đủ tên + SĐT thì KHÔNG bắt gõ lại — không còn ô nhập liên hệ", async () => {
    vi.spyOn(assignmentsApi, "fetchBookingOptions").mockResolvedValue(OPTIONS);
    renderForm();
    await screen.findByRole("combobox");

    expect(screen.queryByLabelText(/họ và tên/i)).toBeNull();
    expect(screen.queryByLabelText(/số điện thoại/i)).toBeNull();
    // Tóm tắt vẫn nói rõ đặt bằng liên hệ nào để khách yên tâm.
    expect(screen.getByText(/Nguyễn Văn A · 0912345678/)).toBeInTheDocument();
  });

  it("bấm 'Dùng vị trí của tôi': showroom GẦN NHẤT được chọn, bản đồ hiện, danh sách sắp gần trước", async () => {
    vi.spyOn(assignmentsApi, "fetchBookingOptions").mockResolvedValue(OPTIONS_WITH_COORDS);
    // GPS giả đứng ở TP HCM → Thảo Điền phải thắng Times City.
    Object.defineProperty(window.navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition: (ok: (p: { coords: { latitude: number; longitude: number } }) => void) =>
          ok({ coords: { latitude: 10.8, longitude: 106.72 } }),
      },
    });

    renderForm();
    await screen.findByRole("combobox");
    // Bản đồ nạp qua next/dynamic (bất đồng bộ) — phải chờ, getByTestId ăn ngay
    // là flaky theo thứ tự chạy test trong file.
    expect(await screen.findByTestId("booking-map")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /dùng vị trí của tôi/i }));

    const thaoDien = await screen.findByRole("button", { name: /VinFast Thảo Điền/ });
    await waitFor(() => expect(thaoDien).toHaveAttribute("aria-pressed", "true"));
    // Sắp gần trước: thẻ Thảo Điền đứng trước Times City trong danh sách.
    const cards = screen.getAllByRole("button", { name: /VinFast (Thảo Điền|Times City)/ });
    expect(cards[0]).toHaveAccessibleName(/Thảo Điền/);
  });
});
