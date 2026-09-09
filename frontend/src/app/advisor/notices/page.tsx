import { AdvisorNotices } from "@/components/advisor/advisor-notices";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorNoticesPage() {
  return <OperationalShell role="advisor"><PageHeading eyebrow="Advisor / Chính sách" title="Thông báo nội bộ" description="Các thay đổi về giá, ưu đãi, bảo hành và quy trình cần biết trước khi tư vấn khách hàng." /><AdvisorNotices /></OperationalShell>;
}
