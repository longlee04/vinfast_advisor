import { MessageSquare } from "lucide-react";

import { ChatSessionList } from "@/components/admin/chat-session-list";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminChatSessionsPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Admin / Observability"
        title="Phiên chat"
        description="Quản lý và theo dõi các phiên tư vấn của khách hàng."
        actions={
          <span className="status-badge status-info">
            <MessageSquare size={14} /> AI observability
          </span>
        }
      />
      <ChatSessionList />
    </OperationalShell>
  );
}

