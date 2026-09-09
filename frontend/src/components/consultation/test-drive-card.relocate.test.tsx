// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TestDriveCard } from "@/components/consultation/test-drive-card";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

/**
 * Đổi vị trí ngay TRÊN thẻ đã có showroom (Sếp 2026-08-31).
 *
 * Thẻ đã ra danh sách showroom + giờ vẫn phải cho khách đổi vị trí / tìm
 * showroom khác ngay trên thẻ: bấm "Đổi vị trí" là quay về khối xin vị trí
 * (tự xin GPS lại như thẻ `needs_location`, fallback ô gõ quận/huyện), kết
 * quả mới THAY danh sách tại chỗ qua `/agent/test-drive/options`.
 */

const { fetchTestDriveOptions } = vi.hoisted(() => ({
  fetchTestDriveOptions: vi.fn(),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return { ...actual, fetchTestDriveOptions };
});

const NAY_9H = "2026-08-31T09:00:00+07:00";
const CU: TestDriveCardData = {
  vehicle_id: "veh-vf8",
  vehicle_name: "VinFast VF 8",
  needs_location: false,
  showrooms: [{ showroom_id: "sr-lb", name: "VinFast Long Biên", address: "Số 1 Nguyễn Văn Cừ", distance_label: "2,1 km" }],
  days: [{ date: "2026-08-31", label: "Hôm nay 31/08", times: [{ scheduled_at: NAY_9H, label: "9h00" }] }],
  options: [{ showroom_id: "sr-lb", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Long Biên" }],
  default_showroom_id: "sr-lb",
  default_date: "2026-08-31",
};

const MOI: TestDriveCardData = {
  ...CU,
  showrooms: [{ showroom_id: "sr-cg", name: "VinFast Cầu Giấy", address: "Trần Thái Tông", distance_label: "1,2 km" }],
  options: [{ showroom_id: "sr-cg", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Cầu Giấy" }],
  default_showroom_id: "sr-cg",
};

function stubGeolocation(impl: (ok: PositionCallback, fail: PositionErrorCallback) => void): void {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: vi.fn(impl) },
  });
}

/** Cha tối giản: giữ thẻ trong state và THAY tại chỗ khi thẻ báo lên — đúng
 *  đường `onCardReplaced` mà consultation-flow dùng. */
function Harness({ initial }: { initial: TestDriveCardData }) {
  const [card, setCard] = useState(initial);
  return <TestDriveCard card={card} onCardReplaced={(next) => setCard(next)} onConfirm={vi.fn()} sessionId="s1" />;
}

describe("TestDriveCard đổi vị trí ngay trên thẻ đã có showroom", () => {
  beforeEach(() => {
    fetchTestDriveOptions.mockReset();
  });
  afterEach(() => {
    cleanup();
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
  });

  it("bấm 'Đổi vị trí' → khối locate hiện, GPS thành công → gọi lại options và render showroom MỚI tại chỗ", async () => {
    const user = userEvent.setup();
    stubGeolocation((ok) => ok({ coords: { latitude: 21.03, longitude: 105.79 } } as GeolocationPosition));
    fetchTestDriveOptions.mockResolvedValueOnce({ test_drive_card: MOI, quick_replies: [] });
    render(<Harness initial={CU} />);

    expect(screen.getByText("VinFast Long Biên")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));

    // Kết quả mới thay danh sách TẠI CHỖ: showroom cũ nhường chỗ showroom mới,
    // vẫn là một thẻ với đủ cột giờ + nút Đặt lịch.
    expect(await screen.findByText("VinFast Cầu Giấy")).toBeInTheDocument();
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "s1",
      vehicleId: "veh-vf8",
      latitude: 21.03,
      longitude: 105.79,
    });
    expect(screen.queryByText("VinFast Long Biên")).toBeNull();
    expect(screen.getByRole("button", { name: "Đặt lịch" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Quận/huyện, tỉnh")).toBeNull();
  });

  it("GPS bị từ chối → ô gõ quận/huyện bày ra ngay trong thẻ, danh sách cũ tạm ẩn, có đường lùi", async () => {
    const user = userEvent.setup();
    stubGeolocation((_ok, fail) => fail({ code: 1, PERMISSION_DENIED: 1 } as GeolocationPositionError));
    render(<Harness initial={CU} />);

    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));

    expect(await screen.findByRole("status")).toHaveTextContent("từ chối quyền vị trí");
    expect(screen.getByLabelText("Quận/huyện, tỉnh")).toBeEnabled();
    expect(fetchTestDriveOptions).not.toHaveBeenCalled();
    expect(screen.queryByText("VinFast Long Biên")).toBeNull();
    // Đường lùi: chưa tìm được chỗ mới thì vẫn quay về danh sách cũ được.
    expect(screen.getByRole("button", { name: "Giữ danh sách showroom hiện tại" })).toBeEnabled();
  });

  it("gõ quận/huyện rồi Tìm trong khối đổi vị trí → gọi options với location_text và thay showroom mới", async () => {
    const user = userEvent.setup();
    // jsdom không có geolocation → auto-GPS fail tức thì, fallback bày ra ngay.
    fetchTestDriveOptions.mockResolvedValueOnce({ test_drive_card: MOI, quick_replies: [] });
    render(<Harness initial={CU} />);

    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));
    await user.type(await screen.findByLabelText("Quận/huyện, tỉnh"), "Cầu Giấy, Hà Nội");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    await waitFor(() => expect(screen.getByText("VinFast Cầu Giấy")).toBeInTheDocument());
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "s1",
      vehicleId: "veh-vf8",
      locationText: "Cầu Giấy, Hà Nội",
    });
  });

  it("'Giữ danh sách showroom hiện tại' → quay về danh sách cũ, không gọi API", async () => {
    const user = userEvent.setup();
    render(<Harness initial={CU} />);

    await user.click(screen.getByRole("button", { name: "Đổi vị trí, tìm showroom khác" }));
    await user.click(await screen.findByRole("button", { name: "Giữ danh sách showroom hiện tại" }));

    expect(screen.getByText("VinFast Long Biên")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "9h00" })).toBeInTheDocument();
    expect(fetchTestDriveOptions).not.toHaveBeenCalled();
  });
});
