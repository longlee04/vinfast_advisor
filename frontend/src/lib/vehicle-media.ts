import type { CatalogVehicle } from "@/lib/api/vehicles";
import { motorbikeMenuCategories } from "@/mocks/motorbike-menu";
import { vehicleMenuCategories } from "@/mocks/vehicle-menu";

const MENU_IMAGES_BY_CATALOG_SLUG = new Map<string, string>([
  ...vehicleMenuCategories.flatMap((category) =>
    category.vehicles.flatMap((vehicle) =>
      vehicle.catalogSlug ? [[vehicle.catalogSlug, vehicle.imageUrl] as const] : [],
    ),
  ),
  ...motorbikeMenuCategories.flatMap((category) =>
    category.motorbikes.map((vehicle) => [vehicle.catalogSlug, vehicle.detailImageUrl] as const),
  ),
]);

/** Chọn ảnh menu chính thức trước, sau đó mới dùng ảnh do Catalog API cung cấp. */
export function resolveCatalogVehicleImage(vehicle: CatalogVehicle): string | null {
  return MENU_IMAGES_BY_CATALOG_SLUG.get(vehicle.slug) ?? vehicle.imageUrl;
}
