import type { AdminMetric, InternalNotice } from "@/types/demo";

export const adminMetrics: AdminMetric[] = [
  { label: "Hội thoại", value: "2.480", change: "+12,6%" },
  { label: "Hồ sơ hoàn tất", value: "2.068", change: "83,4%" },
  { label: "Đề xuất đã duyệt", value: "1.342", change: "74% nguyên trạng" },
  { label: "Yêu cầu lái thử", value: "318", change: "12,8% chuyển đổi" },
];

export const internalNotices: InternalNotice[] = [
  { id: "notice-1", title: "Cập nhật ưu đãi VF 7 tháng 8", priority: "high", createdAt: "04/08/2026", readCount: 18, audienceCount: 24 },
  { id: "notice-2", title: "Quy trình xác nhận lịch lái thử", priority: "normal", createdAt: "04/08/2026", readCount: 22, audienceCount: 24 },
  { id: "notice-3", title: "Chính sách bảo hành pin cập nhật", priority: "normal", createdAt: "03/08/2026", readCount: 24, audienceCount: 24 },
];
