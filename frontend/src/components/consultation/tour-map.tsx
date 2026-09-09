"use client";

import L from "leaflet";
// CSS của Leaflet import NGAY TẠI component — cùng lý do với `location-map.tsx`:
// `@import` trong `globals.css` không lọt vào bundle prod.
import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";

import type { NavigateShowroom } from "@/types/agent";

type TourMapProps = {
  center: { readonly lat: number; readonly lng: number } | null;
  showrooms: readonly NavigateShowroom[];
  selectedId: string | null;
  onSelect: (showroomId: string) => void;
};

const VIETNAM_CENTER: L.LatLngExpression = [16.25, 106.3];

/**
 * Ghim showroom: dùng lại `.location-map-marker.is-showroom` của bản đồ
 * /locations — `divIcon` nên không phụ thuộc ảnh marker mặc định của Leaflet
 * (đường ảnh đó vỡ khi bundle, là lỗi kinh điển với Next).
 */
function showroomIcon(selected: boolean): L.DivIcon {
  return L.divIcon({
    className: ["location-map-marker", "is-showroom", selected ? "is-selected" : ""].join(" "),
    html: '<span aria-hidden="true"><b>V</b></span>',
    iconAnchor: [17, 34],
    iconSize: [34, 34],
  });
}

const USER_ICON = L.divIcon({
  className: "tour-map-user",
  html: '<span aria-hidden="true"></span>',
  iconAnchor: [9, 9],
  iconSize: [18, 18],
});

/**
 * Bản đồ trong panel "trang web đi theo hội thoại" (đợt 9): vị trí khách (nếu
 * có) + ghim showroom của thẻ lái thử cùng lượt. Bấm ghim = chọn showroom —
 * đồng bộ với cột showroom trong thẻ qua `onSelect`/`selectedId` ở store.
 *
 * Nhẹ hơn `location-map.tsx`: vài ghim, không cluster, không báo bounds.
 */
