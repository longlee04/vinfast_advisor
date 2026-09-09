/**
 * Client cho Catalog API thật (`/api/v1/vehicles*`). Thay cho `mocks/vehicles`
 * trước đây — component chỉ nên biết `CatalogVehicle`, không biết shape API.
 */

import { withSessionRetry } from "@/lib/api/session";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

type ApiPrice = { price_type: string; amount_vnd: number; status: string };

type ApiShowcaseItem = {
  showcase_item_id: string;
  section_key: string;
  item_key: string;
  title: string;
  description: string | null;
  media_url: string | null;
  media_alt: string | null;
  display_order: number;
  source_url: string;
  source_retrieved_at: string;
};

type ApiVehicleDetail = {
  vehicle: {
    vehicle_id: string;
    vehicle_type: "CAR" | "ELECTRIC_MOTORBIKE";
    brand: string;
    model_name: string;
    variant_name: string | null;
    model_year: number | null;
    status: string;
    slug: string;
    image_url: string | null;
    detail_url: string | null;
  };
  // Backend trả specs dạng chuỗi số (vd "210.00") và tên trường khác nhau giữa
  // CAR (range_km, fast_charge_time_minutes/home_charge_time_minutes) và
  // ELECTRIC_MOTORBIKE (range_max_km, charging_time_minutes).
  specs: Record<string, string | number | boolean | null> | null;
  prices: ApiPrice[];
  feature_flags?: Array<{ name: string; status: string; verification_status: string }>;
  showcase_items?: ApiShowcaseItem[];
  promotions?: Array<{ promotion_id: string; vehicle_id: string }>;
};

export type VehicleShowcaseItem = {
  id: string;
  section: string;
  key: string;
  title: string;
  description: string | null;
  mediaUrl: string | null;
  mediaAlt: string;
  order: number;
  sourceUrl: string;
  sourceRetrievedAt: string;
};

export type CatalogVehicle = {
  id: string;
  slug: string;
  modelName: string;
  variant: string;
  vehicleType: "car" | "electric_motorbike";
  priceVnd: number | null;
  priceType: string | null;
  rangeKm: number | null;
  seats: number | null;
  chargeMinutes: number | null;
  batteryCapacityKwh: number | null;
  imageUrl: string | null;
  detailUrl: string | null;
  specs: Record<string, string | number | boolean | null>;
  unknownFeatureNames: string[];
  showcaseItems: VehicleShowcaseItem[];
  promotionIds?: string[];
};

// `PROMOTION_PRICE` có thời hạn, `BATTERY_SUBSCRIPTION` là mô hình thuê pin đã
// ngừng bán — không dùng cho hiển thị catalog. Khớp PRICE_PREFERENCE ở
// src/products/application/tco_service.py.
const PRICE_PREFERENCE = ["BATTERY_INCLUDED", "STARTING_PRICE"] as const;

function pickPrice(prices: ApiPrice[]): { amount: number; type: string } | null {
  const active = prices.filter((price) => price.status === "ACTIVE");
  for (const wanted of PRICE_PREFERENCE) {
    const found = active.find((price) => price.price_type === wanted);
    if (found) return { amount: found.amount_vnd, type: found.price_type };
  }
  return null;
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function toCatalogVehicle(detail: ApiVehicleDetail): CatalogVehicle {
  const specs = detail.specs ?? {};
  const price = pickPrice(detail.prices ?? []);
  return {
    id: detail.vehicle.vehicle_id,
    slug: detail.vehicle.slug,
    modelName: detail.vehicle.model_name,
    variant: detail.vehicle.variant_name ?? "",
    vehicleType: detail.vehicle.vehicle_type === "CAR" ? "car" : "electric_motorbike",
    priceVnd: price?.amount ?? null,
    priceType: price?.type ?? null,
    rangeKm: toNumber(specs.range_km ?? specs.range_max_km),
    seats: toNumber(specs.seat_count),
    chargeMinutes: toNumber(specs.fast_charge_time_minutes ?? specs.charging_time_minutes ?? specs.home_charge_time_minutes),
    batteryCapacityKwh: toNumber(specs.battery_capacity_kwh),
    imageUrl: detail.vehicle.image_url,
    detailUrl: detail.vehicle.detail_url,
    specs,
    unknownFeatureNames: (detail.feature_flags ?? [])
      .filter((feature) => feature.status === "UNKNOWN")
      .map((feature) => feature.name),
    promotionIds: (detail.promotions ?? []).map((promotion) => promotion.promotion_id),
    showcaseItems: (detail.showcase_items ?? []).map((item) => ({
      id: item.showcase_item_id,
      section: item.section_key,
      key: item.item_key,
      title: item.title,
      description: item.description,
      mediaUrl: item.media_url,
      mediaAlt: item.media_alt ?? item.title,
      order: item.display_order,
      sourceUrl: item.source_url,
      sourceRetrievedAt: item.source_retrieved_at,
    })),
  };
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);
  if (!response.ok) throw new Error(`request failed: ${response.status}`);
  return response.json() as Promise<T>;
}

/** Ném ra bởi các lời gọi `/admin/*` khi response không OK, giữ nguyên status
 * HTTP để UI phân biệt 401/403 (chưa đăng nhập / không đủ quyền) với lỗi khác. */
