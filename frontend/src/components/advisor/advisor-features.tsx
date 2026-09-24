import { CalendarDays, ClipboardCheck, ContactRound, Gift, LayoutDashboard } from "lucide-react";
import type { ReactNode } from "react";

import { PageHeading } from "@/components/shared/page-heading";

/**
 * 5 tính năng của tư vấn viên (plan §17, §18 — "Hội thoại" đã gộp vào "Khách hàng").
 * MỘT nguồn cho menu lẫn tiêu đề trang, để nhãn menu, tiêu đề và dòng mô tả nghiệp vụ
 * không bao giờ lệch nhau.
 *
 * Mỗi `description` trả lời "trang này để làm gì trong công việc bán hàng", không mô tả
 * giao diện.
 */
export const ADVISOR_FEATURES = {
  home: {
    href: "/advisor",
    label: "Tổng quan",
    title: "Tổng quan khách của tôi",
    description: "Bắt đầu ngày làm việc ở đây: việc cần làm với khách của bạn, khách mới chờ nhận và thông báo nội bộ.",
    icon: LayoutDashboard,
  },
  customers: {
    href: "/advisor/customers",
    label: "Khách hàng",
    title: "Khách hàng",
    description:
      "Tab “Đã nhận”: khách bạn phụ trách, nóng nhất xếp trước — mở hồ sơ để xem hội thoại, nhu cầu, rào cản và việc nên làm. Tab “Chưa nhận”: khách mới để nhận. Khách xin gặp tư vấn viên hiện ngay trên đầu để tiếp quản.",
    icon: ContactRound,
    /** Live chat (`/advisor/conversations/[id]`) là việc của một khách — thuộc mục này. */
    match: ["/advisor/customers", "/advisor/conversations"],
  },
  review: {
    href: "/advisor/queue",
    label: "Duyệt nội dung AI",
    title: "Duyệt nội dung AI",
    description: "Kiểm tra bản nháp báo giá, đề xuất và nút thắt AI phát hiện trước khi đến tay khách — không có gì sai được gửi đi.",
    icon: ClipboardCheck,
  },
  testDrives: {
    href: "/advisor/test-drives",
    label: "Lịch lái thử",
    title: "Lịch lái thử",
    description: "Lịch lái thử khách đã đặt — xác nhận hoặc gọi lại để khách đến showroom đúng giờ, đúng xe.",
    icon: CalendarDays,
  },
  promotions: {
    href: "/advisor/promotions",
    label: "Ưu đãi",
    title: "Ưu đãi",
    description: "Quản lý chương trình ưu đãi (điều kiện, hạn mức tự cấp) và duyệt ưu đãi vượt hạn mức của đồng nghiệp.",
    icon: Gift,
  },
} as const;

export type AdvisorFeatureKey = keyof typeof ADVISOR_FEATURES;

/** Thứ tự menu — việc hằng ngày trước, việc quản lý sau. */
export const ADVISOR_MENU: readonly AdvisorFeatureKey[] = ["home", "customers", "review", "testDrives", "promotions"];

/** Tiêu đề trang của một tính năng: tên + một dòng mô tả nghiệp vụ. */
export function AdvisorPageHeading({ feature, actions }: Readonly<{ feature: AdvisorFeatureKey; actions?: ReactNode }>) {
  const item = ADVISOR_FEATURES[feature];
  return <PageHeading actions={actions} description={item.description} eyebrow="Tư vấn viên" title={item.title} />;
}
