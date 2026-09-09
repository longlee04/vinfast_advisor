import { describe, expect, it } from "vitest";

import { consultationHref, productHrefForVehicle } from "@/lib/vehicle-links";

describe("vehicle links", () => {
  it("maps a catalog variant back to the matching internal family page", () => {
    expect(productHrefForVehicle("VinFast VF 8 Eco Extended Range")).toBe(
      "/vehicles/vf-8",
    );
  });

  it("does not invent a product page for an unknown model", () => {
    expect(productHrefForVehicle("VinFast Unknown Concept")).toBeNull();
  });

  it("builds a targeted chat prompt with a return path", () => {
    expect(consultationHref("VF 7", "/vehicles/vf-7")).toBe(
      "/consultation?prompt=Cho+t%C3%B4i+th%C3%B4ng+tin+chi+ti%E1%BA%BFt+v%E1%BB%81+VF+7&from=%2Fvehicles%2Fvf-7",
    );
  });
});
