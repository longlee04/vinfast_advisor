import { notFound } from "next/navigation";

import { VehicleDetailContent, hasBespokeExperience } from "@/components/catalog/vehicle-detail-content";
import { CustomerShell } from "@/components/shared/customer-shell";
import { getVehicleMenuEntry, vehicleMenuCategories } from "@/mocks/vehicle-menu";

export function generateStaticParams(): { slug: string }[] {
  return vehicleMenuCategories.flatMap((category) =>
    category.vehicles.map((vehicle) => ({ slug: vehicle.id })),
  );
}

export default async function VehicleDetailPage({
  params,
}: Readonly<{
  params: Promise<{ slug: string }>;
}>) {
  const { slug } = await params;
  const vehicle = getVehicleMenuEntry(slug);
  if (!vehicle) notFound();
  // MỘT header cho cả site (Sếp 2026-08-31: trang bespoke tự vẽ header 7 mục
  // kiểu cũ → "2 trạng thái thanh ngang"). Bespoke cũng bọc CustomerShell —
  // header nội bộ + nút chat tròn của experience bị ẩn bằng CSS toàn cục
  // (globals.css, khối "header nội bộ trang chi tiết"); hero full-bleed nên
  // dùng header biến thể overlay.
  const content = <VehicleDetailContent slug={slug} />;
  return <CustomerShell headerVariant={hasBespokeExperience(slug) ? "overlay" : "default"}>{content}</CustomerShell>;
}
