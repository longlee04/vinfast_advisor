"use client";

import L from "leaflet";
// CSS của Leaflet import NGAY TẠI component chứ không qua `@import` trong
// `globals.css`: đường đó rơi rụng trên prod (xem ghi chú đầu `globals.css`).
import "leaflet/dist/leaflet.css";
import Supercluster from "supercluster";
import { useEffect, useRef } from "react";

import type { MapBounds } from "@/lib/api/locations";
import type { MobilityLocation, MobilityLocationCategory, UserPosition } from "@/types/location";

type LocationMapProps = {
  locations: MobilityLocation[];
  selectedId: string | null;
  userPosition: UserPosition | null;
  onSelect: (id: string) => void;
  onBoundsChange?: (bounds: MapBounds) => void;
};

type PointProperties = {
  id: string;
  type: MobilityLocationCategory;
};

type MapFeature = Supercluster.ClusterFeature<Supercluster.AnyProps> | Supercluster.PointFeature<PointProperties>;

const DEFAULT_CENTER: L.LatLngExpression = [16.25, 106.3];

function categoryAppearance(type: MobilityLocationCategory): "showroom" | "service" | "charge" | "swap" {
  if (type.startsWith("showroom")) return "showroom";
  if (type.includes("charging")) return "charge";
  if (type === "battery_swap_station") return "swap";
  return "service";
}

function markerLabel(type: MobilityLocationCategory): string {
  const appearance = categoryAppearance(type);
  if (appearance === "showroom") return "V";
  if (appearance === "charge") return "⚡";
  if (appearance === "swap") return "↻";
  return "●";
}

function markerIcon(type: MobilityLocationCategory, selected: boolean): L.DivIcon {
  const appearance = categoryAppearance(type);
  const className = ["location-map-marker", `is-${appearance}`, selected ? "is-selected" : ""].join(" ");

  return L.divIcon({
    className,
    html: `<span aria-hidden="true"><b>${markerLabel(type)}</b></span>`,
    iconAnchor: [17, 34],
    iconSize: [34, 34],
  });
}

function clusterIcon(count: number): L.DivIcon {
  const size = count >= 10_000 ? 52 : count >= 1_000 ? 46 : count >= 100 ? 40 : 34;
  return L.divIcon({
    className: "location-map-cluster",
    html: `<span style="width:${size}px;height:${size}px">${new Intl.NumberFormat("vi-VN", { notation: "compact" }).format(count)}</span>`,
    iconAnchor: [size / 2, size / 2],
    iconSize: [size, size],
  });
}

function isClusterFeature(feature: MapFeature): feature is Supercluster.ClusterFeature<Supercluster.AnyProps> {
  return "cluster" in feature.properties && feature.properties.cluster === true;
}

