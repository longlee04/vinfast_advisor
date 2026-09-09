// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TcoCard } from "@/components/consultation/tco-card";
import type { TcoCard as TcoCardData } from "@/types/agent";

const estimateTco = vi.fn();
const fetchProvinceOptions = vi.fn();

vi.mock("@/lib/api/agent", () => ({
  estimateTco: (...args: unknown[]) => estimateTco(...args),
  fetchProvinceOptions: () => fetchProvinceOptions(),
}));

const CARD: TcoCardData = {
  vehicle_id: "20000000-0000-0000-0000-000000000108",
  vehicle_name: "VinFast VF 8 All New",
  total_vnd: "937883030",
  components: [
    { code: "promoted_purchase_price_vnd", label: "Giá xe", amount_vnd: "899000000" },
    { code: "rolling_fees_vnd", label: "Lệ phí ban đầu", amount_vnd: "10920000" },
  ],
  daily_distance_km: 30,
  daily_distance_known: false,
  province_code: null,
  region_code: "KHU_VUC_II",
  assumption_note: "Tính theo 30 km/ngày (em tạm tính), đăng ký ngoài Hà Nội/TP.HCM.",
};

afterEach(() => {
  cleanup();
  estimateTco.mockReset();
  fetchProvinceOptions.mockReset();
});

