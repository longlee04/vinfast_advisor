// @vitest-environment jsdom

import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Leaflet giả: chỉ đủ để chứng minh "invalidateSize được gọi SAU khi panel
 * trượt xong" — jsdom không có layout thật để test bằng bản đồ thật.
 */
const { fakeMap } = vi.hoisted(() => ({
  fakeMap: {
    setView: vi.fn(),
    invalidateSize: vi.fn(),
    flyToBounds: vi.fn(),
    remove: vi.fn(),
  },
}));

vi.mock("leaflet", () => {
  const layer = () => ({ addTo: vi.fn().mockReturnThis(), on: vi.fn(), clearLayers: vi.fn(), setIcon: vi.fn(), setZIndexOffset: vi.fn() });
  return {
    default: {
      map: vi.fn(() => ({ ...fakeMap, setView: fakeMap.setView.mockReturnValue(fakeMap) })),
      tileLayer: layer,
      control: { zoom: layer },
      layerGroup: layer,
      marker: layer,
      divIcon: vi.fn(() => ({})),
      latLngBounds: vi.fn((points: unknown) => ({ points })),
    },
  };
});

import TourMap from "@/components/consultation/tour-map";

const SHOWROOMS = [
  { showroom_id: "sr-1", name: "A", address: "HN", lat: 21.03, lng: 105.79 },
  { showroom_id: "sr-2", name: "B", address: "HN", lat: 21.04, lng: 105.88 },
];

describe("TourMap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("đo lại (invalidateSize) và bay tới ghim sau transitionend của panel", () => {
    render(
      <aside className="tour-panel is-open">
        <TourMap center={null} onSelect={vi.fn()} selectedId="sr-1" showrooms={SHOWROOMS} />
      </aside>,
    );
    // Vẽ ghim lần đầu đã fit một lần; đếm từ đây.
    expect(fakeMap.flyToBounds).toHaveBeenCalledTimes(1);
    fakeMap.invalidateSize.mockClear();

    const panel = document.querySelector(".tour-panel")!;
    // Đợt 11: listener chỉ nghe propertyName "transform" (transform và opacity
    // giờ cùng kết thúc — không lọc là flyToBounds bắn đôi). jsdom không có
    // constructor TransitionEvent nên gắn propertyName bằng defineProperty.
    const slideEnd = new Event("transitionend", { bubbles: true });
    Object.defineProperty(slideEnd, "propertyName", { value: "transform" });
    panel.dispatchEvent(slideEnd);

    expect(fakeMap.invalidateSize).toHaveBeenCalledTimes(1);
    expect(fakeMap.flyToBounds).toHaveBeenCalledTimes(2);
    expect(fakeMap.flyToBounds.mock.calls[1][1]).toMatchObject({ animate: true });

    // transitionend của OPACITY (cùng lúc với transform) thì bỏ qua — không đo
    // lại lần hai, không tự ngắt cú bay đang chạy.
    const fadeEnd = new Event("transitionend", { bubbles: true });
    Object.defineProperty(fadeEnd, "propertyName", { value: "opacity" });
    panel.dispatchEvent(fadeEnd);
    expect(fakeMap.flyToBounds).toHaveBeenCalledTimes(2);
  });

  it("transitionend nổi lên từ phần tử con (fade nội dung) thì KHÔNG đo lại", () => {
    const { container } = render(
      <aside className="tour-panel is-open">
        <TourMap center={null} onSelect={vi.fn()} selectedId={null} showrooms={SHOWROOMS} />
      </aside>,
    );
    fakeMap.invalidateSize.mockClear();

    container.querySelector(".tour-map-canvas")!.dispatchEvent(new Event("transitionend", { bubbles: true }));

    expect(fakeMap.invalidateSize).not.toHaveBeenCalled();
  });

  it("chỉ đổi ghim được chọn (selectedId) thì KHÔNG bay lại — chọn showroom chỉ đổi màu ghim", () => {
    const { rerender } = render(
      <aside className="tour-panel is-open is-animated">
        <TourMap center={null} onSelect={vi.fn()} selectedId="sr-1" showrooms={SHOWROOMS} />
      </aside>,
    );
    expect(fakeMap.flyToBounds).toHaveBeenCalledTimes(1);

    rerender(
      <aside className="tour-panel is-open is-animated">
        <TourMap center={null} onSelect={vi.fn()} selectedId="sr-2" showrooms={SHOWROOMS} />
      </aside>,
    );

    expect(fakeMap.flyToBounds).toHaveBeenCalledTimes(1);
  });

  it("panel không chuyển cảnh (reduced-motion, thiếu .is-animated): fit ngay sau rAF, không chờ transitionend", async () => {
    render(
      <aside className="tour-panel is-open">
        <TourMap center={null} onSelect={vi.fn()} selectedId={null} showrooms={SHOWROOMS} />
      </aside>,
    );
    fakeMap.invalidateSize.mockClear();

    // KHÔNG dispatch transitionend — reduced-motion không có transition nào cả.
    await vi.waitFor(() => expect(fakeMap.invalidateSize).toHaveBeenCalled());
    const lastFly = fakeMap.flyToBounds.mock.calls.at(-1);
    expect(lastFly?.[1]).toMatchObject({ animate: false });
  });
});
