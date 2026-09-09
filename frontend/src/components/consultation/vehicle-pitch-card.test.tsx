// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { VehiclePitchCard } from "@/components/consultation/vehicle-pitch-card";
import type { RecommendedVehicle } from "@/types/agent";

// `globals` tắt trong vitest.config.ts nên auto-cleanup của testing-library
// không tự chạy; phải tự gọi cleanup() sau mỗi test.
afterEach(() => {
  cleanup();
});

const VEHICLE: RecommendedVehicle = {
  vehicle_id: "20000000-0000-0000-0000-000000000101",
  rank: 1,
  display_name: "VF 6",
  image_url: "https://cdn/vf6.png",
  starting_price_vnd: "690000000",
  pitch: "VF 6 đi được 399 km.",
  citations: [
    { index: 1 },
  ],
};

describe("VehiclePitchCard", () => {
  it("shows the name, price and pitch", () => {
    render(<VehiclePitchCard vehicle={VEHICLE} pitchHidden={false} />);

    expect(screen.getByText("VF 6")).toBeInTheDocument();
    expect(screen.getByText("Giá từ 690.000.000 đ")).toBeInTheDocument();
    expect(screen.getByText("VF 6 đi được 399 km.")).toBeInTheDocument();
    // `VehicleImage` dựng qua `next/image`, nên `src` là đường dẫn tối ưu hoá
    // (`/_next/image?url=...`) chứ không còn là URL gốc. Kiểm URL gốc nằm TRONG
    // đó — đủ để bắt việc truyền nhầm ảnh, mà không khoá vào chi tiết của Next.
    expect(screen.getByRole("img", { name: "VF 6" }).getAttribute("src")).toContain(
      encodeURIComponent("https://cdn/vf6.png"),
    );
  });

  it("hides the pitch when an advisor rewrote the answer", () => {
    render(<VehiclePitchCard vehicle={VEHICLE} pitchHidden />);

    expect(screen.getByText("VF 6")).toBeInTheDocument();
    expect(screen.queryByText("VF 6 đi được 399 km.")).not.toBeInTheDocument();
  });

  it("says so when the vehicle has no active price", () => {
    render(
      <VehiclePitchCard
        vehicle={{ ...VEHICLE, starting_price_vnd: null, image_url: null }}
        pitchHidden={false}
      />,
    );

    expect(screen.getByText("Chưa có giá hiệu lực")).toBeInTheDocument();
    // Không có ảnh thì hiện khung "Ảnh đang được cập nhật" thay vì một ô vỡ
    // (Sếp 2026-08-25). Khung đó vẫn mang `role="img"` cho trình đọc màn hình,
    // nên kiểm bằng nội dung chứ không bằng sự vắng mặt của vai trò.
    expect(screen.getByText("Ảnh đang được cập nhật")).toBeInTheDocument();
  });
});

// Sếp 2026-08-26: "hiện ra 3 xe thì người dùng có thể chọn được ngay".
describe("VehiclePitchCard chọn mẫu", () => {
  it("gọi onSelect với đúng chiếc xe của thẻ", async () => {
    const chosen: RecommendedVehicle[] = [];
    render(
      <VehiclePitchCard onSelect={(v) => chosen.push(v)} pitchHidden={false} vehicle={VEHICLE} />,
    );

    await userEvent.click(screen.getByRole("button", { name: /chọn mẫu này/i }));

    expect(chosen).toEqual([VEHICLE]);
  });

  it("không có onSelect thì thẻ không mọc nút", () => {
    // Thẻ xem lại trong lịch sử hội thoại không nên mời chọn một lần nữa.
    render(<VehiclePitchCard pitchHidden={false} vehicle={VEHICLE} />);

    expect(screen.queryByRole("button", { name: /chọn mẫu này/i })).toBeNull();
  });

  it("đang gửi thì khoá nút, tránh bấm hai lần thành hai lượt", () => {
    render(
      <VehiclePitchCard disabled onSelect={() => {}} pitchHidden={false} vehicle={VEHICLE} />,
    );

    expect(screen.getByRole("button", { name: /chọn mẫu này/i })).toBeDisabled();
  });
});
