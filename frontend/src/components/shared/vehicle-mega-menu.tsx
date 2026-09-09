"use client";

import {
  CatalogMegaMenu,
  MobileCatalogMenu,
  type CatalogMegaMenuCategory,
} from "@/components/shared/catalog-mega-menu";
import { vehicleMenuCategories } from "@/mocks/vehicle-menu";

const VEHICLE_CATEGORIES: CatalogMegaMenuCategory[] = vehicleMenuCategories.map((category) => ({
  id: category.id,
  label: category.label,
  items: category.vehicles,
}));

export function VehicleMegaMenu() {
  return (
    <CatalogMegaMenu
      categories={VEHICLE_CATEGORIES}
      defaultCategory="electric"
      idPrefix="vehicle-menu"
      triggerLabel="Ô tô"
    />
  );
}

export function MobileVehicleMenu({
  onVehicleClick,
}: Readonly<{
  onVehicleClick: () => void;
}>) {
  return (
    <MobileCatalogMenu
      ariaLabel="Các dòng ô tô"
      categories={VEHICLE_CATEGORIES}
      defaultCategory="electric"
      idPrefix="mobile-vehicle-menu"
      onItemClick={onVehicleClick}
    />
  );
}
