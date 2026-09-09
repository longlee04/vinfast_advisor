import { motorbikeMenuCategories } from "@/mocks/motorbike-menu";
import { vehicleMenuCategories } from "@/mocks/vehicle-menu";

type MenuVehicle = { readonly name: string; readonly href: string };

const MENU_VEHICLES: readonly MenuVehicle[] = [
  ...vehicleMenuCategories.flatMap((category) => category.vehicles),
  ...motorbikeMenuCategories.flatMap((category) => category.motorbikes),
].sort((left, right) => right.name.length - left.name.length);

function normalizedName(value: string): string {
  return value
    .toLocaleLowerCase("vi-VN")
    .replace(/vinfast/g, " ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Resolve a card display name to an existing internal product page. */
export function productHrefForVehicle(displayName: string): string | null {
  const candidate = ` ${normalizedName(displayName)} `;
  for (const vehicle of MENU_VEHICLES) {
    const menuName = ` ${normalizedName(vehicle.name)} `;
    if (candidate.includes(menuName)) return vehicle.href;
  }
  return null;
}

/** Open chat with an exact vehicle target while preserving a return link. */
export function consultationHref(vehicleName: string, from: string): string {
  const query = new URLSearchParams({
    prompt: `Cho tôi thông tin chi tiết về ${vehicleName}`,
    from,
  });
  return `/consultation?${query.toString()}`;
}
