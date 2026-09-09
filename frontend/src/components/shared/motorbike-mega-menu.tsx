"use client";

import {
  CatalogMegaMenu,
  MobileCatalogMenu,
  type CatalogMegaMenuCategory,
} from "@/components/shared/catalog-mega-menu";
import { motorbikeMenuCategories } from "@/mocks/motorbike-menu";

const MOTORBIKE_CATEGORIES: CatalogMegaMenuCategory[] = motorbikeMenuCategories.map((category) => ({
  id: category.id,
  label: category.label,
  items: category.motorbikes,
}));

export function MotorbikeMegaMenu() {
  return (
    <CatalogMegaMenu
      categories={MOTORBIKE_CATEGORIES}
      defaultCategory="popular"
      idPrefix="motorbike-menu"
      triggerLabel="Xe máy điện"
    />
  );
}

export function MobileMotorbikeMenu({
  onMotorbikeClick,
}: Readonly<{
  onMotorbikeClick: () => void;
}>) {
  return (
    <MobileCatalogMenu
      ariaLabel="Các dòng xe máy điện"
      categories={MOTORBIKE_CATEGORIES}
      defaultCategory="popular"
      idPrefix="mobile-motorbike-menu"
      onItemClick={onMotorbikeClick}
    />
  );
}
