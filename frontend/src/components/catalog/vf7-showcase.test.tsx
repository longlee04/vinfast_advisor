import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Vf7Showcase } from "@/components/catalog/vf7-showcase";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";

const { fetchVehicle } = vi.hoisted(() => ({ fetchVehicle: vi.fn() }));

vi.mock("@/lib/api/vehicles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/vehicles")>();
  return { ...actual, fetchVehicle };
});

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} />
  ),
}));
vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props}>{children}</a>,
}));

describe("Vf7Showcase", () => {
  it("tái hiện bố cục VF7 chính thức với menu trượt, ngoại thất, nội thất và màu sắc", async () => {
    fetchVehicle.mockResolvedValue({
      id: "vf7", slug: "vinfast-vf-7-all-new", modelName: "VF 7", variant: "All New",
      vehicleType: "car", priceVnd: 740_000_000, priceType: "BATTERY_INCLUDED",
      rangeKm: 440, seats: 5, chargeMinutes: 25, batteryCapacityKwh: 70,
      imageUrl: null, detailUrl: null, specs: { motor_power_kw: "130", torque_nm: "250" },
      unknownFeatureNames: [], showcaseItems: [], promotionIds: [],
    });

    render(<Vf7Showcase vehicle={getVehicleMenuEntry("vf-7")!} />);

    expect(await screen.findByText(/740\.000\.000/)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Điều hướng nội dung VF 7" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ngoại thất" })).toHaveAttribute("href", "#exterior");
    expect(screen.getByRole("link", { name: "Nội thất" })).toHaveAttribute("href", "#interior");
    expect(screen.getAllByRole("button", { name: /Solar Ruby|Zenith Grey|Urban Mint|Infinity Blanc|Jet Black/ })).toHaveLength(5);
    expect(screen.getByRole("img", { name: /nội thất VF 7/i })).toHaveAttribute(
      "data-image-src", "/vehicles/vf7/interior.webp",
    );
    fireEvent.click(screen.getAllByRole("button", { name: /VF 7 Plus/ })[0]);
    expect(screen.getByText("500,5 km")).toBeInTheDocument();
    expect(screen.getByText("150 kW")).toBeInTheDocument();
    expect(screen.getByText("70 kWh")).toBeInTheDocument();
    expect(screen.queryByText(/database|catalog|crawl|unknown|demo/i)).not.toBeInTheDocument();
  });
});
