import { AdvisorCustomers } from "@/components/advisor/advisor-customers";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorCustomersPage() {
  return <OperationalShell role="advisor"><PageHeading eyebrow="Advisor / CRM preview" title="Khách hàng được phân công" description="Xem hồ sơ nhu cầu, lịch sử tư vấn và trạng thái chuyển đổi của các khách hàng thuộc phạm vi phụ trách." /><AdvisorCustomers /></OperationalShell>;
}
