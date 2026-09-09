// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TestDriveCard } from "@/components/consultation/test-drive-card";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

const NAY_9H = "2026-08-28T09:00:00+07:00";
const NAY_10H = "2026-08-28T10:00:00+07:00";
const NAY_11H = "2026-08-28T11:00:00+07:00";
const MAI_9H = "2026-08-29T09:00:00+07:00";

/**
 * "Long Biên" còn 9h và 11h; "Mỹ Đình" chỉ còn 10h. Cột giờ dùng chung nên luôn
 * có đủ ba ô — hai ô của showroom kia phải MỜ, không được biến mất.
 */
const CARD: TestDriveCardData = {
  vehicle_id: "veh-vf5",
  vehicle_name: "VinFast VF 5 All New",
  showrooms: [
    { showroom_id: "sr-lb", name: "Long Biên", address: "Số 1 Nguyễn Văn Cừ", distance_label: "2,1 km" },
    { showroom_id: "sr-md", name: "Mỹ Đình", address: "Số 2 Phạm Hùng", distance_label: "5,4 km" },
  ],
  days: [
    {
      date: "2026-08-28",
      label: "Hôm nay 28/08",
      times: [
        { scheduled_at: NAY_9H, label: "9h00" },
        { scheduled_at: NAY_10H, label: "10h00" },
        { scheduled_at: NAY_11H, label: "11h00" },
      ],
    },
    { date: "2026-08-29", label: "Ngày mai 29/08", times: [{ scheduled_at: MAI_9H, label: "9h00" }] },
  ],
  options: [
    { showroom_id: "sr-lb", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Long Biên" },
    { showroom_id: "sr-lb", scheduled_at: NAY_11H, value: "__lichlaithu__|" + NAY_11H + "|Long Biên" },
    { showroom_id: "sr-md", scheduled_at: NAY_10H, value: "__lichlaithu__|" + NAY_10H + "|Mỹ Đình" },
    { showroom_id: "sr-lb", scheduled_at: MAI_9H, value: "__lichlaithu__|" + MAI_9H + "|Long Biên" },
  ],
  default_showroom_id: "sr-lb",
  default_date: "2026-08-28",
};

afterEach(cleanup);

function times() {
  return ["9h00", "10h00", "11h00"].map((label) => screen.getByRole("button", { name: label }));
}

describe("TestDriveCard", () => {
  it("giữ nguyên cột giờ và chỉ làm mờ ô showroom đang chọn hết chỗ", async () => {
    render(<TestDriveCard card={CARD} onConfirm={vi.fn()} />);

    const [chinGio, muoiGio, muoiMotGio] = times();
    expect(chinGio).toBeEnabled();
    expect(muoiGio).toBeDisabled();
    expect(muoiMotGio).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: /Mỹ Đình/ }));

    // Cột giờ KHÔNG co lại — vẫn đủ ba ô, chỉ đảo bên nào mờ.
    const [sauChin, sauMuoi, sauMuoiMot] = times();
    expect(sauChin).toBeDisabled();
    expect(sauMuoi).toBeEnabled();
    expect(sauMuoiMot).toBeDisabled();
  });

  it("chỉ đặt lịch khi khách bấm xác nhận, và gửi đúng mã của ô đã chọn", async () => {
    const onConfirm = vi.fn();
    render(<TestDriveCard card={CARD} onConfirm={onConfirm} />);

    // Chưa chọn giờ thì không cho đặt.
    expect(screen.getByRole("button", { name: "Đặt lịch" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "11h00" }));
    expect(onConfirm).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Đặt lịch" }));
    expect(onConfirm).toHaveBeenCalledWith("__lichlaithu__|" + NAY_11H + "|Long Biên");
  });

  it("bỏ chọn khi đổi sang showroom không còn chỗ giờ đó", async () => {
    const onConfirm = vi.fn();
    render(<TestDriveCard card={CARD} onConfirm={onConfirm} />);

    await userEvent.click(screen.getByRole("button", { name: "9h00" }));
    await userEvent.click(screen.getByRole("button", { name: /Mỹ Đình/ }));

    // Mỹ Đình kín 9h ⇒ không được để một ô mờ trông như đang được chọn.
    expect(screen.getByRole("button", { name: "Đặt lịch" })).toBeDisabled();
  });

  it("giấu các ngày khác sau một nút, mở ra mới đổi ngày", async () => {
    render(<TestDriveCard card={CARD} onConfirm={vi.fn()} />);

    expect(screen.queryByRole("button", { name: "Ngày mai 29/08" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Xem ngày khác" }));
    await userEvent.click(screen.getByRole("button", { name: "Ngày mai 29/08" }));

    expect(screen.getByText("Ngày mai 29/08", { selector: "p" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "9h00" })).toHaveLength(1);
  });
});
