import { AdvisorLiveChat } from "@/components/advisor/advisor-live-chat";
import { OperationalShell } from "@/components/shared/operational-shell";

export default async function AdvisorConversationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <OperationalShell role="advisor"><AdvisorLiveChat conversationId={id} /></OperationalShell>;
}
