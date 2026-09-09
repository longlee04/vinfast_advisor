import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Canh cửa cho lỗi prod 2026-08-31: bản đồ /locations vỡ vì CSS của Leaflet
 * không lọt vào bundle. Nguyên nhân là `@import "leaflet/dist/leaflet.css"`
 * đặt trong `globals.css`; Next chỉ gom chắc chắn khi component client import
 * thẳng. Test này không thay được `npm run build` + grep `leaflet-container`,
 * nhưng chặn ngay việc ai đó "dọn" import về lại chỗ cũ.
 */
function read(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
}

describe("CSS Leaflet đi cùng component bản đồ", () => {
  it("mỗi component bản đồ tự import leaflet/dist/leaflet.css", () => {
    expect(read("./location-map.tsx")).toMatch(/import "leaflet\/dist\/leaflet\.css";/);
    expect(read("../consultation/tour-map.tsx")).toMatch(/import "leaflet\/dist\/leaflet\.css";/);
  });

  it("globals.css KHÔNG còn @import leaflet (đường rơi rụng trên prod)", () => {
    const css = read("../../app/globals.css");
    expect(css).not.toMatch(/^\s*@import "leaflet/m);
  });
});
