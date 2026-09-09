/**
 * Client cho Locations API thật (`/api/v1/locations*`). Thay cho các file
 * JSON tĩnh trước đây (`public/locations/**`, nay đã bị xoá) — component chỉ
 * nên biết `MobilityLocation`, không biết shape API.
 */

import type { MobilityLocation, MobilityLocationCategory, MobilityLocationStatus } from "@/types/location";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

type LocationOut = {
  id: string;
  external_id: string;
  type: string;
  category_label: string;
  name: string;
  address: string;
  city: string;
  district: string | null;
  latitude: string;
  longitude: string;
  hotline: string | null;
  directions_url: string | null;
  open_time: string | null;
  close_time: string | null;
  status: string | null;
  distance_km: string | null;
};

export type LocationListResult = {
  items: MobilityLocation[];
  total: number;
  truncated: boolean;
};

export type LocationCategory = { id: string; label: string; count: number };
export type LocationRegion = { city: string; districts: string[] };

export type MapBounds = { south: number; north: number; west: number; east: number };

// Nguồn dữ liệu trả "1" (phổ biến) hoặc "True" (một phần nhỏ bản ghi) cho
// trạng thái đang hoạt động; mọi giá trị khác coi là tạm ngừng. Đây là vấn đề
// chất lượng dữ liệu ở tầng crawl/seed, không xử lý gì thêm ở đây ngoài việc
// quy đổi hai dạng "truthy" đã quan sát được về "open".
function mapStatus(raw: string | null): MobilityLocationStatus {
  if (!raw) return "maintenance";
  const normalized = raw.trim().toLowerCase();
  return normalized === "1" || normalized === "true" ? "open" : "maintenance";
}

function toMobilityLocation(row: LocationOut): MobilityLocation {
  const openingHours =
    row.open_time && row.close_time ? `${row.open_time} - ${row.close_time}` : "Chưa có dữ liệu";
  return {
    id: row.external_id,
    name: row.name,
    type: row.type as MobilityLocationCategory,
    categoryLabel: row.category_label,
    address: row.address,
    city: row.city,
    district: row.district ?? "Chưa có dữ liệu quận/huyện",
    latitude: Number(row.latitude),
    longitude: Number(row.longitude),
    openingHours,
    status: mapStatus(row.status),
    phone: row.hotline ?? undefined,
    directionsUrl: row.directions_url ?? undefined,
    source: "api",
    distanceKm: row.distance_km != null ? Number(row.distance_km) : undefined,
  };
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { signal });
  if (!response.ok) {
    // FastAPI trả lỗi dạng {"detail": "..."} hoặc {"detail": [{"msg": "..."}]}
    // (422 validation) — không phải {"error": "..."}. Đã xác nhận bằng curl
    // thật trên backend, không theo giả định trong bản nháp.
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
    const detail = body?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => (item as { msg?: string }).msg ?? "unknown").join("; ")
          : `HTTP ${response.status}`;
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export async function fetchLocations(
  params: {
    bounds?: MapBounds;
    types?: string[];
    city?: string;
    district?: string;
    q?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<LocationListResult> {
  const query = new URLSearchParams();
  if (params.bounds) {
    query.set("south", String(params.bounds.south));
    query.set("north", String(params.bounds.north));
    query.set("west", String(params.bounds.west));
    query.set("east", String(params.bounds.east));
  }
  (params.types ?? []).forEach((type) => query.append("types", type));
  if (params.city && params.city !== "all") query.set("city", params.city);
  if (params.district && params.district !== "all") query.set("district", params.district);
  if (params.q) query.set("q", params.q);
  query.set("limit", String(params.limit ?? 500));

  const payload = await getJson<{ items: LocationOut[]; total: number; truncated: boolean }>(
    `/locations?${query.toString()}`,
    signal,
  );
  return {
    items: payload.items.map(toMobilityLocation),
    total: payload.total,
    truncated: payload.truncated,
  };
}

export async function fetchNearby(
  params: {
    latitude: number;
    longitude: number;
    radiusKm?: number;
    types?: string[];
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<LocationListResult> {
  const query = new URLSearchParams();
  query.set("lat", String(params.latitude));
  query.set("lon", String(params.longitude));
  query.set("radius_km", String(params.radiusKm ?? 10));
  (params.types ?? []).forEach((type) => query.append("types", type));
  query.set("limit", String(params.limit ?? 50));

  const payload = await getJson<{ items: LocationOut[]; total: number; truncated: boolean }>(
    `/locations/nearby?${query.toString()}`,
    signal,
  );
  return {
    items: payload.items.map(toMobilityLocation),
    total: payload.total,
    truncated: payload.truncated,
  };
}

export async function fetchCategories(): Promise<LocationCategory[]> {
  return getJson<LocationCategory[]>("/locations/categories");
}

export async function fetchRegions(): Promise<LocationRegion[]> {
  return getJson<LocationRegion[]>("/locations/regions");
}
