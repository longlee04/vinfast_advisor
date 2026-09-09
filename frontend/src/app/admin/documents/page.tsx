import { PolicyDocumentManager } from "@/components/admin/policy-document-manager";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminDocumentsPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Admin / Controlled sources"
        title="Phân tích chính sách & thông báo"
        description="AI trích xuất dữ liệu có cấu trúc; chỉ nội dung được Admin duyệt và Publish mới hiển thị cho khách hàng."
      />
      <PolicyDocumentManager />
    </OperationalShell>
  );
}
