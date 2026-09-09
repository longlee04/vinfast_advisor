import { RecommendationsView } from "@/components/recommendations/recommendations-view";
import { CustomerShell } from "@/components/shared/customer-shell";

export default function RecommendationsPage() {
  return <CustomerShell><div className="customer-container recommendations-page"><RecommendationsView /></div></CustomerShell>;
}