describe("TcoCard", () => {
  it("dùng danh sách tỉnh gửi kèm thẻ, không gọi mạng lần nữa", async () => {
    fetchProvinceOptions.mockResolvedValue([]);

    render(
      <TcoCard
        card={{
          ...CARD,
          province_options: [
            { code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" },
            { code: "DN", name: "Đà Nẵng", region_code: "KHU_VUC_II" },
          ],
        }}
      />,
    );

    expect(await screen.findByRole("option", { name: "Hà Nội" })).toBeInTheDocument();
    expect(fetchProvinceOptions).not.toHaveBeenCalled();
  });

  it("mời khách bấm khi chưa chọn tỉnh, và không khoá ô lúc danh sách rỗng", async () => {
    fetchProvinceOptions.mockResolvedValue([]);

    render(<TcoCard card={CARD} />);

    // Khoá ô khi chưa có danh sách là khách hết đường thử lại.
    expect(screen.getByLabelText(/Tỉnh thành đăng ký xe/)).toBeEnabled();
    expect(await screen.findByRole("option", { name: "Chọn tỉnh…" })).toBeInTheDocument();
    expect(screen.getByText(/chọn để tính đúng lệ phí biển/)).toBeInTheDocument();
  });

  it("hiển thị tổng và từng khoản với dấu phân nghìn", () => {
    fetchProvinceOptions.mockResolvedValue([]);

    render(<TcoCard card={CARD} />);

    expect(screen.getByText("937.883.030 đồng")).toBeInTheDocument();
    expect(screen.getByText("899.000.000 đồng")).toBeInTheDocument();
  });

  it("nói ra rằng quãng đường đang là mốc tạm khi khách chưa nêu", () => {
    fetchProvinceOptions.mockResolvedValue([]);

    render(<TcoCard card={CARD} />);

    // Một ước tính không nói mình ước tính theo gì thì khách không biết nó sai ở đâu.
    expect(screen.getByText("(em tạm tính)")).toBeInTheDocument();
  });

  it("đổi tỉnh thì gọi tính lại và thay con số, không cần gõ vào khung chat", async () => {
    fetchProvinceOptions.mockResolvedValue([
      { code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" },
    ]);
    estimateTco.mockResolvedValue({
      ...CARD,
      total_vnd: "951963030",
      province_code: "HN",
      region_code: "KHU_VUC_I",
      assumption_note: "Tính theo 30 km/ngày, đăng ký tại khu vực Hà Nội/TP.HCM.",
    });

    render(<TcoCard card={CARD} sessionId="phien-1" />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Hà Nội" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Tỉnh thành đăng ký xe"), "HN");

    await waitFor(() => expect(screen.getByText("951.963.030 đồng")).toBeInTheDocument());
    expect(estimateTco).toHaveBeenCalledWith({
      vehicleId: CARD.vehicle_id,
      dailyDistanceKm: 30,
      provinceCode: "HN",
      sessionId: "phien-1",
    });
  });

  it("gọi tính lại hỏng thì GIỮ con số cũ và nói ra", async () => {
    // Hiện một tổng nửa vời hay xoá trắng đều tệ hơn: khách đang so tiền.
    fetchProvinceOptions.mockResolvedValue([
      { code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" },
    ]);
    estimateTco.mockRejectedValue(new Error("mat mang"));

    render(<TcoCard card={CARD} />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Hà Nội" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Tỉnh thành đăng ký xe"), "HN");

    await waitFor(() => expect(screen.getByText(/chưa cập nhật được số mới/i)).toBeInTheDocument());
    expect(screen.getByText("937.883.030 đồng")).toBeInTheDocument();
  });

  it("không có danh sách tỉnh thì thẻ vẫn dùng được", async () => {
    fetchProvinceOptions.mockRejectedValue(new Error("mat mang"));

    render(<TcoCard card={CARD} />);

    await waitFor(() => expect(screen.getByText("937.883.030 đồng")).toBeInTheDocument());
    expect(screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét")).toBeEnabled();
  });

  // Đợt 10: ô KHU VỰC không bao giờ được trống — sai tỉnh là chỗ sai đắt nhất
  // của cả thẻ (lệ phí biển chênh 100 lần), nên mất mạng phụ cũng phải còn
  // đường chọn.
  it("backend thiếu options + mạng tỉnh hỏng: vẫn có đủ bộ 3 khu vực như /tco", async () => {
    fetchProvinceOptions.mockRejectedValue(new Error("mat mang"));

    render(<TcoCard card={CARD} />);

    expect(await screen.findByRole("option", { name: "Hà Nội" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "TP. Hồ Chí Minh" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Tỉnh/thành khác (Khu vực II)" })).toBeInTheDocument();
  });

  it("chọn fallback 'TP. Hồ Chí Minh' gọi tính lại với mã HCM thật", async () => {
    fetchProvinceOptions.mockRejectedValue(new Error("mat mang"));
    estimateTco.mockResolvedValue({ ...CARD, province_code: "HCM", region_code: "KHU_VUC_I" });

    render(<TcoCard card={CARD} sessionId="phien-1" />);
    await userEvent.selectOptions(await screen.findByLabelText("Tỉnh thành đăng ký xe"), "HCM");

    await waitFor(() =>
      expect(estimateTco).toHaveBeenCalledWith({
        vehicleId: CARD.vehicle_id,
        dailyDistanceKm: 30,
        provinceCode: "HCM",
        sessionId: "phien-1",
      }),
    );
  });

  it("'Tỉnh/thành khác' KHÔNG gửi mã bịa: giữ null (mặc định Khu vực II) và select vẫn hiển thị lựa chọn", async () => {
    fetchProvinceOptions.mockRejectedValue(new Error("mat mang"));

    render(<TcoCard card={CARD} />);
    const select = await screen.findByLabelText("Tỉnh thành đăng ký xe");
    await userEvent.selectOptions(select, "__khac__");

    // Thẻ đang tính sẵn theo mặc định Khu vực II — không có gì để hỏi lại server.
    expect(estimateTco).not.toHaveBeenCalled();
    expect(select).toHaveValue("__khac__");
    expect(screen.queryByText(/chọn để tính đúng lệ phí biển/)).not.toBeInTheDocument();
  });

  it("mạng tỉnh về danh sách đầy đủ thì thay fallback", async () => {
    fetchProvinceOptions.mockResolvedValue([
      { code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" },
      { code: "DN", name: "Đà Nẵng", region_code: "KHU_VUC_II" },
    ]);

    render(<TcoCard card={CARD} />);

    expect(await screen.findByRole("option", { name: "Đà Nẵng" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Tỉnh/thành khác (Khu vực II)" })).not.toBeInTheDocument();
  });
});

describe("TcoCard — thanh km", () => {
  it("kéo thanh gọi tính lại ngay và đổi con số hiển thị", async () => {
    fetchProvinceOptions.mockResolvedValue([]);
    estimateTco.mockResolvedValue({ ...CARD, total_vnd: "608119000", daily_distance_km: 90 });

    render(<TcoCard card={CARD} />);
    const slider = screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét");
    fireEvent.change(slider, { target: { value: "90" } });

    await waitFor(() => expect(screen.getByText("608.119.000 đồng")).toBeInTheDocument());
    expect(estimateTco).toHaveBeenCalledTimes(1);
    expect(screen.getByText("90 km")).toBeInTheDocument();
  });

  it("km không đổi thì không gọi lại", async () => {
    fetchProvinceOptions.mockResolvedValue([]);

    render(<TcoCard card={CARD} />);
    fireEvent.change(screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét"), {
      target: { value: String(CARD.daily_distance_km) },
    });

    expect(estimateTco).not.toHaveBeenCalled();
  });
});

// Đơn giá cố định để tay tính đối chiếu — cùng số với `src/lib/tco.test.ts`.
// totalKm(30) = 30*365*5 = 54.750 → maintenance ceil(5.475)=6 → total = 1.097.125.000
// totalKm(90) = 90*365*5 = 164.250 → maintenance ceil(16.425)=17 → total = 1.288.875.000
const RATES = {
  fixed_vnd: "900000000",
  energy_vnd_per_km: "1500",
  insurance_vnd_per_year: "8000000",
  maintenance_vnd_per_service: "2500000",
  maintenance_interval_km: 10000,
  battery_vnd_per_month: "1000000",
  years: 5,
  days_per_year: 365,
  formula_note: "Tính cho 5 năm, 365 ngày/năm.",
};

const CARD_WITH_RATES: TcoCardData = { ...CARD, rates: RATES };

function mockMatchMedia(matches: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn().mockReturnValue({
      matches,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  });
}

describe("TcoCard — có `rates`: kéo km tính tại chỗ, không gọi mạng", () => {
  beforeEach(() => {
    mockMatchMedia(false);
    fetchProvinceOptions.mockResolvedValue([]);
  });

  it("hiện đúng tổng và từng khoản ngay từ đầu, theo công thức", () => {
    render(<TcoCard card={CARD_WITH_RATES} />);

    expect(screen.getByText("1.097.125.000 đồng")).toBeInTheDocument();
    expect(screen.getByText("82.125.000 đồng")).toBeInTheDocument(); // Nhiên liệu / điện
    expect(screen.getByText("Tính cho 5 năm, 365 ngày/năm.")).toBeInTheDocument();
  });

  it("kéo thanh: đổi số NGAY, không đợi mạng, và KHÔNG gọi estimateTco", () => {
    // Giờ ảo cho `requestAnimationFrame`/`performance`: animation 250ms không
    // được phép phụ thuộc đồng hồ THẬT của máy chạy test (máy càng bận, animation
    // càng trễ, `waitFor` theo thời gian thật càng dễ hết hạn trong lúc chạy
    // song song nhiều file — đúng lỗi từng thấy khi chạy cả bộ test).
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] });
    try {
      render(<TcoCard card={CARD_WITH_RATES} />);

      fireEvent.change(screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét"), { target: { value: "90" } });

      // Animation đang chạy (không giảm chuyển động): số CHƯA nhảy thẳng tới
      // đích ngay trong cùng một tick đồng bộ.
      expect(screen.queryByText("1.288.875.000 đồng")).not.toBeInTheDocument();

      act(() => vi.advanceTimersByTime(300));

      expect(screen.getByText("1.288.875.000 đồng")).toBeInTheDocument();
      expect(screen.getByText("246.375.000 đồng")).toBeInTheDocument(); // Nhiên liệu / điện ở 90km
      expect(estimateTco).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("prefers-reduced-motion: nhảy thẳng tới số đích, không chạy animation", () => {
    mockMatchMedia(true);
    render(<TcoCard card={CARD_WITH_RATES} />);

    fireEvent.change(screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét"), { target: { value: "90" } });

    // Giảm chuyển động: số phải đúng NGAY, không cần chờ animation frame nào.
    expect(screen.getByText("1.288.875.000 đồng")).toBeInTheDocument();
    expect(estimateTco).not.toHaveBeenCalled();
  });

  it("đổi tỉnh vẫn gọi mạng như cũ — lệ phí biển không tính được ở client", async () => {
    fetchProvinceOptions.mockResolvedValue([{ code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" }]);
    estimateTco.mockResolvedValue({
      ...CARD_WITH_RATES,
      province_code: "HN",
      rates: { ...RATES, fixed_vnd: "915000000" },
    });

    render(<TcoCard card={CARD_WITH_RATES} />);
    await waitFor(() => expect(screen.getByRole("option", { name: "Hà Nội" })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText("Tỉnh thành đăng ký xe"), "HN");

    await waitFor(() => expect(estimateTco).toHaveBeenCalledWith({
      vehicleId: CARD.vehicle_id,
      dailyDistanceKm: 30,
      provinceCode: "HN",
      sessionId: undefined,
    }));
  });
});

// ==== Mục D đợt 11: payload THẬT của VF 7 (Sếp báo thẻ "bị lỗi" dù backend
// trả ĐỦ). Giữ nguyên HÌNH DẠNG wire (cast qua unknown) — đúng thứ client
// nhận: `battery_vnd_per_month` VẮNG HẲN (VF 7 không thuê pin),
// `maintenance_interval_km` là CHUỖI "12000", `total_vnd` là SỐ 785482910,
// `energy_vnd_per_km` thập phân "501.165000", 37 tỉnh gửi kèm.
const VF7_WIRE_CARD = {
  vehicle_id: "20000000-0000-0000-0000-000000000107",
  vehicle_name: "VinFast VF 7",
  total_vnd: 785482910, // SỐ, không phải chuỗi như hợp đồng
  components: [
    { code: "fixed_vnd", label: "Chi phí cố định", amount_vnd: "748520000" },
  ],
  daily_distance_km: 30,
  daily_distance_known: false,
  province_code: null,
  region_code: "KHU_VUC_II",
  assumption_note: "Tính theo 30 km/ngày, 5 năm, 360 ngày/năm.",
  province_options: Array.from({ length: 37 }, (_, index) => ({
    code: `P${String(index + 1).padStart(2, "0")}`,
    name: `Tỉnh ${index + 1}`,
    region_code: index < 2 ? "KHU_VUC_I" : "KHU_VUC_II",
  })),
  rates: {
    fixed_vnd: "748520000",
    energy_vnd_per_km: "501.165000",
    insurance_vnd_per_year: "480000",
    maintenance_vnd_per_service: "1500000",
    maintenance_interval_km: "12000", // CHUỖI chứ không phải số
    // battery_vnd_per_month KHÔNG có mặt — Number(undefined) là NaN nếu không đỡ
    years: 5,
    days_per_year: 360,
  },
} as unknown as TcoCardData;

describe("TcoCard — payload thật VF 7 (mục D đợt 11)", () => {
  beforeEach(() => {
    // Giảm chuyển động để số nhảy thẳng tới đích — test soi GIÁ TRỊ, không soi animation.
    mockMatchMedia(true);
    fetchProvinceOptions.mockResolvedValue([]);
  });

  it("render đúng tổng 785.482.910 đồng — khớp total_vnd server, không NaN", () => {
    render(<TcoCard card={VF7_WIRE_CARD} />);

    // fixed 748.520.000 + energy 501,165*54.000km + insurance 480.000*5
    // + maintenance ceil(54.000/12.000)*1.500.000 + pin 0 = 785.482.910.
    expect(screen.getByText("785.482.910 đồng")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("NaN");
  });

  it("kéo km 30→90: tính lại TẠI CHỖ ra 853.108.730, không NaN, không gọi mạng", () => {
    render(<TcoCard card={VF7_WIRE_CARD} />);

    fireEvent.change(screen.getByLabelText("Quãng đường mỗi ngày, ki-lô-mét"), { target: { value: "90" } });

    // totalKm = 90*360*5 = 162.000 → energy 81.188.730; bảo dưỡng
    // ceil(162.000/12.000)=14 lần → 21.000.000; pin 0.
    expect(screen.getByText("853.108.730 đồng")).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("NaN");
    expect(estimateTco).not.toHaveBeenCalled();
  });

  it("37 tỉnh gửi kèm thẻ đều vào ô chọn, không gọi mạng lần nữa", async () => {
    render(<TcoCard card={VF7_WIRE_CARD} />);

    expect(await screen.findByRole("option", { name: "Tỉnh 37" })).toBeInTheDocument();
    expect(fetchProvinceOptions).not.toHaveBeenCalled();
  });
});


// ==== Sếp 2026-08-31: "giá lăn bánh với TCO là MỘT" — thẻ chia hai nhóm, và
// một thẻ sống cả phiên (lượt sau cập nhật tại chỗ, nháy viền). ====
const GROUPED_CARD: TcoCardData = {
  ...CARD,
  components: [
    { code: "promoted_purchase_price_vnd", label: "Giá xe", amount_vnd: "899000000", group: "rolling" },
    { code: "rolling_fees_vnd", label: "Lệ phí ban đầu", amount_vnd: "10920000", group: "rolling" },
    { code: "energy_vnd", label: "Chi phí năng lượng", amount_vnd: "20000000", group: "operating" },
    { code: "scheduled_maintenance_vnd", label: "Bảo dưỡng", amount_vnd: "7043030", group: "operating" },
  ],
};

describe("TcoCard — nhóm lăn bánh / vận hành (2026-08-31)", () => {
  beforeEach(() => {
    fetchProvinceOptions.mockResolvedValue([]);
  });

  it("có group thì chia hai nhóm với tổng từng nhóm", () => {
    render(<TcoCard card={GROUPED_CARD} />);

    expect(screen.getByText("Chi phí lăn bánh ban đầu")).toBeInTheDocument();
    expect(screen.getByText("Chi phí vận hành 5 năm")).toBeInTheDocument();
    // Cộng lăn bánh: 899.000.000 + 10.920.000
    expect(screen.getByText("909.920.000 đồng")).toBeInTheDocument();
    // Cộng vận hành: 20.000.000 + 7.043.030
    expect(screen.getByText("27.043.030 đồng")).toBeInTheDocument();
  });

  it("không có group (backend cũ) thì bảng phẳng như cũ, không tiêu đề nhóm", () => {
    render(<TcoCard card={CARD} />);

    expect(screen.queryByText("Chi phí lăn bánh ban đầu")).not.toBeInTheDocument();
    expect(screen.getByText("899.000.000 đồng")).toBeInTheDocument();
  });

  it("prefill km + tỉnh khách đã nói từ trước — không bắt nhập tay lại", () => {
    render(
      <TcoCard
        card={{
          ...GROUPED_CARD,
          daily_distance_km: 60,
          daily_distance_known: true,
          province_code: "HN",
          province_options: [{ code: "HN", name: "Hà Nội", region_code: "KHU_VUC_I" }],
        }}
      />,
    );

    expect(screen.getByText("60 km")).toBeInTheDocument();
    expect(screen.getByLabelText("Tỉnh thành đăng ký xe")).toHaveValue("HN");
    // Km lấy từ lời khách thì không còn là "em tạm tính".
    expect(screen.queryByText("(em tạm tính)")).not.toBeInTheDocument();
  });

  it("card prop đổi (lượt sau cập nhật thẻ tại chỗ) thì đổi số và nháy viền", async () => {
    const { rerender } = render(<TcoCard card={GROUPED_CARD} />);
    expect(document.querySelector(".tco-card--updated")).toBeNull();

    rerender(<TcoCard card={{ ...GROUPED_CARD, total_vnd: "999999030", province_code: "HN" }} />);

    expect(screen.getByText("999.999.030 đồng")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector(".tco-card--updated")).not.toBeNull());
  });
});
