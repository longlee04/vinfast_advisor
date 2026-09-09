import { LiveChatSessionDetail } from "@/components/admin/live-chat-session-detail";
import { OperationalShell } from "@/components/shared/operational-shell";

export default async function AdminChatSessionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <OperationalShell role="admin">
      <LiveChatSessionDetail id={id} />
    </OperationalShell>
  );
}