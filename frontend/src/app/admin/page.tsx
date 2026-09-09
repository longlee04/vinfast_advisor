import { AdminDashboard } from "@/components/admin/admin-dashboard";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminPage() {
  return <OperationalShell role="admin"><PageHeading eyebrow="Admin preview" title="Tổng quan sản phẩm" description="Các chỉ số chỉ dùng để trình diễn bố cục và không đến từ analytics pipeline thật." /><AdminDashboard /></OperationalShell>;
}
