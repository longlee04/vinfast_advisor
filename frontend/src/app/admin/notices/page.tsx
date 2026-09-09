import { NoticePreview } from "@/components/admin/notice-preview";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminNoticesPage() {
  return <OperationalShell role="admin"><PageHeading eyebrow="Admin / Vận hành" title="Thông báo nội bộ" description="Theo dõi trạng thái đọc và tạo thông báo cho đội ngũ tư vấn." /><NoticePreview /></OperationalShell>;
}
