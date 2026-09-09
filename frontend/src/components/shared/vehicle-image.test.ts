import { describe, expect, it } from "vitest";

import { toDirectImageUrl } from "@/components/shared/vehicle-image";

describe("toDirectImageUrl", () => {
  it("trả nguyên vẹn khi thiếu src", () => {
    expect(toDirectImageUrl(null)).toBeNull();
    expect(toDirectImageUrl(undefined)).toBeUndefined();
    expect(toDirectImageUrl("")).toBe("");
  });

  it("đổi link Google Drive dạng /file/d/<id>/view sang URL ảnh trực tiếp", () => {
    expect(toDirectImageUrl("https://drive.google.com/file/d/ABC123/view?usp=drive_link")).toBe(
      "https://lh3.googleusercontent.com/d/ABC123",
    );
  });

  it("đổi link Google Drive dạng uc?export=view&id=<id> — dạng đang nằm trong DB prod", () => {
    expect(toDirectImageUrl("https://drive.google.com/uc?export=view&id=ABC123")).toBe(
      "https://lh3.googleusercontent.com/d/ABC123",
    );
  });

  it("trả nguyên URL không phải Google Drive", () => {
    expect(toDirectImageUrl("https://static-cms-prod.vinfastauto.com/photo.jpg")).toBe(
      "https://static-cms-prod.vinfastauto.com/photo.jpg",
    );
  });
});
