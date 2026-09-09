import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Vf8Showcase } from "@/components/catalog/vf8-showcase";
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

function vehicle(variant: string, slug: string, power: string) {
  return {
    id: slug,
    slug,
    modelName: "VF 8",
    variant,
    vehicleType: "car" as const,
    priceVnd: 854_050_000,
    priceType: "BATTERY_INCLUDED",
    rangeKm: variant.startsWith("Eco") ? 562 : 457,
    seats: 5,
    chargeMinutes: 30,
    batteryCapacityKwh: 87.7,
    imageUrl: null,
    detailUrl: null,
    specs: {
      motor_power_kw: power,
      torque_nm: variant.startsWith("Eco") ? "310.000" : "620.000",
      acceleration_0_100_seconds: variant.startsWith("Eco") ? "11.800" : "5.580",
      range_cycle: variant.startsWith("Eco") ? "NEDC" : "WLTP",
      fast_charge_from_percent: "10",
      fast_charge_to_percent: "70",
    },
    promotionIds: ["promotion-1"],
    unknownFeatureNames: ["GPS", "Ứng dụng di động"],
    showcaseItems: variant.startsWith("Eco") ? [
      {
        id: "hero",
        section: "overview",
        key: "overview.hero",
        title: "VF 8",
        description: "SUV điện cao cấp",
        mediaUrl: "https://shop.vinfastauto.com/official-vf8-hero.webp",
        mediaAlt: "VinFast VF 8 chính hãng",
        order: 0,
        sourceUrl: "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf8.html",
        sourceRetrievedAt: "2026-08-11T10:00:00+07:00",
      },
      {
        id: "black",
        section: "colors",
        key: "colors.ce11",
        title: "Jet Black",
        description: "Màu ngoại thất",
        mediaUrl: "https://shop.vinfastauto.com/vf8-black.webp",
        mediaAlt: "VF 8 màu Jet Black",
        order: 0,
        sourceUrl: "https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf8.html",
        sourceRetrievedAt: "2026-08-11T10:00:00+07:00",
      },
    ] : [],
  };
}

describe("Vf8Showcase", () => {
  it("renders the sticky product menu, official media and unchanged Catalog values", async () => {
    fetchVehicle
      .mockResolvedValueOnce(vehicle("Eco Extended Range", "eco", "150.000"))
      .mockResolvedValueOnce(vehicle("Plus Extended Range", "plus", "300.000"));

    render(<Vf8Showcase vehicle={getVehicleMenuEntry("vf-8")!} />);

    expect(await screen.findByRole("navigation", { name: "Điều hướng nội dung VF 8" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Màu sắc" })).toHaveAttribute("href", "#colors");
    expect(screen.getByRole("img", { name: "VinFast VF 8 chính hãng" })).toHaveAttribute(
      "data-image-src",
      "https://shop.vinfastauto.com/official-vf8-hero.webp",
    );
    expect(screen.getAllByText(/854\.050\.000/)).toHaveLength(4);
    expect(screen.getByRole("button", { name: "Jet Black" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/1 chương trình ưu đãi đang áp dụng/i)).toBeInTheDocument();
    expect(screen.getAllByText("150 kW")).toHaveLength(3);
    expect(screen.queryByText("150.000 kW")).not.toBeInTheDocument();
    expect(screen.queryByText(/database|catalog nhóm|crawl|unknown|đối chiếu trang nguồn/i)).not.toBeInTheDocument();
    expect(fetchVehicle).toHaveBeenNthCalledWith(1, "vinfast-vf-8-eco-extended-range");
    expect(fetchVehicle).toHaveBeenNthCalledWith(2, "vinfast-vf-8-plus-extended-range");
  });
});
