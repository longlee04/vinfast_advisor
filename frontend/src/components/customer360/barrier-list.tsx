import { bottleneckLabel } from "@/components/advisor/offer-state-labels";
import type { Barrier } from "@/types/customer360";

export type BarrierListProps = {
  readonly items: readonly Pick<Barrier, "code" | "evidence_quote" | "session_id" | "turn_index">[];
  /**
   * Bằng chứng đã qua `redact_pii` ở backend (Phase 0). Hiện nhãn để người đọc biết
   * dấu `[SĐT]`/`[EMAIL]` là do hệ thống che, không phải khách gõ như vậy.
   */
  readonly redacted?: boolean;
};

/** Rào cản của khách, mỗi mục kèm câu nguyên văn làm bằng chứng. */
export function BarrierList({ items, redacted = true }: BarrierListProps) {
  if (items.length === 0) {
    return <p className="customer360-empty">Chưa ghi nhận rào cản nào.</p>;
  }
  return (
    <div className="customer360-barriers">
      <ul>
        {items.map((item, index) => (
          <li key={`${item.session_id}-${item.turn_index ?? index}-${item.code}`}>
            <strong>{bottleneckLabel(item.code)}</strong>
            <blockquote>{item.evidence_quote}</blockquote>
          </li>
        ))}
      </ul>
      {redacted ? <small>Đã che thông tin liên hệ trong câu trích.</small> : null}
    </div>
  );
}
