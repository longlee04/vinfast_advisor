import { ProductExperience } from "@/components/product/product-experience";
import { Mpv7Experience } from "@/components/mpv7/mpv7-experience";
import { Vf2Experience } from "@/components/vf2/vf2-experience";
import { Vf3Experience } from "@/components/vf3/vf3-experience";
import { Vf5Experience } from "@/components/vf5/vf5-experience";
import { Vf6Experience } from "@/components/vf6/vf6-experience";
import { Vf7Experience } from "@/components/vf7/vf7-experience";
import { Vf8Experience } from "@/components/vf8/vf8-experience";
import { Vf8AllNewExperience } from "@/components/vf8-all-new/vf8-all-new-experience";
import { Vf9Experience } from "@/components/vf9/vf9-experience";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";

/**
 * Nội dung trang chi tiết xe theo `slug` — MỘT nguồn cho hai chỗ dùng: route
 * `/vehicles/[slug]` và panel "trang web đi theo hội thoại" (đợt 9) nhúng cạnh
 * khung chat. Trước đây bảng slug → experience nằm thẳng trong `page.tsx`;
 * panel mà chép lại bảng đó thì thêm một mẫu xe là hai chỗ phải nhớ sửa.
 *
 * Không có `"use client"`: file này chỉ chọn component, và mọi experience đã là
 * client component — nên cả server page lẫn panel client đều import được.
 *
 * Trả `null` khi slug lạ: route thì gọi `notFound()`, panel thì hiện lời xin lỗi
 * kèm liên kết — mỗi chỗ tự quyết, đây không quyết hộ.
 */
export function VehicleDetailContent({ slug }: Readonly<{ slug: string }>): React.JSX.Element | null {
  if (slug === "vf-2") return <Vf2Experience />;
  if (slug === "vf-3") return <Vf3Experience />;
  if (slug === "vf-5") return <Vf5Experience />;
  if (slug === "vf-6") return <Vf6Experience />;
  if (slug === "vf-7") return <Vf7Experience />;
  if (slug === "vf-mpv-7") return <Mpv7Experience />;
  if (slug === "vf-8") return <Vf8Experience />;
  if (slug === "vf-8-all-new") return <Vf8AllNewExperience />;
  if (slug === "vf-9") return <Vf9Experience />;
  const vehicle = getVehicleMenuEntry(slug);
  if (!vehicle) return null;
  return <ProductExperience category="car" categoryLabel={vehicle.categoryLabel} vehicle={vehicle} />;
}

/** Có nội dung chi tiết cho slug này không (để panel biết mà xin lỗi thay vì trống). */
export function hasVehicleDetail(slug: string): boolean {
  return hasBespokeExperience(slug) || getVehicleMenuEntry(slug) !== undefined;
}

/** Mẫu có trang riêng (không cần `CustomerShell` bọc ngoài). */
export function hasBespokeExperience(slug: string): boolean {
  return ["vf-2", "vf-3", "vf-5", "vf-6", "vf-7", "vf-mpv-7", "vf-8", "vf-8-all-new", "vf-9"].includes(slug);
}
