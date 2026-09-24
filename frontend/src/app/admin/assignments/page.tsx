import { AssignmentCenter } from "@/components/admin/assignment-center";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminAssignmentsPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Admin / Điều hành Phân công"
        title="Khách hàng & phân công"
        description="Chọn khách theo độ nóng, giao cho tư vấn viên phụ trách và xem lịch sử phân công."
      />
      <AssignmentCenter />
    </OperationalShell>
  );
}
