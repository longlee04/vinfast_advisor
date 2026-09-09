// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { VehiclePitchList } from "@/components/consultation/vehicle-pitch-list";
import type { RecommendedVehicle } from "@/types/agent";

const MOCK_VEHICLES: RecommendedVehicle[] = [
  { vehicle_id: "vf3", rank: 1, display_name: "VinFast VF 3", image_url: null, starting_price_vnd: "240000000", pitch: "Xe mini", citations: [] },
  { vehicle_id: "vf5", rank: 2, display_name: "VinFast VF 5", image_url: null, starting_price_vnd: "468000000", pitch: "Xe đô thị", citations: [] },
  { vehicle_id: "vf6", rank: 3, display_name: "VinFast VF 6", image_url: null, starting_price_vnd: "675000000", pitch: "Xe gia đình", citations: [] },
  { vehicle_id: "vf7", rank: 4, display_name: "VinFast VF 7", image_url: null, starting_price_vnd: "850000000", pitch: "Xe thể thao", citations: [] },
  { vehicle_id: "vf8", rank: 5, display_name: "VinFast VF 8", image_url: null, starting_price_vnd: "1090000000", pitch: "Xe SUV cao cấp", citations: [] },
  { vehicle_id: "vf9", rank: 6, display_name: "VinFast VF 9", image_url: null, starting_price_vnd: "1500000000", pitch: "Xe full-size", citations: [] },
  { vehicle_id: "vf_wild", rank: 7, display_name: "VinFast VF Wild", image_url: null, starting_price_vnd: "1800000000", pitch: "Xe bán tải", citations: [] },
];

describe("VehiclePitchList", () => {
  afterEach(() => {
    cleanup();
  });
  it("hiển thị toàn bộ xe khi có <= 5 xe và không có nút Xem thêm", () => {
    render(<VehiclePitchList pitchHidden={false} vehicles={MOCK_VEHICLES.slice(0, 5)} />);

    expect(screen.getByText("VinFast VF 3")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 5")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 7")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 8")).toBeInTheDocument();
    expect(screen.queryByText(/Xem thêm/)).not.toBeInTheDocument();
  });

  it("chỉ hiển thị 5 xe đầu tiên khi có > 5 xe và có nút Xem thêm", () => {
    render(<VehiclePitchList pitchHidden={false} vehicles={MOCK_VEHICLES} />);

    expect(screen.getByText("VinFast VF 3")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 5")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 6")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 7")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF 8")).toBeInTheDocument();
    expect(screen.queryByText("VinFast VF 9")).not.toBeInTheDocument();
    expect(screen.queryByText("VinFast VF Wild")).not.toBeInTheDocument();

    const seeMoreBtn = screen.getByRole("button", { name: /Xem thêm/ });
    expect(seeMoreBtn).toBeInTheDocument();
    expect(seeMoreBtn).toHaveTextContent("Xem thêm (2 mẫu xe khác)");
  });

  it("mở rộng xem toàn bộ xe khi click Xem thêm và thu gọn khi click Thu gọn", () => {
    render(<VehiclePitchList pitchHidden={false} vehicles={MOCK_VEHICLES} />);

    const seeMoreBtn = screen.getByRole("button", { name: /Xem thêm/ });
    fireEvent.click(seeMoreBtn);

    expect(screen.getByText("VinFast VF 9")).toBeInTheDocument();
    expect(screen.getByText("VinFast VF Wild")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Thu gọn/ })).toHaveTextContent("Thu gọn danh sách (7 xe)");

    // Click thu gọn
    fireEvent.click(screen.getByRole("button", { name: /Thu gọn/ }));
    expect(screen.queryByText("VinFast VF 9")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Xem thêm/ })).toBeInTheDocument();
  });
});
