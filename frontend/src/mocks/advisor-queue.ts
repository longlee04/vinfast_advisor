import type { AdvisorQueueItem } from "@/types/demo";

export const initialAdvisorQueue: AdvisorQueueItem[] = [
  {
    id: "review-0182",
    customerName: "Khách hàng #VF-101",
    customerEmail: "customer.101@example.com",
    proposedVehicleIds: ["vf6-plus", "vf7-base", "vf5-plus"],
    submittedAt: "Hôm nay, 15:22",
    priority: "high",
    status: "pending",
    generatedAt: "04/08/2026 · 15:22",
    warningLabels: ["Camera 360 chưa xác định"],
  },
  {
    id: "review-0181",
    customerName: "Khách hàng #VF-102",
    customerEmail: "customer.102@example.com",
    proposedVehicleIds: ["vf7-base", "vf6-plus"],
    submittedAt: "Hôm nay, 15:16",
    priority: "normal",
    status: "pending",
    generatedAt: "04/08/2026 · 15:16",
    warningLabels: [],
  },
  {
    id: "review-0179",
    customerName: "Khách hàng #VF-104",
    customerEmail: "customer.104@example.com",
    proposedVehicleIds: ["vf5-plus"],
    submittedAt: "Hôm nay, 15:04",
    priority: "normal",
    status: "approved",
    generatedAt: "04/08/2026 · 15:04",
    warningLabels: [],
  },
];
