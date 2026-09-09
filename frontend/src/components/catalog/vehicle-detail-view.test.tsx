import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VehicleDetailView } from "@/components/catalog/vehicle-detail-view";
import { getMotorbikeMenuEntry } from "@/mocks/motorbike-menu";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";
import { DemoStoreProvider } from "@/store/demo-store";

const { fetchVehicle } = vi.hoisted(() => ({ fetchVehicle: vi.fn() }));

vi.mock("@/lib/api/vehicles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/vehicles")>();
  return { ...actual, fetchVehicle };
});

vi.mock("next/image", () => ({
  default: ({ alt, onError, src }: { alt: string; onError?: () => void; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} onError={onError} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: React.ComponentProps<"a">) => <a href={href}>{children}</a>,
}));

describe("VehicleDetailView", () => {
  beforeEach(() => fetchVehicle.mockReset());

  it("hiển thị thông số Catalog và các hành động nội bộ khi API có dữ liệu", async () => {
    fetchVehicle.mockResolvedValue({
      id: "vehicle-vf6",
      slug: "vinfast-vf-6-plus",
      modelName: "VF 6",
      variant: "Plus",
      vehicleType: "car",
      priceVnd: 749_000_000,
      priceType: "BATTERY_INCLUDED",
      rangeKm: 399,
      seats: 5,
      chargeMinutes: 25,
      batteryCapacityKwh: 59.6,
      imageUrl: null,
      detailUrl: null,
    });

    render(
      <DemoStoreProvider>
        <VehicleDetailView vehicle={getVehicleMenuEntry("vf-6")!} />
      </DemoStoreProvider>,
    );

    expect(await screen.findByText("399 km")).toBeInTheDocument();
    expect(screen.getByText("5 chỗ")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /nhờ ai tư vấn/i })).toHaveAttribute("href", "/consultation");
    expect(screen.getByRole("link", { name: /đăng ký lái thử/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("button", { name: /thêm vào so sánh/i })).toBeEnabled();
  });

  it("giữ khách trong hệ thống và báo đang cập nhật khi Catalog chưa có mẫu xe", async () => {
    render(
      <DemoStoreProvider>
        <VehicleDetailView vehicle={getVehicleMenuEntry("fadil")!} />
      </DemoStoreProvider>,
    );

    expect(screen.getByRole("heading", { name: "Fadil" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText(/thông tin chi tiết đang được cập nhật/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /chưa thể so sánh/i })).toBeDisabled();
    expect(screen.queryByRole("link", { name: /vinfast/i })).not.toBeInTheDocument();
    expect(fetchVehicle).not.toHaveBeenCalled();
  });

  it("dùng đúng dữ liệu Catalog cho trang chi tiết xe máy điện nội bộ", async () => {
    fetchVehicle.mockResolvedValue({
      id: "motorbike-vero-x",
      slug: "vinfast-vero-x",
      modelName: "Vero X",
      variant: "Standard",
      vehicleType: "electric_motorbike",
      priceVnd: 34_900_000,
      priceType: "BATTERY_INCLUDED",
      rangeKm: 134,
      seats: 2,
      chargeMinutes: 360,
      batteryCapacityKwh: 2.4,
      imageUrl: null,
      detailUrl: null,
    });

    render(
      <DemoStoreProvider>
        <VehicleDetailView vehicle={getMotorbikeMenuEntry("vero-x")!} />
      </DemoStoreProvider>,
    );

    expect(await screen.findByText("134 km")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Vero X" })).toBeInTheDocument();
    expect(screen.getByText("Cao cấp")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Ảnh xe Vero X" })).toBeInTheDocument();
    expect(screen.getByText(/chế độ xem 3d đang chờ model chính thức/i)).toBeInTheDocument();
    expect(fetchVehicle).toHaveBeenCalledWith("vinfast-vero-x");
  });
});
