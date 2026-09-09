import { describe, expect, it } from "vitest";

import { motorbikeMenuCategories } from "@/mocks/motorbike-menu";

describe("motorbikeMenuCategories", () => {
  it("có đúng ba phân khúc và 18 mẫu xe theo danh mục", () => {
    expect(motorbikeMenuCategories.map((category) => category.label)).toEqual([
      "Cao cấp",
      "Trung cấp",
      "Phổ thông",
    ]);
    expect(motorbikeMenuCategories.map((category) => category.motorbikes.length)).toEqual([3, 3, 12]);
  });

  it("chỉ điều hướng tới trang chi tiết xe máy điện nội bộ", () => {
    const motorbikes = motorbikeMenuCategories.flatMap((category) => category.motorbikes);

    for (const motorbike of motorbikes) {
      expect(motorbike.href).toBe(`/motorbikes/${motorbike.id}`);
      expect(motorbike.href).not.toMatch(/^https?:\/\//);
      expect(motorbike.catalogSlug).toBeTruthy();
      expect(motorbike.imageUrl).toContain("/images/mega-menu/scooter/");
      expect(motorbike.detailImageUrl).toMatch(/^\/vehicles\/motorbikes\//);
    }
  });
});
