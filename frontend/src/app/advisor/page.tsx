import { AdvisorPageHeading } from "@/components/advisor/advisor-features";
import { AdvisorHome } from "@/components/advisor/advisor-home";
import { OperationalShell } from "@/components/shared/operational-shell";

export default function AdvisorPage() {
  return (
    <OperationalShell role="advisor">
      <AdvisorPageHeading feature="home" />
      <AdvisorHome />
    </OperationalShell>
  );
}
