import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchTco } from "@/lib/api/vehicles";

function okResponse() {
  return {
    ok: true,
    json: async () => ({ data: { breakdown: {}, assumptions: {}, consumption: {} } }),
  } as unknown as Response;
}

describe("fetchTco — nơi đăng ký xe", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("'Tỉnh/thành khác' (mã rỗng): KHÔNG gửi province — backend tự dùng mặc định Khu vực II", async () => {
    // Bản cũ gửi cứng "Cần Thơ" cho mọi tỉnh còn lại — dữ liệu bịa lọt vào log
    // và mọi thống kê theo tỉnh.
    const fetchMock = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal("fetch", fetchMock);

    await fetchTco("vf-6", "", 1200, 5);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).not.toContain("province=");
    expect(url).toContain("monthly_distance_km=1200");
  });

  it("tỉnh cụ thể vẫn gửi như cũ (lệ phí biển số Khu vực I phụ thuộc nó)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse());
    vi.stubGlobal("fetch", fetchMock);

    await fetchTco("vf-6", "Hà Nội", 1200, 5);

    expect(String(fetchMock.mock.calls[0][0])).toContain("province=H%C3%A0+N%E1%BB%99i");
  });
});
