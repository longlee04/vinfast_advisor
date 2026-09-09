// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TourPanel } from "@/components/consultation/tour-panel";
import type { TourPanelState } from "@/store/agent-session";
import type { TestDriveCard as TestDriveCardData } from "@/types/agent";

// Leaflet cần `window` thật; tóm tắt xe thì gọi Catalog API — cả hai mock về
// một ô đánh dấu: bộ này canh khung panel, còn nội dung tóm tắt đã có bộ riêng
// (`tour-vehicle-summary.test.tsx`).
vi.mock("next/dynamic", () => ({
  default: () => (props: { showrooms: readonly { name: string }[] }) => (
    <div data-testid="tour-map">{props.showrooms.map((s) => s.name).join("|")}</div>
  ),
}));
vi.mock("@/components/consultation/tour-vehicle-summary", () => ({
  TourVehicleSummary: ({ navigate }: { navigate: { slug: string; name: string } }) => (
    <div data-testid="vehicle-summary">{navigate.slug || navigate.name}</div>
  ),
}));

const noop = { onClose: vi.fn(), onLocated: vi.fn(), onShowroomPick: vi.fn() };

const VEHICLE: TourPanelState = {
  open: true,
  navigate: { kind: "vehicle", vehicle_id: "v-5", slug: "", name: "VinFast VF 5" },
  selectedShowroomId: null,
};

const MAP: TourPanelState = {
  open: true,
  selectedShowroomId: "sr-1",
  navigate: {
    kind: "map",
    vehicle_id: "v-5",
    center: { lat: 21, lng: 105.8 },
    needs_location: false,
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "Cầu Giấy, HN", lat: 21.03, lng: 105.79, distance_km: 2.1 },
      { showroom_id: "sr-2", name: "VinFast Long Biên", address: "Long Biên, HN", lat: 21.04, lng: 105.88, distance_km: 6.4 },
    ],
  },
};

