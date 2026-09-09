// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestDriveCard } from "@/components/consultation/test-drive-card";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

/**
 * MỘT thẻ cho cả xin vị trí lẫn chọn giờ (hợp đồng đợt 8, 2026-08-30).
 *
 * Thẻ tới với `needs_location=true` và rỗng showroom: chính thẻ xin vị trí
 * (GPS hoặc gõ quận/huyện), gọi `/agent/test-drive/options`, rồi báo cha THAY
 * thẻ tại chỗ. Bộ này canh: gọi đúng body, thay đúng thẻ, và mọi trạng thái
 * (đang tìm / lỗi / không thấy showroom) hiện NGAY TRONG thẻ.
 */

const { fetchTestDriveOptions } = vi.hoisted(() => ({
  fetchTestDriveOptions: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchTestDriveOptions };
});

const EMPTY: TestDriveCardData = {
  vehicle_id: "veh-vf8",
  vehicle_name: "VinFast VF 8",
  needs_location: true,
  showrooms: [],
  days: [],
  options: [],
  default_showroom_id: "",
  default_date: "",
};

const NAY_9H = "2026-08-30T09:00:00+07:00";
const FULL: TestDriveCardData = {
  vehicle_id: "veh-vf8",
  vehicle_name: "VinFast VF 8",
  needs_location: false,
  showrooms: [{ showroom_id: "sr-lb", name: "Long Biên", address: "Số 1 Nguyễn Văn Cừ", distance_label: "2,1 km" }],
  days: [{ date: "2026-08-30", label: "Hôm nay 30/08", times: [{ scheduled_at: NAY_9H, label: "9h00" }] }],
  options: [{ showroom_id: "sr-lb", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Long Biên" }],
  default_showroom_id: "sr-lb",
  default_date: "2026-08-30",
};

function stubGeolocation(impl: (ok: PositionCallback, fail: PositionErrorCallback) => void): void {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: vi.fn(impl) },
  });
}

