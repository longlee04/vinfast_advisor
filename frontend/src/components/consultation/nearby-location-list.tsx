"use client";

import { BatteryCharging, MapPin, Navigation, Phone, Store, Wrench, Zap } from "lucide-react";

import type { NearbyLocation, NearbyLocationList } from "@/types/agent";

/** `location_type` → icon + nhãn. Giá trị lạ dùng nhãn server gửi kèm, không đoán. */
const KIND_PRESENTATION: Readonly<
  Record<string, { readonly label: string; readonly Icon: typeof Store }>
> = {
  SHOWROOM_CAR: { label: "Showroom Ô tô", Icon: Store },
  SHOWROOM_MOTORBIKE: { label: "Showroom Xe máy điện", Icon: Store },
  CHARGING_STATION_CAR: { label: "Trạm sạc Ô tô điện", Icon: Zap },
  CHARGING_STATION_MOTORBIKE: { label: "Trạm sạc Xe máy điện", Icon: Zap },
  BATTERY_SWAP_CABINET: { label: "Tủ đổi pin", Icon: BatteryCharging },
  SERVICE_WORKSHOP_CAR: { label: "Xưởng dịch vụ Ô tô", Icon: Wrench },
  SERVICE_WORKSHOP_MOTORBIKE: { label: "Xưởng dịch vụ Xe máy điện", Icon: Wrench },
};

/**
 * Khoảng cách đọc được. Dưới 1 km đổi sang mét — "0.4 km" đọc chậm hơn "khoảng
 * 400 m", và đây là con số khách quyết định dựa vào. Cùng luật với
 * `domain/nearby_location.format_distance` phía backend, cố ý lặp lại ở đây vì
 * client chỉ nhận số thô và tự định dạng theo ngôn ngữ của nó.
 */
function formatDistance(distanceKm: number | null): string {
  if (distanceKm === null || !Number.isFinite(distanceKm)) return "Chưa rõ khoảng cách";
  if (distanceKm < 1) return `Cách khoảng ${Math.round(distanceKm * 1000)} m`;
  return `Cách khoảng ${distanceKm.toFixed(1)} km`;
}

function presentation(location: NearbyLocation) {
  return (
    KIND_PRESENTATION[location.location_type] ?? {
      label: location.category_label,
      Icon: MapPin,
    }
  );
}

function LocationCard({ location }: Readonly<{ location: NearbyLocation }>): React.JSX.Element {
  const { label, Icon } = presentation(location);
  const hours =
    location.open_time && location.close_time
      ? `${location.open_time} - ${location.close_time}`
      : null;

  return (
    <article className="nearby-location-card">
      <div className="nearby-location-card-top">
        <span className="nearby-location-symbol" aria-hidden="true">
          <Icon size={20} />
        </span>
        <div className="nearby-location-main">
          <div className="nearby-location-header">
            <span className="nearby-location-type-badge">{label}</span>
            <span className="nearby-location-distance-badge">{formatDistance(location.distance_km)}</span>
          </div>
          <h3 className="nearby-location-title">{location.name}</h3>
          <p className="nearby-location-address">
            <MapPin aria-hidden="true" size={14} /> <span>{location.address}</span>
          </p>
          <div className="nearby-location-meta">
            {hours ? (
              <span className="nearby-location-meta-item">
                <span className="opacity-75">Giờ mở cửa:</span> {hours}
              </span>
            ) : null}
            {location.hotline ? (
              <a
                className="nearby-location-hotline"
                href={`tel:${location.hotline.replace(/\s+/g, "")}`}
              >
                <Phone aria-hidden="true" size={12} /> <span>{location.hotline}</span>
              </a>
            ) : null}
            {location.maps_url ? (
              <a
                className="nearby-location-directions"
                href={location.maps_url}
                rel="noreferrer"
                target="_blank"
              >
                <Navigation aria-hidden="true" size={13} /> <span>Chỉ đường Google Maps</span>
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  );
}

/**
 * Danh sách địa điểm do agent trả về, hiện ngay trong dòng hội thoại.
 *
 * Chỉ ÁNH XẠ payload sang card — không sắp xếp lại, không tính lại khoảng cách,
 * không lọc lại theo loại, không ghép lại `maps_url`. Backend đã chốt cả bốn từ
 * chính dữ liệu `locations`; làm lại ở đây là dựng bộ tính thứ hai, và nó sẽ lệch
 * khỏi câu dẫn mà agent vừa viết ngay lần đổi đơn vị đầu tiên.
 *
 * Trả `null` khi lượt đang CHỜ loại hoặc CHỜ vị trí: hai màn đó là nút bấm
 * (`quick_replies`) và `LocationRequest`, không phải một danh sách rỗng.
 */
export function NearbyLocationCards({
  locations,
}: Readonly<{ locations: NearbyLocationList }>): React.JSX.Element | null {
  if (locations.needs_location_kind || locations.needs_location) return null;
  if (locations.results.length === 0) {
    // Danh sách rỗng KHÔNG được im lặng: câu dẫn trong bong bóng đã nói rõ đã
    // quét bao xa, nên ở đây chỉ cần không dựng một khối trống.
    return null;
  }
  return (
    <div className="nearby-location-list">
      {locations.results.map((location) => (
        <LocationCard key={location.id} location={location} />
      ))}
      {locations.origin_label ? (
        <p className="nearby-location-origin">Tính từ: {locations.origin_label}</p>
      ) : null}
    </div>
  );
}