describe("TourPanel", () => {
  it("kind=vehicle CÓ slug: nhúng TOÀN TRANG qua iframe ?embed=1 (Sếp 2026-08-31)", () => {
    render(<TourPanel {...noop} panel={VEHICLE} sessionId="s1" />);

    expect(screen.getByRole("complementary", { name: "Trang đi theo hội thoại" })).toHaveClass("is-open");
    const frame = document.querySelector("iframe.tour-panel__frame");
    expect(frame).toBeNull(); // fixture mặc định slug rỗng → tóm tắt
    expect(screen.getByTestId("vehicle-summary")).toHaveTextContent("VinFast VF 5");
    expect(document.querySelector("iframe")).toBeNull();
    expect(window.location.pathname).not.toContain("/vehicles/");
  });

  it("có slug (kể cả lạ) → iframe toàn trang /vehicles/{slug}?embed=1, trang tự lo 404", () => {
    render(
      <TourPanel
        {...noop}
        panel={{ ...VEHICLE, navigate: { kind: "vehicle", vehicle_id: "x", slug: "vf-99", name: "VF 99" } }}
      />,
    );

    const frame = document.querySelector("iframe.tour-panel__frame") as HTMLIFrameElement;
    expect(frame).not.toBeNull();
    expect(frame.getAttribute("src")).toBe("/vehicles/vf-99?embed=1");
    expect(screen.queryByTestId("vehicle-summary")).toBeNull();
  });

  it("kind=map: bản đồ + danh sách showroom, bấm showroom = chọn ghim", async () => {
    const onShowroomPick = vi.fn();
    const user = userEvent.setup();
    render(<TourPanel {...noop} onShowroomPick={onShowroomPick} panel={MAP} sessionId="s1" />);

    expect(screen.getByTestId("tour-map")).toHaveTextContent("VinFast Cầu Giấy|VinFast Long Biên");
    expect(screen.getByRole("button", { name: /VinFast Cầu Giấy/ })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: /VinFast Long Biên/ }));

    expect(onShowroomPick).toHaveBeenCalledWith("sr-2");
  });

  it("needs_location: hiện nút vị trí + ô quận/huyện thay vì bản đồ", () => {
    render(
      <TourPanel
        {...noop}
        panel={{ ...MAP, navigate: { ...MAP.navigate!, showrooms: [], needs_location: true } as never }}
        sessionId="s1"
      />,
    );

    expect(screen.getByRole("button", { name: "Dùng vị trí của tôi" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Quận/huyện, tỉnh" })).toBeInTheDocument();
    expect(screen.queryByTestId("tour-map")).not.toBeInTheDocument();
  });

  it("nút ✕ và phím ESC báo đóng lên cha; panel đóng vẫn còn trong DOM (mở lại không nạp lại)", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<TourPanel {...noop} onClose={onClose} panel={VEHICLE} />);

    await user.click(screen.getByRole("button", { name: "Đóng cửa sổ" }));
    expect(onClose).toHaveBeenCalledTimes(1);
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(2);

    rerender(<TourPanel {...noop} onClose={onClose} panel={{ ...VEHICLE, open: false }} />);
    expect(screen.getByLabelText("Trang đi theo hội thoại", { selector: "aside" })).not.toHaveClass("is-open");
  });

  it("mặc định có class chuyển cảnh; prefers-reduced-motion thì KHÔNG (chỉ hiện/ẩn)", async () => {
    const { unmount } = render(<TourPanel {...noop} panel={VEHICLE} />);
    expect(await screen.findByLabelText("Trang đi theo hội thoại", { selector: "aside" })).toHaveClass("is-animated");
    unmount();

    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("reduce"),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    render(<TourPanel {...noop} panel={VEHICLE} />);
    const aside = screen.getByLabelText("Trang đi theo hội thoại", { selector: "aside" });
    await vi.waitFor(() => expect(aside).not.toHaveClass("is-animated"));
    expect(aside).toHaveClass("is-open");
    vi.unstubAllGlobals();
  });

  it("đổi nội dung vehicle → map thì khối nội dung mount lại (fade chéo, không nháy trắng)", () => {
    const { rerender } = render(<TourPanel {...noop} panel={VEHICLE} />);
    const first = document.querySelector(".tour-panel__content");
    rerender(<TourPanel {...noop} panel={MAP} />);
    const second = document.querySelector(".tour-panel__content");

    expect(second).not.toBe(first);
    expect(second).toHaveClass("tour-panel__content");
  });

  it("panel đóng bị 'inert' — nội dung ẩn không nhận focus/click; mở thì hết inert", () => {
    const { rerender } = render(<TourPanel {...noop} panel={{ ...VEHICLE, open: false }} />);
    const aside = screen.getByLabelText("Trang đi theo hội thoại", { selector: "aside" });
    expect(aside).toHaveAttribute("inert");

    rerender(<TourPanel {...noop} panel={VEHICLE} />);
    expect(aside).not.toHaveAttribute("inert");
  });

  it("ESC giữa chừng gõ IME (isComposing) hoặc đã bị preventDefault thì KHÔNG đóng", () => {
    const onClose = vi.fn();
    render(<TourPanel {...noop} onClose={onClose} panel={VEHICLE} />);

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", isComposing: true }));
    const prevented = new KeyboardEvent("keydown", { key: "Escape", cancelable: true });
    prevented.preventDefault();
    window.dispatchEvent(prevented);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("ESC khi đang focus ô nhập TRONG panel: chỉ blur ô nhập, không đóng panel", () => {
    const onClose = vi.fn();
    render(
      <TourPanel
        {...noop}
        onClose={onClose}
        panel={{ ...MAP, navigate: { ...MAP.navigate!, showrooms: [], needs_location: true } as never }}
        sessionId="s1"
      />,
    );
    const input = screen.getByRole("textbox", { name: "Quận/huyện, tỉnh" });
    input.focus();
    expect(input).toHaveFocus();

    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

    expect(onClose).not.toHaveBeenCalled();
    expect(input).not.toHaveFocus();
  });

  it("slug rỗng (xe máy chưa có trang chi tiết): không render link /vehicles/ trống", () => {
    render(
      <TourPanel
        {...noop}
        panel={{ ...VEHICLE, navigate: { kind: "vehicle", vehicle_id: "moto-1", slug: "", name: "Evo200" } }}
      />,
    );

    expect(screen.getByTestId("vehicle-summary")).toHaveTextContent("Evo200");
    expect(document.querySelector('a[href="/vehicles/"]')).toBeNull();
  });

  it("tour-panel KHÔNG import *Experience/vehicle-detail-content nữa — trang full-width vỡ trong cột hẹp", async () => {
    // Khoá ở mức VĂN BẢN nguồn (cùng cách consultation-css.test.ts): mock ở
    // trên che mất import thật, nên phải đọc thẳng file để chắc không ai nối
    // lại đường nhúng trang lớn vào cột 380–600px.
    const { readFileSync } = await import("node:fs");
    // Không dùng `import.meta.url`: trong môi trường jsdom nó mang scheme http
    // nên không mở file được — vitest luôn chạy từ thư mục `frontend`.
    const source = readFileSync(`${process.cwd()}/src/components/consultation/tour-panel.tsx`, "utf8");
    // Bắt IMPORT chứ không bắt chữ trần: comment trong file được phép nhắc tên
    // *Experience khi kể lại vì sao đã bỏ.
    expect(source).not.toMatch(/Experience[^\n]*from|from[^\n]*experience/);
    expect(source).not.toContain("vehicle-detail-content");
    expect(source).toContain("TourVehicleSummary");
  });

  // Sếp báo "không tắt được cửa sổ" khi nội dung là iframe: nút Đóng phải nằm
  // NGOÀI iframe (trong bar), có chữ "Đóng" và bấm được ngay cả khi trang nhúng
  // đang render.
  it("nút Đóng cửa sổ bấm được khi nội dung là IFRAME, có chữ 'Đóng' cạnh icon", async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <TourPanel
        {...noop}
        onClose={onClose}
        panel={{ ...VEHICLE, navigate: { kind: "vehicle", vehicle_id: "x", slug: "vf-7", name: "VF 7" } }}
      />,
    );

    // Iframe đang render thật sự.
    expect(document.querySelector("iframe.tour-panel__frame")).not.toBeNull();
    const close = screen.getByRole("button", { name: "Đóng cửa sổ" });
    // Chữ "Đóng" hiện cạnh icon — không chỉ là aria-label.
    expect(close).toHaveTextContent("Đóng");
    // Nút nằm trong bar, tức NGOÀI iframe — click không phụ thuộc iframe.
    expect(close.closest(".tour-panel__bar")).not.toBeNull();
    expect(close.closest("iframe")).toBeNull();

    await user.click(close);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("CSS: bar đủ cao (≥48px), không co, nổi trên iframe; nút Đóng ≥40x40", async () => {
    // jsdom không có layout — khoá ở mức văn bản CSS (cùng cách consultation-css.test.ts).
    const { readFileSync } = await import("node:fs");
    const css = readFileSync(`${process.cwd()}/src/app/globals.css`, "utf8");
    const bar = css.slice(css.indexOf(".tour-panel__bar {"), css.indexOf(".tour-panel__title"));
    expect(bar).toContain("min-height: 52px");
    expect(bar).toContain("flex: 0 0 auto");
    expect(bar).toContain("z-index: 2");
    const collapse = css.slice(css.indexOf(".tour-panel__collapse {"), css.indexOf(".tour-panel__collapse:hover"));
    expect(collapse).toContain("min-width: 40px");
    expect(collapse).toContain("min-height: 40px");
  });

  it("không có navigate thì không vẽ gì", () => {
    const { container } = render(
      <TourPanel {...noop} panel={{ open: false, navigate: null, selectedShowroomId: null }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});

// Đợt 11 (Sếp: "đăng ký giờ của tôi ở đâu"): panel bản đồ bày ngày + khung giờ
// từ CHÍNH test_drive_card của lượt; bấm giờ rồi "Đặt lịch" gửi đúng mã đã ký
// (`__lichlaithu__…`) qua onSendMessage — cùng đường với thẻ trong chat.
describe("TourPanel — khung giờ lái thử trong panel bản đồ", () => {
  const TD_CARD: TestDriveCardData = {
    vehicle_id: "v-5",
    vehicle_name: "VinFast VF 5",
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "Cầu Giấy, HN", distance_label: "2,1 km" },
      { showroom_id: "sr-2", name: "VinFast Long Biên", address: "Long Biên, HN", distance_label: "6,4 km" },
    ],
    days: [
      {
        date: "2026-09-01",
        label: "Thứ Ba 01/09",
        times: [
          { scheduled_at: "2026-09-01T09:00:00+07:00", label: "09:00" },
          { scheduled_at: "2026-09-01T10:00:00+07:00", label: "10:00" },
        ],
      },
    ],
    options: [
      { showroom_id: "sr-1", scheduled_at: "2026-09-01T09:00:00+07:00", value: "__lichlaithu__sr1-0900" },
      { showroom_id: "sr-2", scheduled_at: "2026-09-01T10:00:00+07:00", value: "__lichlaithu__sr2-1000" },
    ],
    default_showroom_id: "sr-1",
    default_date: "2026-09-01",
  };

  it("mở panel: CHƯA bày khung giờ, chỉ gợi ý bấm showroom (Sếp 2026-08-31)", () => {
    render(<TourPanel {...noop} onSendMessage={vi.fn()} panel={MAP} sessionId="s1" testDriveCard={TD_CARD} />);

    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();
    expect(screen.getByText("Bấm chọn showroom để xem khung giờ lái thử.")).toBeInTheDocument();
  });

  it("bấm showroom mở khung giờ, bấm giờ rồi Đặt lịch: gửi đúng option.value của showroom đang chọn", async () => {
    const onSendMessage = vi.fn();
    const user = userEvent.setup();
    render(
      <TourPanel {...noop} onSendMessage={onSendMessage} panel={MAP} sessionId="s1" testDriveCard={TD_CARD} />,
    );

    // Khung giờ chỉ mở khi khách CHỦ ĐỘNG bấm một showroom (Sếp 2026-08-31:
    // "click vào 1 showroom thì cửa sổ giờ sẽ mở ra").
    await user.click(screen.getByRole("button", { name: /VinFast Cầu Giấy/ }));

    // sr-1 đang chọn (ghim của MAP): 09:00 còn chỗ, 10:00 kín.
    const nine = screen.getByRole("button", { name: "09:00" });
    expect(screen.getByRole("button", { name: "10:00" })).toBeDisabled();

    // Chưa bấm giờ thì nút Đặt lịch khoá — không được lỡ tay.
    expect(screen.getByRole("button", { name: "Đặt lịch" })).toBeDisabled();

    await user.click(nine);
    expect(nine).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Đặt lịch" }));

    expect(onSendMessage).toHaveBeenCalledWith("__lichlaithu__sr1-0900");
  });

  it("ghim đang trỏ showroom khác: bấm showroom đó thì cột giờ theo đúng nó", async () => {
    const user = userEvent.setup();
    render(
      <TourPanel
        {...noop}
        onSendMessage={vi.fn()}
        panel={{ ...MAP, selectedShowroomId: "sr-2" }}
        sessionId="s1"
        testDriveCard={TD_CARD}
      />,
    );
    await user.click(screen.getByRole("button", { name: /VinFast Long Biên/ }));

    // sr-2: 10:00 còn chỗ, 09:00 kín — ngược với sr-1.
    expect(screen.getByRole("button", { name: "10:00" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "09:00" })).toBeDisabled();
    // Tiêu đề khung lịch nói rõ showroom đang đặt (tên còn xuất hiện ở cột
    // showroom nên phải soi đúng câu tiêu đề).
    expect(screen.getByText("Đặt lịch lái thử VinFast VF 5 — VinFast Long Biên")).toBeInTheDocument();
  });

  it("chọn ghim từ NGOÀI panel (thẻ trong chat) cũng mở khung giờ", async () => {
    // Đồng bộ hai chiều: khách bấm showroom ở thẻ trong chat → ghim đổi qua
    // store → panel phải mở khung giờ y như bấm trong panel.
    const { rerender } = render(
      <TourPanel {...noop} onSendMessage={vi.fn()} panel={MAP} sessionId="s1" testDriveCard={TD_CARD} />,
    );
    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();

    rerender(
      <TourPanel
        {...noop}
        onSendMessage={vi.fn()}
        panel={{ ...MAP, selectedShowroomId: "sr-2" }}
        sessionId="s1"
        testDriveCard={TD_CARD}
      />,
    );
    expect(await screen.findByRole("button", { name: "Đặt lịch" })).toBeInTheDocument();
    expect(screen.getByText("Đặt lịch lái thử VinFast VF 5 — VinFast Long Biên")).toBeInTheDocument();
  });

  it("accordion: click lại showroom đang mở thì khối giờ tắt; click showroom khác thì khối chuyển theo", async () => {
    const user = userEvent.setup();
    render(<TourPanel {...noop} onSendMessage={vi.fn()} panel={MAP} sessionId="s1" testDriveCard={TD_CARD} />);

    const caugiay = screen.getByRole("button", { name: /VinFast Cầu Giấy/ });
    await user.click(caugiay);
    expect(screen.getByText("Đặt lịch lái thử VinFast VF 5 — VinFast Cầu Giấy")).toBeInTheDocument();
    expect(caugiay).toHaveAttribute("aria-expanded", "true");

    // Click lại: khối của chính nó tắt.
    await user.click(caugiay);
    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();
    expect(caugiay).toHaveAttribute("aria-expanded", "false");

    // Click showroom khác: chỉ MỘT khối mở, và là khối của showroom đó.
    await user.click(caugiay);
    await user.click(screen.getByRole("button", { name: /VinFast Long Biên/ }));
    expect(screen.getAllByRole("button", { name: "Đặt lịch" })).toHaveLength(1);
    expect(screen.getByText("Đặt lịch lái thử VinFast VF 5 — VinFast Long Biên")).toBeInTheDocument();
    expect(screen.queryByText("Đặt lịch lái thử VinFast VF 5 — VinFast Cầu Giấy")).toBeNull();
  });

  it("không có thẻ lái thử (hoặc thẻ đang xin vị trí) thì panel không bày khung giờ", () => {
    render(<TourPanel {...noop} onSendMessage={vi.fn()} panel={MAP} sessionId="s1" />);
    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();

    cleanup();
    render(
      <TourPanel
        {...noop}
        onSendMessage={vi.fn()}
        panel={MAP}
        sessionId="s1"
        testDriveCard={{ ...TD_CARD, needs_location: true }}
      />,
    );
    expect(screen.queryByRole("button", { name: "Đặt lịch" })).toBeNull();
  });
});
