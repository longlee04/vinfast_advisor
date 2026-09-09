import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Dọn DOM sau MỖI test.
//
// Testing Library chỉ tự đăng ký `afterEach(cleanup)` khi Vitest bật `globals`.
// Config này không bật, nên trước đây mỗi file test phải tự gọi — 5 file có gọi,
// số còn lại thì không, và `render` của test sau chồng lên DOM của test trước.
//
// Đó là nguyên nhân THẬT của `Found multiple elements with the role "button" and
// name "Ô tô"`: hai nút đó thuộc HAI lần render khác nhau, không phải hai nút
// trùng tên trong một màn hình. Suýt nữa đã đi sửa nhãn của component cho một
// lỗi trợ năng không hề tồn tại.
afterEach(cleanup);

// `jsdom` không cài `Element.prototype.scrollTo` (cũng như `scrollIntoView`).
// Component nào cuộn danh sách tin nhắn xuống đáy sẽ ném
// `TypeError: list.scrollTo is not a function` — lỗi của MÔI TRƯỜNG, không phải
// của sản phẩm. Gắn hàm rỗng, đúng mức: test không kiểm việc cuộn.
if (typeof Element !== "undefined") {
  Element.prototype.scrollTo ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}

// Node ≥22 tự khai `globalThis.localStorage` (getter trả `undefined` khi không
// có `--localstorage-file`), và môi trường jsdom của Vitest KHÔNG ghi đè key đã
// tồn tại. Kết quả: `window.localStorage.clear()` ném `Cannot read properties
// of undefined` dù test đã ở jsdom. Gắn một Storage trong bộ nhớ khi thiếu.
for (const key of ["localStorage", "sessionStorage"] as const) {
  if (typeof (globalThis as Record<string, unknown>)[key] !== "undefined") continue;
  const store = new Map<string, string>();
  const shim: Storage = {
    get length() {
      return store.size;
    },
    clear: () => store.clear(),
    getItem: (k) => store.get(k) ?? null,
    key: (i) => [...store.keys()][i] ?? null,
    removeItem: (k) => {
      store.delete(k);
    },
    setItem: (k, v) => {
      store.set(k, String(v));
    },
  };
  Object.defineProperty(globalThis, key, { value: shim, configurable: true, writable: true });
}
