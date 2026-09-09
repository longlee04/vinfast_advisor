import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { MotorbikeShowcase } from "@/components/catalog/motorbike-showcase";
import { getMotorbikeMenuEntry } from "@/mocks/motorbike-menu";

const { fetchVehicle } = vi.hoisted(() => ({ fetchVehicle: vi.fn() }));

vi.mock("@/lib/api/vehicles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/vehicles")>();
  return { ...actual, fetchVehicle };
});

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: React.ComponentProps<"a">) => <a href={href}>{children}</a>,
}));

describe("MotorbikeShowcase", () => {
  beforeEach(() => fetchVehicle.mockReset());

  it("dùng ảnh sản phẩm local chất lượng cao và bố cục thông số kiểu trang chính thức", async () => {
    fetchVehicle.mockResolvedValue({
      id: "evo-grand-lite",
      slug: "vinfast-evo-grand-lite-standard",
      modelName: "Evo Grand Lite",
      variant: "Standard",
      vehicleType: "electric_motorbike",
      priceVnd: 16_500_000,
      priceType: "BATTERY_INCLUDED",
      rangeKm: 70,
      seats: null,
      chargeMinutes: 390,
      batteryCapacityKwh: 1.2,
      imageUrl: null,
      detailUrl: null,
      specs: { max_speed_kmh: "48", max_power_w: "1900" },
      unknownFeatureNames: [],
      showcaseItems: [],
      promotionIds: [],
    });

    render(<MotorbikeShowcase vehicle={getMotorbikeMenuEntry("evo-grand-lite")!} />);

    expect(await screen.findByText(/16\.500\.000/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Evo Grand Lite/ })).toHaveAttribute(
      "src",
      "/vehicles/motorbikes/evo-grand-lite.webp",
    );
    expect(screen.getByText("48 km/h")).toBeInTheDocument();
    expect(screen.getByText("70 km")).toBeInTheDocument();
    expect(screen.getByText("1.900 W")).toBeInTheDocument();
    expect(screen.queryByText(/chế độ xem 3D đang chờ/i)).not.toBeInTheDocument();
  });
});
