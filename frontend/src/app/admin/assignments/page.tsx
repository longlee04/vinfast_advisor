import { AssignmentCenter } from "@/components/admin/assignment-center";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminAssignmentsPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Admin / Điều hành Phân công"
        title="Trung tâm Phân công Khách hàng"
        description="Phân bổ và điều phối quan hệ chăm sóc giữa Khách hàng và Tư vấn viên (Customer Lead Allocation)."
      />
      <AssignmentCenter />
    </OperationalShell>
  );
}