describe("TestDriveCard xin vị trí ngay trong thẻ", () => {
  beforeEach(() => {
    fetchTestDriveOptions.mockReset();
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
  });

  it("needs_location + trình duyệt không có GPS: hiện ngay fallback nút GPS + ô gõ, chưa có cột showroom/giờ", () => {
    // jsdom không có `navigator.geolocation` → lượt tự xin GPS thất bại tức thì
    // và khối dự phòng phải bày ra liền, không bắt khách chờ gì cả.
    render(<TestDriveCard card={EMPTY} onConfirm={vi.fn()} sessionId="s1" />);

    const card = screen.getByRole("region", { name: "Chọn lịch lái thử" });
    expect(card).toHaveTextContent("Đặt lịch lái thử VinFast VF 8");
    expect(screen.getByRole("button", { name: /Dùng vị trí của tôi/ })).toBeInTheDocument();
    expect(screen.getByLabelText("Quận/huyện, tỉnh")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();
    expect(document.querySelector(".test-drive-card__times")).toBeNull();
  });

  it("thẻ hiện ra thì TỰ xin GPS: đang chờ toạ độ hiện 'Đang xác định vị trí…', CHƯA bày ô gõ", () => {
    // getCurrentPosition không gọi callback nào — mô phỏng khách đang nhìn
    // prompt quyền của trình duyệt.
    stubGeolocation(() => undefined);
    render(<TestDriveCard card={EMPTY} onConfirm={vi.fn()} sessionId="s1" />);

    expect(screen.getByRole("status")).toHaveTextContent("Đang xác định vị trí…");
    expect(screen.queryByLabelText("Quận/huyện, tỉnh")).toBeNull();
    expect(screen.queryByRole("button", { name: /Dùng vị trí của tôi/ })).toBeNull();
  });

  it("gõ quận/huyện rồi Tìm: gọi options với location_text và thay thẻ tại chỗ", async () => {
    const user = userEvent.setup();
    const onCardReplaced = vi.fn();
    fetchTestDriveOptions.mockResolvedValueOnce({
      test_drive_card: FULL,
      quick_replies: [{ label: "Giá lăn bánh", value: "Giá lăn bánh" }],
    });
    render(<TestDriveCard card={EMPTY} onCardReplaced={onCardReplaced} onConfirm={vi.fn()} sessionId="s1" />);

    await user.type(screen.getByLabelText("Quận/huyện, tỉnh"), "Long Biên, Hà Nội");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    await waitFor(() => expect(onCardReplaced).toHaveBeenCalledTimes(1));
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "s1",
      vehicleId: "veh-vf8",
      locationText: "Long Biên, Hà Nội",
    });
    expect(onCardReplaced).toHaveBeenCalledWith(FULL, [{ label: "Giá lăn bánh", value: "Giá lăn bánh" }]);
  });

  it("GPS thành công KHÔNG cần bấm gì: tự gọi options với toạ độ và thay thẻ tại chỗ", async () => {
    const onCardReplaced = vi.fn();
    stubGeolocation((ok) => ok({ coords: { latitude: 21.03, longitude: 105.85 } } as GeolocationPosition));
    fetchTestDriveOptions.mockResolvedValueOnce({ test_drive_card: FULL, quick_replies: [] });
    render(<TestDriveCard card={EMPTY} onCardReplaced={onCardReplaced} onConfirm={vi.fn()} sessionId="s1" />);

    await waitFor(() => expect(onCardReplaced).toHaveBeenCalledWith(FULL, []));
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "s1",
      vehicleId: "veh-vf8",
      latitude: 21.03,
      longitude: 105.85,
    });
  });

  it("GPS bị từ chối: nói ngay trong thẻ, không gọi API, fallback ô gõ bày ra", async () => {
    stubGeolocation((_ok, fail) => fail({ code: 1, PERMISSION_DENIED: 1 } as GeolocationPositionError));
    render(<TestDriveCard card={EMPTY} onConfirm={vi.fn()} sessionId="s1" />);

    expect(await screen.findByRole("status")).toHaveTextContent("từ chối quyền vị trí");
    expect(fetchTestDriveOptions).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Quận/huyện, tỉnh")).toBeEnabled();
    // Nút GPS vẫn còn trong fallback để khách đổi ý cấp quyền rồi thử lại.
    expect(screen.getByRole("button", { name: /Dùng vị trí của tôi/ })).toBeEnabled();
  });

  it("GPS quá hạn (timeout): rơi về fallback với lời mời gõ quận/huyện", async () => {
    stubGeolocation((_ok, fail) => fail({ code: 3, PERMISSION_DENIED: 1 } as GeolocationPositionError));
    render(<TestDriveCard card={EMPTY} onConfirm={vi.fn()} sessionId="s1" />);

    expect(await screen.findByRole("status")).toHaveTextContent("Không lấy được toạ độ GPS");
    expect(screen.getByLabelText("Quận/huyện, tỉnh")).toBeEnabled();
  });

  it("200 nhưng showrooms rỗng: giữ khối xin vị trí, hiện message của server, KHÔNG thay thẻ", async () => {
    const user = userEvent.setup();
    const onCardReplaced = vi.fn();
    fetchTestDriveOptions.mockResolvedValueOnce({
      test_drive_card: { ...FULL, showrooms: [], days: [], options: [] },
      quick_replies: [],
      message: "Chưa tìm thấy showroom quanh đây",
    });
    render(<TestDriveCard card={EMPTY} onCardReplaced={onCardReplaced} onConfirm={vi.fn()} sessionId="s1" />);

    await user.type(screen.getByLabelText("Quận/huyện, tỉnh"), "Xã Xa Lắm");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Chưa tìm thấy showroom quanh đây");
    expect(onCardReplaced).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Quận/huyện, tỉnh")).toBeEnabled();
  });

  it("API lỗi: báo trong thẻ và cho thử lại", async () => {
    const user = userEvent.setup();
    fetchTestDriveOptions.mockRejectedValueOnce(new Error("boom"));
    render(<TestDriveCard card={EMPTY} onConfirm={vi.fn()} sessionId="s1" />);

    await user.type(screen.getByLabelText("Quận/huyện, tỉnh"), "Cầu Giấy");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    expect(await screen.findByRole("status")).toHaveTextContent("chưa tìm được showroom");
    expect(screen.getByRole("button", { name: "Tìm showroom" })).toBeEnabled();
  });

  it("thẻ đủ showroom/giờ thì vẽ như cũ, không có khối xin vị trí", () => {
    render(<TestDriveCard card={FULL} onConfirm={vi.fn()} sessionId="s1" />);
    expect(screen.queryByLabelText("Quận/huyện, tỉnh")).toBeNull();
    expect(screen.getByRole("button", { name: "9h00" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Đặt lịch" })).toBeInTheDocument();
  });
});
