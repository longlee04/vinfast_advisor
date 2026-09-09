import { VehicleCatalog } from "@/components/catalog/vehicle-catalog";
import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function MotorbikesPage() {
  return <CustomerShell><div className="customer-wide-container"><PageHeading eyebrow="Xe máy điện VinFast" title="Chọn phong cách di chuyển của bạn" description="Khám phá các mẫu xe máy điện qua hình ảnh chính thức, thông số local và trang chi tiết riêng." /><VehicleCatalog initialFilter="electric_motorbike" /></div></CustomerShell>;
}
