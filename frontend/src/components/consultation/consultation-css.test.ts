import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

/**
 * Canh cửa cho lỗi 761–999px (đợt vá UI 2026-08-31): mở cửa sổ hội thoại trong
 * khoảng này từng làm MẤT khung chat — workspace về một cột nhưng sidebar vẫn
 * bung đầy đủ (display: revert) và cao cả màn hình, đẩy chat xuống dưới nếp gấp.
 * Chốt: 761–999px thu sidebar thành rail 56px như desktop; chỉ ≤760px (sidebar
 * vốn là ngăn kéo fixed) mới trả nội dung đầy đủ về cho ngăn kéo.
 *
 * jsdom không có layout thật nên test này khóa đúng văn bản CSS — cùng cách với
 * `locations/leaflet-css.test.ts`.
 */
function read(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
}

function mediaBlock(css: string, marker: string): string {
  const start = css.indexOf(marker);
  if (start < 0) throw new Error(`không thấy block ${marker}`);
  const next = css.indexOf("@media", start + marker.length);
  return css.slice(start, next < 0 ? css.length : next);
}

describe("CSS cửa sổ hội thoại 761–1099px", () => {
  const css = read("../../app/globals.css");
  // Block mobile của cửa sổ nằm CUỐI file (sau block desktop .tour-panel-open).
  const tourSection = css.slice(css.indexOf(".consultation-workspace.tour-panel-open"));
  const blockNarrow = mediaBlock(tourSection, "@media (max-width: 1099px)");

  it("desktop mở cửa sổ: panel là vai chính — chat co về minmax(440px, 38%), panel minmax(560px, 1fr)", () => {
    expect(tourSection).toContain("grid-template-columns: 56px minmax(440px, 38%) minmax(560px, 1fr)");
    // Không còn --chat-col: bề rộng do một mình CSS quyết.
    expect(tourSection).not.toContain("--chat-col");
  });

  it("chuyển cảnh đồng pha (đợt 11): lưới chat MỞ 480ms cubic-bezier, ĐÓNG 420ms cubic-bezier", () => {
    // Đóng: luật has-tour-panel trần (class tour-panel-open đã gỡ) cầm lái.
    expect(tourSection).toContain(
      ".consultation-workspace.has-tour-panel { transition: grid-template-columns 420ms cubic-bezier(.4,0,.2,1), width 420ms cubic-bezier(.4,0,.2,1); }",
    );
    // Mở: luật tour-panel-open cầm lái.
    expect(tourSection).toContain(
      ".consultation-workspace.has-tour-panel.tour-panel-open { transition: grid-template-columns 480ms cubic-bezier(.22,.61,.36,1), width 480ms cubic-bezier(.22,.61,.36,1); }",
    );
  });

  it("panel trượt CÙNG duration/easing với lưới — lệch pha là panel xong mà cột chat còn co", () => {
    // Desktop: transform + opacity cùng nhịp (không delay).
    expect(css).toContain(".tour-panel.is-animated { transition: transform 420ms cubic-bezier(.4,0,.2,1), opacity 420ms cubic-bezier(.4,0,.2,1); }");
    expect(css).toContain(
      ".tour-panel.is-animated.is-open { transition: transform 480ms cubic-bezier(.22,.61,.36,1), opacity 480ms cubic-bezier(.22,.61,.36,1); }",
    );
    // Mobile (bottom-sheet) chỉ transform, cùng 320/400.
    expect(css).toContain(".tour-panel.is-animated { transition: transform 320ms ease-in; }");
    expect(css).toContain(".tour-panel.is-animated.is-open { transition: transform 400ms cubic-bezier(.22,.61,.36,1); }");
  });

  it("mở ở 1280px: panel ≥560px và chat ≥440px (số học của minmax trên)", () => {
    // Toán tay theo đúng luật minmax: chat lấy 38% của 1280 = 486.4 (trên sàn
    // 440), panel lấy phần còn lại sau rail 56.
    const chat = Math.max(440, Math.min(0.38 * 1280, 1280 - 56 - 560));
    const panel = 1280 - 56 - chat;
    expect(panel).toBeGreaterThanOrEqual(560);
    expect(chat).toBeGreaterThanOrEqual(440);
    // Sát ngưỡng bottom-sheet: 1100px vẫn đủ chỗ cho cả ba cột tối thiểu.
    expect(56 + 440 + 560).toBeLessThanOrEqual(1100);
  });

  it("761–1099px mở cửa sổ: sidebar thu thành rail 56px, chat giữ phần còn lại; ngưỡng 1099 vì grid mở cần tối thiểu 1036px", () => {
    expect(blockNarrow).toContain("grid-template-columns: 56px minmax(0, 1fr)");
  });

  it("761–1099px KHÔNG bung lại sidebar đầy đủ (display: revert từng đẩy chat khỏi màn hình)", () => {
    expect(blockNarrow).not.toContain("display: revert");
  });

  it("≤760px (sidebar là ngăn kéo): ngăn kéo vẫn có nội dung đầy đủ, không bị luật rail che", () => {
    const block760 = mediaBlock(tourSection, "@media (max-width: 760px)");
    expect(block760).toContain("display: revert");
  });
});
