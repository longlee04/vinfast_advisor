import { Suspense } from "react";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { CustomerShell } from "@/components/shared/customer-shell";
import { AgentSessionProvider } from "@/store/agent-session";

type ConsultationPageProps = {
  readonly searchParams: Promise<{ readonly prompt?: string | readonly string[]; readonly conversation?: string | readonly string[] }>;
};

export default async function ConsultationPage({ searchParams }: ConsultationPageProps) {
  const promptValue = (await searchParams).prompt;
  const conversationValue = (await searchParams).conversation;
  const initialPrompt = Array.isArray(promptValue) ? promptValue[0] : promptValue;
  const conversationId = Array.isArray(conversationValue) ? conversationValue[0] : conversationValue;

  return (
    <CustomerShell>
      <AgentSessionProvider conversationId={conversationId}>
        <Suspense fallback={<div className="consultation-stage" />}>
          <ConsultationFlow initialPrompt={initialPrompt} initialConversationId={conversationId} />
        </Suspense>
      </AgentSessionProvider>
    </CustomerShell>
  );
}
