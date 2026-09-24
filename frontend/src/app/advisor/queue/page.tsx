import { AdvisorPageHeading } from "@/components/advisor/advisor-features";
import { AdvisorQueueTable } from "@/components/advisor/advisor-queue-table";
import { OperationalShell } from "@/components/shared/operational-shell";

export default function AdvisorQueuePage() {
  return (
    <OperationalShell role="advisor">
      <AdvisorPageHeading feature="review" />
      <AdvisorQueueTable />
    </OperationalShell>
  );
}
