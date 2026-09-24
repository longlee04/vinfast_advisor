import { AdvisorPageHeading } from "@/components/advisor/advisor-features";
import { PromotionManager } from "@/components/advisor/promotion-manager";
import { OperationalShell } from "@/components/shared/operational-shell";

export default function AdvisorPromotionsPage() {
  return (
    <OperationalShell role="advisor">
      <AdvisorPageHeading feature="promotions" />
      <PromotionManager />
    </OperationalShell>
  );
}
