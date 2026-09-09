import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CarShowcase } from "@/components/catalog/car-showcase";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";
import { DemoStoreProvider } from "@/store/demo-store";

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

describe("CarShowcase", () => {
  beforeEach(() => fetchVehicle.mockReset());

  it("áp dụng bố cục showcase và nội dung biên tập cho mẫu ô tô khác VF8", async () => {
    fetchVehicle.mockResolvedValue({
      id: "vf6-plus",
      slug: "vinfast-vf-6-plus",
      modelName: "VF 6",
      variant: "Plus",
      vehicleType: "car",
      priceVnd: 699_000_000,
      priceType: "BATTERY_INCLUDED",
      rangeKm: 310,
      seats: 5,
      chargeMinutes: 24,
      batteryCapacityKwh: 59.6,
      imageUrl: null,
      detailUrl: null,
      specs: { motor_power_kw: "150.000", torque_nm: "310.000" },
      unknownFeatureNames: [],
      showcaseItems: [],
      promotionIds: ["promotion-1"],
    });

    render(
      <DemoStoreProvider>
        <CarShowcase
          editorial={{ summary: "SUV điện dành cho gia đình trẻ.", exterior: "Ngoại thất năng động.", interior: "Khoang lái tiện nghi.", performance: "Vận hành linh hoạt.", safety: "An toàn chủ động.", sourceUrl: "https://example.com/vf6" }}
          vehicle={getVehicleMenuEntry("vf-6")!}
        />
      </DemoStoreProvider>,
    );

    expect(await screen.findByText(/699\.000\.000/)).toBeInTheDocument();
    expect(screen.getAllByText("SUV điện dành cho gia đình trẻ.")).toHaveLength(2);
    expect(screen.getByText("150 kW")).toBeInTheDocument();
    expect(screen.getByText(/1 chương trình ưu đãi/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /vận hành/i })).toHaveAttribute("href", "#performance");
  });
});
