import { describe, expect, it } from "vitest";

import { vehicleMenuCategories } from "@/mocks/vehicle-menu";

describe("vehicleMenuCategories", () => {
  it("chỉ điều hướng tới trang chi tiết nội bộ", () => {
    const vehicles = vehicleMenuCategories.flatMap((category) => category.vehicles);

    expect(vehicles).toHaveLength(19);
    for (const vehicle of vehicles) {
      expect(vehicle.href).toBe(`/vehicles/${vehicle.id}`);
      expect(vehicle.href).not.toMatch(/^https?:\/\//);
    }
  });
});
