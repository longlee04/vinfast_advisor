import Link from "next/link";

import type { Barrier, ViewerRole } from "@/types/customer360";

import { barrierLabel, shortDate } from "./customer360-labels";

export type BarrierRowsProps = {
  readonly items: readonly Pick<Barrier, "code" | "evidence_quote" | "session_id" | "turn_index" | "at">[];
  readonly role: ViewerRole;
};

/**
 * "Rào cản khách đã nói ra" (mockup 02): nhãn · câu nguyên văn (đã che liên hệ ở backend) ·
 * link tới đúng lượt trong hội thoại. Rào cản đầu tiên là rào cản chính nên tô cam.
 */
export function BarrierRows({ items, role }: BarrierRowsProps) {
  return (
    <ul className="c360-barrier-rows">
      {items.map((item, index) => {
        const where = [item.turn_index !== null ? `Lượt ${item.turn_index}` : null, shortDate(item.at)].filter(Boolean).join(" · ");
        const href = `/${role}/conversations/${encodeURIComponent(item.session_id)}${item.turn_index !== null ? `#turn-${item.turn_index}` : ""}`;
        return (
          <li key={`${item.session_id}-${item.turn_index ?? index}-${item.code}`}>
            <span className="c360-chip" data-tone={index === 0 ? "primary" : undefined}>
              {barrierLabel(item.code)}
            </span>
            <q>{item.evidence_quote}</q>
            <Link href={href}>{where || "Mở hội thoại"}</Link>
          </li>
        );
      })}
    </ul>
  );
}
