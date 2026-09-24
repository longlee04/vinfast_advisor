import { PromotionManager } from "@/components/admin/promotion-manager";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AdminPromotionsPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Admin / Ưu đãi"
        title="Ưu đãi"
        description="Tạo, dựng điều kiện áp dụng, kích hoạt và theo dõi hiệu quả ưu đãi."
      />
      <PromotionManager />
    </OperationalShell>
  );
}
