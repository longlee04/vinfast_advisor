import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Tự tìm test, mặc định chạy trong `jsdom`.
//
// Bản trước để `environment: "node"` rồi liệt kê TAY từng file cần DOM. Đếm thật
// 2026-08-28: 36 file `*.test.*` tồn tại, danh sách tay chỉ có 23 — **13 file
// chưa từng chạy**, trong đó có `catalog/vehicle-detail-view.test.tsx`. Thứ phải
// đăng ký thủ công thì sớm muộn có người quên, và quên ở đây thì mọi thứ vẫn
// xanh.
//
// `jsdom` làm mặc định vì phần lớn test là component. Test thuần logic chạy
// trong `jsdom` không sai gì, chỉ tốn thêm chút thời gian dựng môi trường.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    // `vitest.setup.ts` đã tồn tại từ trước nhưng KHÔNG được nạp — nên 16 file
    // test phải tự `import "@testing-library/jest-dom/vitest"`, và file nào
    // quên thì đỏ với `Invalid Chai property: toBeInTheDocument`. Nạp một lần ở
    // đây, không bắt mỗi file nhớ.
    setupFiles: ["./vitest.setup.ts"],
    // Tự tìm, KHÔNG liệt kê tay.
    //
    // Đếm thật 2026-08-28: 36 file `*.test.*` tồn tại, danh sách tay chỉ đăng ký
    // 23 — **13 file chưa từng chạy**, trong đó có
    // `components/catalog/vehicle-detail-view.test.tsx`. Thứ phải đăng ký thủ
    // công thì sớm muộn có người quên, và quên ở đây thì mọi thứ vẫn xanh.
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
