import { SalesOpportunityList } from "@/components/advisor/sales-opportunity-list";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorSalesOpportunitiesPage() {
  return (
    <OperationalShell role="advisor">
      <PageHeading
        eyebrow="Advisor / Chủ động"
        title="Cơ hội bán hàng"
        description="Phiên trò chuyện đang chạy đã bộc lộ nút thắt, kèm nguyên văn câu khách nói. Tách khỏi hàng đợi duyệt nội dung — ở đây không duyệt gì, chỉ chọn khách để liên hệ trước."
      />
      <SalesOpportunityList />
    </OperationalShell>
  );
}