export default function LocationMap({ locations, selectedId, userPosition, onSelect, onBoundsChange }: LocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const locationsLayerRef = useRef<L.LayerGroup | null>(null);
  const userLayerRef = useRef<L.LayerGroup | null>(null);
  const indexRef = useRef(new Supercluster<PointProperties>({ maxZoom: 17, minPoints: 3, radius: 62 }));
  const locationsByIdRef = useRef(new Map<string, MobilityLocation>());
  const selectedIdRef = useRef<string | null>(selectedId);
  const onSelectRef = useRef(onSelect);
  const onBoundsChangeRef = useRef(onBoundsChange);
  const renderClustersRef = useRef<() => void>(() => undefined);
  const initialFitDoneRef = useRef(false);
  const flownToUserRef = useRef(false);
  const boundsDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { onSelectRef.current = onSelect; }, [onSelect]);
  useEffect(() => { onBoundsChangeRef.current = onBoundsChange; }, [onBoundsChange]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, { preferCanvas: true, zoomControl: false }).setView(DEFAULT_CENTER, 6);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    L.control.zoom({ position: "bottomright" }).addTo(map);
    locationsLayerRef.current = L.layerGroup().addTo(map);
    userLayerRef.current = L.layerGroup().addTo(map);

    const reportBounds = (): void => {
      const activeMap = mapRef.current;
      if (!activeMap) return;
      try {
        const bounds = activeMap.getBounds();
        if (!bounds || !bounds.isValid()) return;
        onBoundsChangeRef.current?.({
          south: bounds.getSouth(),
          north: bounds.getNorth(),
          west: bounds.getWest(),
          east: bounds.getEast(),
        });
      } catch {
        // Leaflet map pane might not have computed positions yet
      }
    };

    map.on("moveend zoomend", () => {
      renderClustersRef.current();
      if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
      boundsDebounceRef.current = setTimeout(reportBounds, 250);
    });
    mapRef.current = map;

    map.whenReady(() => {
      initTimerRef.current = setTimeout(() => {
        if (!mapRef.current) return;
        try {
          map.invalidateSize();
          reportBounds();
        } catch {
          // ignore layout timing edge-cases
        }
      }, 60);
    });

    // Khung bản đồ đổi cỡ SAU khi Leaflet đã đo (panel trượt vào, xoay máy,
    // sidebar đóng/mở) thì tile lệch và ghim đứng sai chỗ cho tới lần kéo tiếp
    // theo. Một `ResizeObserver` gọi `invalidateSize` đúng lúc, thay vì đoán
    // bằng timer.
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

    return () => {
      observer?.disconnect();
      if (initTimerRef.current) clearTimeout(initTimerRef.current);
      if (boundsDebounceRef.current) clearTimeout(boundsDebounceRef.current);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = locationsLayerRef.current;
    if (!map || !layer) return;

    const points: Array<Supercluster.PointFeature<PointProperties>> = locations.map((location) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [location.longitude, location.latitude] },
      properties: { id: location.id, type: location.type },
    }));
    const index = new Supercluster<PointProperties>({ maxZoom: 17, minPoints: 3, radius: 62 }).load(points);
    indexRef.current = index;
    locationsByIdRef.current = new Map(locations.map((location) => [location.id, location]));

    const renderClusters = (): void => {
      const activeMap = mapRef.current;
      const activeLayer = locationsLayerRef.current;
      if (!activeMap || !activeLayer) return;

      try {
        const bounds = activeMap.getBounds();
        if (!bounds || !bounds.isValid()) return;
        activeLayer.clearLayers();
        const zoom = Math.round(activeMap.getZoom());
        const clusters = index.getClusters(
          [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
          zoom,
        );

        clusters.forEach((feature) => {
          const [longitude, latitude] = feature.geometry.coordinates;
          if (isClusterFeature(feature)) {
            const marker = L.marker([latitude, longitude], {
              icon: clusterIcon(feature.properties.point_count),
              keyboard: true,
              title: `${feature.properties.point_count.toLocaleString("vi-VN")} địa điểm`,
            });
            marker.on("click", () => {
              try {
                const expansionZoom = index.getClusterExpansionZoom(feature.properties.cluster_id);
                activeMap.flyTo([latitude, longitude], expansionZoom, { duration: 0.55 });
              } catch {
                // ignore
              }
            });
            marker.addTo(activeLayer);
            return;
          }

          const location = locationsByIdRef.current.get(feature.properties.id);
          if (!location) return;
          const marker = L.marker([latitude, longitude], {
            icon: markerIcon(location.type, location.id === selectedIdRef.current),
            keyboard: true,
            title: location.name,
          });
          marker.on("click", () => onSelectRef.current(location.id));
          marker.addTo(activeLayer);
        });
      } catch {
        // map pane not ready
      }
    };

    renderClustersRef.current = renderClusters;
    renderClusters();

    if (!initialFitDoneRef.current && locations.length > 0) {
      try {
        const bounds = L.latLngBounds(locations.map((location) => [location.latitude, location.longitude]));
        if (bounds.isValid()) {
          map.fitBounds(bounds, { maxZoom: 11, padding: [48, 48] });
          initialFitDoneRef.current = true;
        }
      } catch {
        // ignore
      }
    }
  }, [locations]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
    const map = mapRef.current;
    const location = selectedId ? locationsByIdRef.current.get(selectedId) : null;
    if (!map || !location) {
      renderClustersRef.current();
      return;
    }

    try {
      map.flyTo([location.latitude, location.longitude], Math.max(map.getZoom(), 15), { duration: 0.65 });
    } catch {
      // ignore
    }
  }, [selectedId]);

  useEffect(() => {
    const map = mapRef.current;
    const userLayer = userLayerRef.current;
    if (!map || !userLayer) return;

    userLayer.clearLayers();
    if (!userPosition) return;

    try {
      const position: L.LatLngExpression = [userPosition.latitude, userPosition.longitude];
      L.circleMarker(position, {
        className: "user-position-marker",
        color: "#ffffff",
        fillColor: "#1464f4",
        fillOpacity: 1,
        radius: 9,
        weight: 4,
      }).addTo(userLayer).bindTooltip("Vị trí của bạn");

      if (!flownToUserRef.current) {
        flownToUserRef.current = true;
        map.flyTo(position, 13, { duration: 0.65 });
      }
    } catch {
      // ignore
    }
  }, [userPosition]);

  return <div aria-label="Bản đồ hệ thống showroom, trạm sạc và dịch vụ" className="location-map-canvas" ref={containerRef} />;
}