export class VehicleApiError extends Error {
  constructor(public readonly status: number) {
    super(`request failed: ${status}`);
    this.name = "VehicleApiError";
  }
}

async function getJsonAsAdmin<T>(path: string): Promise<T> {
  // Cùng cơ chế giữ phiên với `agent.ts`/`auth.ts`: access token sống 15 phút,
  // gặp 401 thì làm mới bằng refresh token rồi gọi lại. Bỏ sót màn admin ở đây
  // thì phiên vẫn "hết hạn" đúng chỗ người vận hành ngồi lâu nhất.
  const response = await withSessionRetry(() =>
    fetch(`${API_BASE_URL}${path}`, { credentials: "include" }),
  );
  if (!response.ok) throw new VehicleApiError(response.status);
  return response.json() as Promise<T>;
}

export async function fetchVehicles(params: {
  vehicleType?: "car" | "electric_motorbike";
  page?: number;
  pageSize?: number;
} = {}): Promise<CatalogVehicle[]> {
  const query = new URLSearchParams();
  if (params.vehicleType) {
    query.set("vehicle_type", params.vehicleType === "car" ? "CAR" : "ELECTRIC_MOTORBIKE");
  }
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 60));
  const payload = await getJson<{ data: ApiVehicleDetail[] }>(`/vehicles?${query.toString()}`);
  return payload.data.map(toCatalogVehicle);
}

export async function fetchVehicle(identifier: string): Promise<CatalogVehicle> {
  const payload = await getJson<{ data: ApiVehicleDetail }>(`/vehicles/${identifier}`);
  return toCatalogVehicle(payload.data);
}

// `GET /admin/vehicles` trả về đúng shape ApiVehicleDetail như /vehicles công
// khai (xem `_detail_out` trong src/products/presentation/routes.py), chỉ thêm
// khả năng thấy các status ngoài ACTIVE (DRAFT/INACTIVE/ARCHIVED) và yêu cầu
// cookie phiên ADMIN — 401/403 nếu chưa đăng nhập / không đủ quyền.
export type AdminVehicle = CatalogVehicle & { status: string };

function toAdminVehicle(detail: ApiVehicleDetail): AdminVehicle {
  return { ...toCatalogVehicle(detail), status: detail.vehicle.status };
}

export type AdminVehiclePage = {
  items: AdminVehicle[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
};

type ApiListResponse = {
  data: ApiVehicleDetail[];
  pagination: { page: number; page_size: number; total_items: number; total_pages: number };
};

export async function fetchAdminVehicles(params: {
  status?: string;
  page?: number;
  pageSize?: number;
} = {}): Promise<AdminVehiclePage> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 100));
  const payload = await getJsonAsAdmin<ApiListResponse>(`/admin/vehicles?${query.toString()}`);
  return {
    items: payload.data.map(toAdminVehicle),
    page: payload.pagination.page,
    pageSize: payload.pagination.page_size,
    totalItems: payload.pagination.total_items,
    totalPages: payload.pagination.total_pages,
  };
}

export type TcoResult = {
  breakdown: {
    vehicle_price_vnd: number;
    price_type: string;
    registration_fee_vnd: number;
    plate_fee_vnd: number;
    inspection_fee_vnd: number;
    inspection_count: number;
    insurance_vnd: number;
    road_fee_vnd: number;
    electricity_vnd: number;
    maintenance_vnd: number;
    maintenance_count: number;
    total_km: number;
    total_upfront_vnd: number;
    total_ownership_vnd: number;
  };
  assumptions: {
    /** Khu vực lệ phí biển số đã dùng để tính — hai khu vực chênh nhau 100 lần. */
    region_code: "KHU_VUC_I" | "KHU_VUC_II";
    assumption_version: number;
    electricity_vnd_per_kwh: number;
    registration_fee_percent: string;
    horizon_months: number;
    source_note: string;
  };
  consumption: {
    kwh_per_100km: string;
    source: "published" | "derived";
    derivation: string | null;
  };
};

export async function fetchTco(
  identifier: string,
  province: string,
  monthlyKm: number,
  years: number,
  signal?: AbortSignal,
): Promise<TcoResult> {
  // Lệ phí biển số ô tô: 14.000.000đ ở Hà Nội/TP.HCM (Khu vực I), 140.000đ ở
  // các tỉnh còn lại (Khu vực II). Tỉnh cụ thể thì gửi lên; "Tỉnh/thành khác"
  // là MÃ RỖNG — không gửi param, backend dùng mặc định Khu vực II. Bản cũ điền
  // bừa "Cần Thơ" cho mọi tỉnh còn lại: đúng số tiền nhưng bịa dữ liệu.
  const query = new URLSearchParams({
    monthly_distance_km: String(monthlyKm),
    ownership_years: String(years),
  });
  if (province) query.set("province", province);
  const response = await fetch(`${API_BASE_URL}/vehicles/${identifier}/tco?${query.toString()}`, { signal });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "unknown" }));
    throw new Error(body.detail ?? "unknown");
  }
  const payload = (await response.json()) as { data: TcoResult };
  return payload.data;
}
