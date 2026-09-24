import { SalesOpportunitiesView } from "@/components/advisor/sales-opportunities-view";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorSalesOpportunitiesPage() {
  return (
    <OperationalShell role="advisor">
      <PageHeading
        eyebrow="Advisor / Chủ động"
        title="Cơ hội bán hàng"
        description="Khách đang có nhu cầu mua, nóng nhất xếp trước. Bấm vào để mở hồ sơ khách và chọn người liên hệ trước."
      />
      <SalesOpportunitiesView />
    </OperationalShell>
  );
}
