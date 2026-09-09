import { AdvisorLiveChat } from "@/components/advisor/advisor-live-chat";
import { OperationalShell } from "@/components/shared/operational-shell";

export default async function AdminConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OperationalShell role="admin"><AdvisorLiveChat conversationId={id} /></OperationalShell>;
}
