export type MobilityLocationCategory =
  | "showroom_car"
  | "showroom_escooter"
  | "service_car"
  | "service_car_partner"
  | "service_bus"
  | "service_escooter"
  | "service_gsm"
  | "car_charging_station"
  | "bike_charging_station"
  | "battery_swap_station";

export type MobilityLocationStatus = "open" | "maintenance";

export type MobilityLocation = {
  id: string;
  name: string;
  type: MobilityLocationCategory;
  categoryLabel: string;
  address: string;
  city: string;
  district: string;
  latitude: number;
  longitude: number;
  openingHours: string;
  status: MobilityLocationStatus;
  phone?: string;
  directionsUrl?: string;
  source: string;
  /** Chỉ có giá trị khi bản ghi đến từ `/locations/nearby` (backend tính sẵn). */
  distanceKm?: number;
};

export type UserPosition = {
  latitude: number;
  longitude: number;
};
