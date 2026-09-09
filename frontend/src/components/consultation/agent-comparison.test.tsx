// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentComparison } from "@/components/consultation/agent-comparison";
import type { VehicleComparison } from "@/types/agent";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} />
  ),
}));

const comparison: VehicleComparison = {
  vehicles: [
    {
      vehicle_id: "vf3",
      found: true,
      display_name: "VinFast VF 3 All New",
      vehicle_type: "CAR",
      image_url: "https://catalog.example/vf3.png",
      starting_price_vnd: "299000000",
      specs: { range_km: "210" },
    },
    {
      vehicle_id: "vf5",
      found: true,
      display_name: "VinFast VF 5 All New",
      vehicle_type: "CAR",
      image_url: null,
      starting_price_vnd: null,
      specs: {},
    },
    { vehicle_id: "gone", found: false, display_name: "", vehicle_type: "", image_url: null, starting_price_vnd: null, specs: {} },
  ],
  spec_fields: [{ code: "range_km", label: "Tầm hoạt động (km)" }],
  summary: "VF 5 rộng hơn nhưng VF 3 rẻ hơn.",
  missing_vehicle_names: ["VF 99"],
};

describe("AgentComparison", () => {
  afterEach(() => cleanup());

  it("dựng bảng có ảnh từng xe và đặt đoạn tóm tắt ngay dưới", () => {
    render(<AgentComparison comparison={comparison} />);

    expect(screen.getByRole("img", { name: "Ảnh xe VinFast VF 3 All New" })).toHaveAttribute(
      "data-image-src",
      "https://catalog.example/vf3.png",
    );
    expect(screen.getByText("210")).toBeInTheDocument();
    expect(screen.getByText("VF 5 rộng hơn nhưng VF 3 rẻ hơn.")).toBeInTheDocument();
  });

  it("không dựng cột cho mẫu chưa tìm thấy nhưng vẫn nói rõ mẫu nào thiếu", () => {
    render(<AgentComparison comparison={comparison} />);

    // Đúng hai cột xe: mẫu `found: false` không được dựng thành một cột trống.
    expect(screen.getAllByRole("heading", { level: 2 }).map((item) => item.textContent)).toEqual([
      "VinFast VF 3 All New",
      "VinFast VF 5 All New",
    ]);
    expect(screen.getByText(/Chưa tìm thấy trong danh mục: VF 99/)).toBeInTheDocument();
  });

  it("nói thẳng khi một xe chưa có giá hiệu lực thay vì để trống", () => {
    render(<AgentComparison comparison={comparison} />);

    expect(screen.getByText("Chưa có giá hiệu lực")).toBeInTheDocument();
    // Thông số xe không có dữ liệu cũng không được để trống.
    expect(screen.getByText("Chưa có dữ liệu")).toBeInTheDocument();
  });
});
