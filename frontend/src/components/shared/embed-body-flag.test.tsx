// @vitest-environment jsdom

import { readFileSync } from "node:fs";

import { render, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EmbedBodyFlag } from "@/components/shared/embed-body-flag";

afterEach(() => {
  delete document.body.dataset.embed;
  window.history.replaceState(null, "", "/");
});

describe("EmbedBodyFlag", () => {
  it("?embed=1: gắn data-embed lên body, unmount thì gỡ", async () => {
    window.history.replaceState(null, "", "/vehicles/vf-7?embed=1");

    const { unmount } = render(<EmbedBodyFlag />);
    await waitFor(() => expect(document.body.dataset.embed).toBe("1"));

    unmount();
    expect(document.body.dataset.embed).toBeUndefined();
  });

  it("không có ?embed=1 thì KHÔNG đụng vào body — trang thường giữ nguyên nav", async () => {
    window.history.replaceState(null, "", "/vehicles/vf-7");

    render(<EmbedBodyFlag />);
    // Chờ qua chu kỳ effect của useEmbedMode rồi mới khẳng định.
    await waitFor(() => expect(document.body.dataset.embed).toBeUndefined());
  });
});

// jsdom không có layout thật — khoá DANH SÁCH selector ở mức văn bản CSS, cùng
// cách với `consultation/consultation-css.test.ts`: mỗi trang chi tiết có nav
// nội bộ phải nằm trong luật `body[data-embed="1"]`, thiếu một dòng là trang đó
// lại đè thanh cửa sổ khi nhúng.
describe("CSS ẩn nav nội bộ khi nhúng (body[data-embed])", () => {
  // Không dùng `import.meta.url`: trong jsdom nó mang scheme http nên không mở
  // file được — vitest luôn chạy từ thư mục `frontend` (cùng bẫy đã ghi ở
  // `tour-panel.test.tsx`).
  const css = readFileSync(`${process.cwd()}/src/app/globals.css`, "utf8");

  const SELECTORS = [
    '.vf7-product-nav',
    '.vf8-model-nav',
    '.car-showcase-nav',
    '.motorbike-showcase-nav',
    '.vf-product-nav',
    'header[class*="-experience_header__"]',
    'nav[class*="_mainNav__"]',
    'nav[class*="_mobileNav__"]',
    'nav[class*="_modelNav__"]',
  ];

  it.each(SELECTORS)("ẩn %s khi body[data-embed=1]", (selector) => {
    expect(css).toContain(`body[data-embed="1"] ${selector}`);
  });

  it("khối embed dùng display:none (ẩn hẳn, không chừa khoảng trống)", () => {
    const block = css.slice(css.indexOf('body[data-embed="1"]'));
    expect(block).toContain("display: none !important");
  });
});
