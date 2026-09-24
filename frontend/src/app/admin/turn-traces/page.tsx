import { TurnTraceTabs } from "@/components/admin/extraction-quality-panel";
import { OperationalShell } from "@/components/shared/operational-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function TurnTracesPage() {
  return (
    <OperationalShell role="admin">
      <PageHeading
        eyebrow="Quan sát"
        title="Vì sao agent đáp như vậy"
        description="Mỗi lượt một dòng: máy chấm điểm ý định thế nào, LLM gắn nhãn gì, cửa tất định nào đã bật. Dùng để hiệu chuẩn ngưỡng tin cậy trước khi bật nó lên thật."
      />
      <TurnTraceTabs />
    </OperationalShell>
  );
}
