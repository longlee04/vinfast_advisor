"use client";

import { ChatSessionTable } from "@/components/shared/chat-session-table";

/** Màn TVV `/advisor/conversations` — bảng dùng chung, phạm vi "của tôi" (backend lọc theo phân công). */
export function AdvisorConversationList() {
  return <ChatSessionTable scope="mine" />;
}
