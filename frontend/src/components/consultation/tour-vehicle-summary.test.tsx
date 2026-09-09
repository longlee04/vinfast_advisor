// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TourVehicleSummary } from "@/components/consultation/tour-vehicle-summary";
import type { CatalogVehicle } from "@/lib/api/vehicles";
import type { NavigateVehicle } from "@/types/agent";

/**
 * Tóm tắt xe trong tour-panel (đợt 10) — thay cho việc nhúng `*Experience`
 * full-width vốn vỡ trong cột hẹp. Bộ này canh: dữ liệu từ Catalog API ra đúng
 * ô (ảnh, tên + giá, lưới thông số chỉ gồm mục CÓ dữ liệu), và nút "Mở toàn
 * trang" điều hướng thật tới /vehicles/[slug].
 */

const { fetchVehicle, push } = vi.hoisted(() => ({
  fetchVehicle: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/lib/api/vehicles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/vehicles")>();
  return { ...actual, fetchVehicle };
});

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push, replace: vi.fn(), back: vi.fn() }),
}));

const NAVIGATE: NavigateVehicle = {
  kind: "vehicle",
  vehicle_id: "veh-vf8",
  slug: "vf-8",
  name: "VinFast VF 8",
};

const VEHICLE: CatalogVehicle = {
  id: "veh-vf8",
  slug: "vf-8",
  modelName: "VF 8",
  variant: "Eco",
  vehicleType: "car",
  priceVnd: 1_190_000_000,
  priceType: "BATTERY_INCLUDED",
  rangeKm: 471,
  seats: 5,
  chargeMinutes: 31,
  batteryCapacityKwh: 87.7,
  imageUrl: "https://cdn/vf8.png",
  detailUrl: null,
  // Chuỗi số như backend trả thật — component phải tự ép số.
  specs: { motor_power_kw: "260.00", cargo_volume_standard_l: "376.00" },
  unknownFeatureNames: [],
  showcaseItems: [],
};

describe("TourVehicleSummary", () => {
  beforeEach(() => {
    fetchVehicle.mockReset();
    push.mockReset();
  });
  afterEach(() => {
    cleanup();
  });

  it("fetch theo vehicle_id, hiện ảnh + tên + giá + lưới thông số chỉ gồm mục có dữ liệu", async () => {
    fetchVehicle.mockResolvedValueOnce(VEHICLE);

    render(<TourVehicleSummary navigate={NAVIGATE} />);

    expect(await screen.findByRole("region", { name: "Tóm tắt VinFast VF 8" })).toBeInTheDocument();
    expect(fetchVehicle).toHaveBeenCalledWith("veh-vf8");
    expect(screen.getByRole("heading", { name: "VF 8 Eco" })).toBeInTheDocument();
    expect(screen.getByText("Giá từ 1.190.000.000 đ")).toBeInTheDocument();
    const specs = screen.getByRole("list", { name: "Thông số chính" });
    expect(specs).toHaveTextContent("471 km");
    expect(specs).toHaveTextContent("31 phút");
    expect(specs).toHaveTextContent("5 chỗ");
    expect(specs).toHaveTextContent("376 L");
    expect(specs).toHaveTextContent("260 kW");
    // 87,7 kWh KHÔNG lọt: đã đủ 6... thật ra chỉ 5 mục trước nó — pin phải có.
    expect(specs).toHaveTextContent("87,7 kWh");
    // Ảnh đi qua VehicleImage (next/image) — URL gốc nằm trong src tối ưu hoá.
    expect(screen.getByRole("img", { name: "VF 8 Eco" }).getAttribute("src")).toContain(
      encodeURIComponent("https://cdn/vf8.png"),
    );
  });

  it("nút 'Mở toàn trang' điều hướng thật tới /vehicles/[slug]", async () => {
    const user = userEvent.setup();
    fetchVehicle.mockResolvedValueOnce(VEHICLE);
    render(<TourVehicleSummary navigate={NAVIGATE} />);

    await user.click(await screen.findByRole("button", { name: "Mở toàn trang" }));

    expect(push).toHaveBeenCalledWith("/vehicles/vf-8");
  });

  it("slug rỗng (xe máy chưa có trang): fetch theo vehicle_id và KHÔNG có nút mở toàn trang", async () => {
    fetchVehicle.mockResolvedValueOnce({ ...VEHICLE, slug: "" });
    render(
      <TourVehicleSummary
        navigate={{ kind: "vehicle", vehicle_id: "moto-1", slug: "", name: "Evo200" }}
      />,
    );

    await screen.findByRole("region", { name: "Tóm tắt Evo200" });
    expect(fetchVehicle).toHaveBeenCalledWith("moto-1");
    expect(screen.queryByRole("button", { name: "Mở toàn trang" })).not.toBeInTheDocument();
  });

  it("thông số thiếu thì ô đó không hiện — không bày ô trống", async () => {
    fetchVehicle.mockResolvedValueOnce({
      ...VEHICLE,
      chargeMinutes: null,
      seats: null,
      batteryCapacityKwh: null,
      specs: {},
    });
    render(<TourVehicleSummary navigate={NAVIGATE} />);

    const specs = await screen.findByRole("list", { name: "Thông số chính" });
    expect(specs).toHaveTextContent("471 km");
    expect(specs).not.toHaveTextContent("phút");
    expect(specs).not.toHaveTextContent("chỗ");
    expect(specs).not.toHaveTextContent("kW");
  });

  it("API lỗi: nói ra trong panel và nút Thử lại gọi lại fetch", async () => {
    const user = userEvent.setup();
    fetchVehicle.mockRejectedValueOnce(new Error("boom")).mockResolvedValueOnce(VEHICLE);
    render(<TourVehicleSummary navigate={NAVIGATE} />);

    expect(await screen.findByText(/chưa tải được thông tin VinFast VF 8/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Thử lại" }));

    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Tóm tắt VinFast VF 8" })).toBeInTheDocument(),
    );
    expect(fetchVehicle).toHaveBeenCalledTimes(2);
  });

  it("chấm màu đứng cạnh từng thông số có dữ liệu", async () => {
    fetchVehicle.mockResolvedValueOnce(VEHICLE);
    render(<TourVehicleSummary navigate={NAVIGATE} />);

    await screen.findByRole("list", { name: "Thông số chính" });
    const dots = document.querySelectorAll(".tour-vehicle-summary__dot");
    const rows = document.querySelectorAll(".tour-vehicle-summary__spec");
    expect(rows.length).toBeGreaterThanOrEqual(4);
    expect(dots.length).toBe(rows.length);
  });
});
