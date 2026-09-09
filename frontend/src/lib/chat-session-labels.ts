import type { ChatSessionStatus } from "@/types/chat-observability";

export const chatSessionStatusLabels: Record<ChatSessionStatus, string> = {
  ACTIVE: "Đang hoạt động",
  WAITING_ADVISOR: "Chờ Advisor",
  ADVISOR_CONNECTED: "Advisor đang xử lý",
  CLOSED: "Đã đóng",
  TRANSFERRED: "Đã chuyển",
};

export const chatSessionStatusTones: Record<ChatSessionStatus, "info" | "warning" | "success" | "neutral"> = {
  ACTIVE: "info",
  WAITING_ADVISOR: "warning",
  ADVISOR_CONNECTED: "info",
  CLOSED: "success",
  TRANSFERRED: "neutral",
};