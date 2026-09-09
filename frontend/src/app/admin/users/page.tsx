import { UserManagementPreview } from "@/components/admin/user-management-preview";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminUsersPage() {
  return <OperationalShell role="admin"><PageHeading eyebrow="Admin / Access" title="Quản lý người dùng" description="Danh sách tài khoản và phân quyền từ Auth API." /><UserManagementPreview /></OperationalShell>;
}
