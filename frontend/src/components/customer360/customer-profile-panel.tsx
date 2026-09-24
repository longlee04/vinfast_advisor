"use client";

import { ExternalLink, Gift } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchBottleneckSignals } from "@/lib/api/agent";
import type { BottleneckSignal } from "@/types/agent";
import type { Barrier, ViewerRole } from "@/types/customer360";

import { BarrierList } from "./barrier-list";
import { knownSlots } from "./customer360-labels";
import { customerProfileHref } from "./profile-links";

export type CustomerProfilePanelProps = {
  readonly conversationId: string;
  readonly customerId: string | null;
  readonly customerLabel: string;
  readonly slots: Record<string, unknown> | undefined;
  readonly hitlReasons: readonly string[];
  readonly role: ViewerRole;
  readonly readOnly: boolean;
};

/** Nút thắt của ĐÚNG phiên này (chờ xác nhận hoặc đã xác nhận đúng). */
async function sessionSignals(conversationId: string): Promise<readonly BottleneckSignal[]> {
  const [pending, correct] = await Promise.all([
    fetchBottleneckSignals({ status: "pending", limit: 100 }).catch(() => [] as readonly BottleneckSignal[]),
    fetchBottleneckSignals({ status: "correct", limit: 100 }).catch(() => [] as readonly BottleneckSignal[]),
  ]);
  return [...pending, ...correct].filter((signal) => signal.session_id === conversationId);
}

/**
 * Panel phải của live chat (plan Customer 360, Phase 3): khách cần gì, vướng gì, việc tiếp
 * theo — chỉ từ dữ liệu thật. Thay cho panel cũ có dòng "Dữ liệu đã xác thực / Không có
 * cảnh báo" viết cứng và mức ưu tiên mặc định "HIGH" không từ nguồn nào.
 */
export function CustomerProfilePanel({ conversationId, customerId, customerLabel, slots, hitlReasons, role, readOnly }: CustomerProfilePanelProps) {
  const [signals, setSignals] = useState<readonly BottleneckSignal[]>([]);

  useEffect(() => {
    let active = true;
    sessionSignals(conversationId).then((items) => {
      if (active) setSignals(items);
    });
    return () => {
      active = false;
    };
  }, [conversationId]);

  const needs = knownSlots(slots);
  const barriers: Barrier[] = signals.map((signal) => ({
    code: signal.label,
    source: "BOTTLENECK",
    evidence_quote: signal.evidence_quote,
    turn_index: null,
    session_id: signal.session_id,
    status: signal.status,
  }));
  const confirmed = signals.find((signal) => signal.status === "CORRECT");

  return (
    <aside aria-label="Hồ sơ khách" className="advisor-chat-context-panel customer360-live-panel">
      <div className="context-heading">
        <span className="eyebrow">Thông tin khách hàng</span>
        <strong>{customerLabel}</strong>
        <span className="context-session">#{conversationId.slice(0, 8)}</span>
      </div>

      <section>
        <h3>Nhu cầu</h3>
        {needs.length ? (
          <dl>
            {needs.map((item) => (
              <div key={item.slot}>
                <dt>{item.label}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="customer360-empty">Chưa thu được thông tin nhu cầu.</p>
        )}
      </section>

      {hitlReasons.length ? (
        <section>
          <h3>Lý do cần hỗ trợ</h3>
          <p>{hitlReasons.join(", ")}</p>
        </section>
      ) : null}

      <section>
        <h3>Rào cản</h3>
        <BarrierList items={barriers} />
      </section>

      {!readOnly && confirmed ? (
        <Link className="secondary-button full-button" href={`/advisor/bottleneck-signals/${confirmed.signal_id}`}>
          <Gift size={15} /> Cấp ưu đãi cho rào cản đã xác nhận
        </Link>
      ) : null}

      {customerId ? (
        <Link className="table-action" href={customerProfileHref(customerId, role)}>
          Xem hồ sơ khách đầy đủ <ExternalLink size={13} />
        </Link>
      ) : null}
    </aside>
  );
}
