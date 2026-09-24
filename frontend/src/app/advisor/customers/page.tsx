import { AdvisorPageHeading } from "@/components/advisor/advisor-features";
import { SalesOpportunitiesView } from "@/components/advisor/sales-opportunities-view";
import { WaitingCustomers } from "@/components/advisor/waiting-customers";
import { OperationalShell } from "@/components/shared/operational-shell";

/** "Khách hàng" = gộp "Cơ hội bán hàng" + "Khách hàng được phân công" + "Hội thoại" (plan §17, §18). */
export default function AdvisorCustomersPage() {
  return (
    <OperationalShell role="advisor">
      <AdvisorPageHeading feature="customers" />
      <WaitingCustomers />
      <SalesOpportunitiesView />
    </OperationalShell>
  );
}
