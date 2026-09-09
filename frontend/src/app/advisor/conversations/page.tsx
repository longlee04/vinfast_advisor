import { AdvisorConversationList } from "@/components/advisor/advisor-conversation-list";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdvisorConversationsPage() {
  return (
    <OperationalShell role="advisor">
      <PageHeading
        description="Theo dõi và xử lý các phiên tư vấn được phân công cho bạn."
        eyebrow="Advisor / Hội thoại"
        title="Phiên tư vấn của tôi"
      />
      <AdvisorConversationList />
    </OperationalShell>
  );
}
