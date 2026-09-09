import { AdvisorReviewPanel } from "@/components/advisor/advisor-review-panel";
import { OperationalShell } from "@/components/shared/operational-shell";

export default async function AdvisorReviewPage({ params }: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;
  return <OperationalShell role="advisor"><AdvisorReviewPanel reviewId={id} /></OperationalShell>;
}
