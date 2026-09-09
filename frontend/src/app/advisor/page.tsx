import { AdvisorQueueTable } from "@/components/advisor/advisor-queue-table";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorPage() {
  return (
    <OperationalShell role="advisor">
      <PageHeading
        description="Kiểm tra đề xuất báo giá, yêu cầu khách hàng và cảnh báo từ hệ thống AI (Dữ liệu PostgreSQL)."
        eyebrow="Hôm nay · Advisor"
        title="Hàng đợi chờ duyệt"
      />
      <AdvisorQueueTable />
    </OperationalShell>
  );
}
