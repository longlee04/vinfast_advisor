// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TourPanel } from "@/components/consultation/tour-panel";
import type { TourPanelState } from "@/store/agent-session";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

/**
 * Đổi vị trí ngay trong PANEL bản đồ (Sếp 2026-08-31) — cùng flow với nút trên
 * thẻ lái thử: tự xin GPS lại, fallback ô gõ, kết quả mới báo lên `onLocated`
 * để consultation-flow đồng bộ ghim + khung giờ.
 */

const { fetchTestDriveAvailability, fetchTestDriveOptions } = vi.hoisted(() => ({
  fetchTestDriveAvailability: vi.fn(),
  fetchTestDriveOptions: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchTestDriveAvailability, fetchTestDriveOptions };
});

// Leaflet cần `window` thật — mock bản đồ về một ô đánh dấu (cùng cách
// tour-panel.test.tsx), bộ này chỉ canh flow đổi vị trí.
vi.mock("next/dynamic", () => ({
  default: () => (props: { showrooms: readonly { name: string }[] }) => (
    <div data-testid="tour-map">{props.showrooms.map((s) => s.name).join("|")}</div>
  ),
}));

const NAY_9H = "2026-08-31T09:00:00+07:00";
const CARD: TestDriveCardData = {
  vehicle_id: "v-5",
  vehicle_name: "VinFast VF 5",
  needs_location: false,
  showrooms: [{ showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "Cầu Giấy, HN", distance_label: "2,1 km" }],
  days: [{ date: "2026-08-31", label: "Hôm nay 31/08", times: [{ scheduled_at: NAY_9H, label: "9h00" }] }],
  options: [{ showroom_id: "sr-1", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Cầu Giấy" }],
  default_showroom_id: "sr-1",
  default_date: "2026-08-31",
};

const MAP: TourPanelState = {
  open: true,
  selectedShowroomId: "sr-1",
  navigate: {
    kind: "map",
    vehicle_id: "v-5",
    center: { lat: 21, lng: 105.8 },
    needs_location: false,
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "Cầu Giấy, HN", lat: 21.03, lng: 105.79, distance_km: 2.1 },
    ],
  },
};

function stubGeolocation(impl: (ok: PositionCallback, fail: PositionErrorCallback) => void): void {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: vi.fn(impl) },
  });
}

describe("TourPanel đổi vị trí ngay trong khối bản đồ", () => {
  beforeEach(() => {
    fetchTestDriveOptions.mockReset();
    fetchTestDriveAvailability.mockReset();
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
  });

  it("bấm 'Đổi vị trí' cạnh danh sách showroom → GPS thành công → gọi options và báo onLocated (đồng bộ ghim + giờ)", async () => {
    const user = userEvent.setup();
    const onLocated = vi.fn();
    stubGeolocation((ok) => ok({ coords: { latitude: 10.77, longitude: 106.7 } } as GeolocationPosition));
    const result = { test_drive_card: CARD, quick_replies: [], navigate: { kind: "map", vehicle_id: "v-5", center: null, needs_location: false, showrooms: [] } };
    fetchTestDriveOptions.mockResolvedValueOnce(result);
    render(
      <TourPanel
        onClose={vi.fn()}
        onLocated={onLocated}
        onSendMessage={vi.fn()}
        onShowroomPick={vi.fn()}
        panel={MAP}
        sessionId="s1"
        testDriveCard={CARD}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));

    await waitFor(() => expect(onLocated).toHaveBeenCalledTimes(1));
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "s1",
      vehicleId: "v-5",
      latitude: 10.77,
      longitude: 106.7,
    });
    expect(onLocated).toHaveBeenCalledWith(result, { latitude: 10.77, longitude: 106.7 });
    // Cờ relocate tự tắt sau khi tìm xong: danh sách showroom hiện lại.
    expect(await screen.findByRole("button", { name: /VinFast Cầu Giấy/ })).toBeInTheDocument();
  });

  it("GPS không có (jsdom) → khối locate thế chỗ danh sách + khung giờ, bày ô gõ quận/huyện; Tìm → onLocated", async () => {
    const user = userEvent.setup();
    const onLocated = vi.fn();
    const result = { test_drive_card: CARD, quick_replies: [] };
    fetchTestDriveOptions.mockResolvedValueOnce(result);
    render(
      <TourPanel
        onClose={vi.fn()}
        onLocated={onLocated}
        onSendMessage={vi.fn()}
        onShowroomPick={vi.fn()}
        panel={MAP}
        sessionId="s1"
        testDriveCard={CARD}
      />,
    );

    // Trước khi bấm: danh sách showroom, và mở khung giờ bằng cách bấm một
    // showroom (accordion — Sếp 2026-08-31, khối giờ không còn hiện sẵn).
    await user.click(screen.getByRole("button", { name: /VinFast Cầu Giấy/ }));
    expect(screen.getByRole("group", { name: "Đặt lịch lái thử tại showroom đang chọn" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));

    // Auto-GPS fail tức thì (không có geolocation) → fallback ô gõ ngay trong panel.
    expect(await screen.findByLabelText("Quận/huyện, tỉnh")).toBeEnabled();
    // Giờ của vị trí cũ tạm ẩn — không gài khách đặt nhầm showroom xa.
    expect(screen.queryByRole("group", { name: "Đặt lịch lái thử tại showroom đang chọn" })).toBeNull();
    expect(screen.queryByRole("button", { name: /VinFast Cầu Giấy/ })).toBeNull();

    await user.type(screen.getByLabelText("Quận/huyện, tỉnh"), "Quận 1, TP HCM");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    await waitFor(() => expect(onLocated).toHaveBeenCalledWith(result, { locationText: "Quận 1, TP HCM" }));
  });

  it("'Giữ danh sách showroom hiện tại' trong panel → quay về danh sách + khung giờ, không gọi API", async () => {
    const user = userEvent.setup();
    render(
      <TourPanel
        onClose={vi.fn()}
        onLocated={vi.fn()}
        onSendMessage={vi.fn()}
        onShowroomPick={vi.fn()}
        panel={MAP}
        sessionId="s1"
        testDriveCard={CARD}
      />,
    );

    // Mở khối giờ của Cầu Giấy trước — accordion giữ trạng thái qua lần đổi ý.
    await user.click(screen.getByRole("button", { name: /VinFast Cầu Giấy/ }));
    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));
    await user.click(await screen.findByRole("button", { name: "Giữ danh sách showroom hiện tại" }));

    expect(screen.getByRole("button", { name: /VinFast Cầu Giấy/ })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Đặt lịch lái thử tại showroom đang chọn" })).toBeInTheDocument();
    expect(fetchTestDriveOptions).not.toHaveBeenCalled();
  });
});
