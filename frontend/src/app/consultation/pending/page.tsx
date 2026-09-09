import { PendingApproval } from "@/components/consultation/pending-approval";
import { CustomerShell } from "@/components/shared/customer-shell";
import { AgentSessionProvider } from "@/store/agent-session";

export default function PendingPage() {
  return (
    <CustomerShell>
      <AgentSessionProvider>
        <PendingApproval />
      </AgentSessionProvider>
    </CustomerShell>
  );
}