export default function TourMap({ center, showrooms, selectedId, onSelect }: TourMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const pinsRef = useRef<L.LayerGroup | null>(null);
  // Khung nhìn mong muốn (mọi ghim + vị trí khách) — dùng lại sau khi panel
  // trượt xong: lúc effect vẽ ghim chạy, panel có thể còn rộng 0px.
  const targetBoundsRef = useRef<L.LatLngBounds | null>(null);
  // Khoá của lần fit gần nhất: chọn showroom khác chỉ đổi MÀU ghim (selectedId
  // vẫn nằm trong deps để vẽ lại icon) — cùng bộ điểm thì KHÔNG bay lại, bản đồ
  // đứng yên dưới tay khách.
  const boundsKeyRef = useRef<string | null>(null);
  const onSelectRef = useRef(onSelect);
  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: false }).setView(VIETNAM_CENTER, 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    pinsRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;

    // Panel trượt vào SAU khi Leaflet đã đo khung (width đi từ 0 → 45%): không
    // `invalidateSize` thì tile chỉ vẽ ở góc và ghim đứng sai chỗ.
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            try {
              map.invalidateSize();
            } catch {
              // map đã bị gỡ giữa chừng
            }
          })
        : null;
    observer?.observe(containerRef.current);

    // Sau khi panel trượt xong (`transitionend` của `.tour-panel`): đo lại rồi
    // bay tới các ghim với animate — "chuyển cảnh mượt" (Sếp 2026-08-31). Trong
    // lúc trượt thì KHÔNG fit: khung đang đổi cỡ từng frame, fit lúc đó ra sai.
    const panel = containerRef.current.closest(".tour-panel");
    const onTransitionEnd = (event: Event): void => {
      if (event.target !== panel) return;
      // Đợt 11: transform và opacity giờ cùng duration (mở 400ms/đóng 320ms,
      // đồng pha với lưới chat) nên MỖI lần trượt bắn hai transitionend — không
      // lọc thì flyToBounds gọi hai phát liền, phát sau tự ngắt phát trước.
      // Chỉ nghe transform: mobile chỉ transition transform, desktop có thêm
      // opacity, nên lọc này đúng cho cả hai.
      if ((event as TransitionEvent).propertyName !== "transform") return;
      try {
        map.invalidateSize();
        const bounds = targetBoundsRef.current;
        if (bounds) map.flyToBounds(bounds, { animate: true, duration: 0.6, maxZoom: 14, padding: [36, 36] });
      } catch {
        // map đã bị gỡ giữa chừng
      }
    };
    panel?.addEventListener("transitionend", onTransitionEnd);

    // Đợt 10: chat co/giãn bằng transition GRID trên `.consultation-workspace`
    // (panel là vai chính) — bề rộng panel đổi mà panel KHÔNG có transition
    // riêng, nên `transitionend` của chính panel không bắn cho ca này. Nghe
    // thêm ở workspace: lưới trượt xong thì đo lại và bay về các ghim. Trong
    // lúc trượt, ResizeObserver ở trên đã `invalidateSize` từng nhịp nên tile
    // không vẽ lệch; reduced-motion không có transition thì nhánh fit-ngay bên
    // dưới đã lo.
    const workspace = containerRef.current.closest(".consultation-workspace");
    const onGridSettled = (event: Event): void => {
      if (event.target !== workspace) return;
      if ((event as TransitionEvent).propertyName !== "grid-template-columns") return;
      try {
        map.invalidateSize();
        const bounds = targetBoundsRef.current;
        if (bounds) map.flyToBounds(bounds, { animate: true, duration: 0.6, maxZoom: 14, padding: [36, 36] });
      } catch {
        // map đã bị gỡ giữa chừng
      }
    };
    workspace?.addEventListener("transitionend", onGridSettled);

    // reduced-motion: JS đã bỏ `.is-animated` nên panel hiện TỨC THỜI — không có
    // transition thì `transitionend` không bao giờ tới. Fit ngay ở frame kế
    // (panel lúc đó đã có kích thước), không animate.
    let reducedFitFrame = 0;
    if (panel && !panel.classList.contains("is-animated")) {
      reducedFitFrame = requestAnimationFrame(() => {
        try {
          map.invalidateSize();
          const bounds = targetBoundsRef.current;
          if (bounds) map.flyToBounds(bounds, { animate: false, maxZoom: 14, padding: [36, 36] });
        } catch {
          // map đã bị gỡ giữa chừng
        }
      });
    }

    return () => {
      if (reducedFitFrame) cancelAnimationFrame(reducedFitFrame);
      workspace?.removeEventListener("transitionend", onGridSettled);
      panel?.removeEventListener("transitionend", onTransitionEnd);
      observer?.disconnect();
      map.remove();
      mapRef.current = null;
      pinsRef.current = null;
    };
  }, []);

  //: Marker theo showroom_id — để click ghim chỉ ĐỔI ICON, không đập đi xây lại.
  const markersRef = useRef(new Map<string, L.Marker>());
  const selectedIdRef = useRef(selectedId);
  selectedIdRef.current = selectedId;

  useEffect(() => {
    const map = mapRef.current;
    const pins = pinsRef.current;
    if (!map || !pins) return;
    pins.clearLayers();
    markersRef.current.clear();
    const points: L.LatLngExpression[] = [];
    if (center) {
      L.marker([center.lat, center.lng], { icon: USER_ICON, interactive: false, zIndexOffset: 500 }).addTo(pins);
      points.push([center.lat, center.lng]);
    }
    for (const showroom of showrooms) {
      const marker = L.marker([showroom.lat, showroom.lng], {
        icon: showroomIcon(showroom.showroom_id === selectedIdRef.current),
        title: showroom.name,
        zIndexOffset: showroom.showroom_id === selectedIdRef.current ? 1000 : 0,
      });
      marker.on("click", () => onSelectRef.current(showroom.showroom_id));
      marker.addTo(pins);
      markersRef.current.set(showroom.showroom_id, marker);
      points.push([showroom.lat, showroom.lng]);
    }
    if (points.length === 0) return;
    const bounds = L.latLngBounds(points);
    targetBoundsRef.current = bounds;
    // Cùng bộ điểm như lần trước → không bay lại.
    const boundsKey = JSON.stringify(points);
    if (boundsKeyRef.current === boundsKey) return;
    boundsKeyRef.current = boundsKey;
    try {
      map.flyToBounds(bounds, { animate: true, duration: 0.6, maxZoom: 14, padding: [36, 36] });
    } catch {
      // khung chưa có kích thước — ResizeObserver sẽ gọi lại invalidateSize
    }
  }, [center, showrooms]);

  // Đổi ghim đang chọn: CHỈ đổi icon/z-index của các marker sẵn có. Bản cũ để
  // `selectedId` trong effect trên nên mỗi cú click là clearLayers + dựng lại
  // toàn bộ ghim — phần lớn cảm giác "map đơ" mà người dùng phàn nàn 2026-08-31.
  useEffect(() => {
    for (const [id, marker] of markersRef.current) {
      marker.setIcon(showroomIcon(id === selectedId));
      marker.setZIndexOffset(id === selectedId ? 1000 : 0);
    }
  }, [selectedId]);

  return <div aria-label="Bản đồ showroom" className="tour-map-canvas" ref={containerRef} role="application" />;
}
