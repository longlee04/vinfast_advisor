import { VehicleCatalog } from "@/components/catalog/vehicle-catalog";
import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function VehiclesPage() {
  return <CustomerShell><div className="customer-wide-container"><PageHeading eyebrow="Dải sản phẩm VinFast" title="Khám phá các dòng xe" description="Lọc ô tô hoặc xe máy điện, xem thông tin chi tiết và chọn những mẫu xe bạn muốn so sánh." /><VehicleCatalog /></div></CustomerShell>;
}
