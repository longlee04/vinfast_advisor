import { CatalogPreview } from "@/components/admin/catalog-preview";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminVehiclesPage() {
  return <OperationalShell role="admin"><PageHeading eyebrow="Admin / Sản phẩm" title="Danh sách phương tiện" description="Quản lý thông tin và trạng thái các mẫu xe trong hệ thống." /><CatalogPreview /></OperationalShell>;
}
