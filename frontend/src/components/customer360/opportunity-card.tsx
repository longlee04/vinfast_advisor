import { Flag, Lightbulb, ListChecks } from "lucide-react";
import type { ReactNode } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import type {
  Barrier,
  BuyerFor,
  FieldValue,
  HeatBand,
  OpportunityStatus,
  SalesStage,
  ValueHistory,
} from "@/types/customer360";

import { BarrierList } from "./barrier-list";
import {
  BUYER_FOR_LABELS,
  HEAT_BAND_BADGES,
  INSIGHT_FIELD_LABELS,
  OPPORTUNITY_STATUS_LABELS,
  SALES_STAGE_LABELS,
  SALES_STAGE_ORDER,
  SLOT_LABELS,
  formatSlotValue,
  knownSlots,
} from "./customer360-labels";

export type OpportunityCardData = {
  readonly title: string;
  readonly status?: OpportunityStatus;
  readonly heatBreakdown?: readonly { readonly code: string; readonly points: number; readonly detail: string }[];
  /** Lịch sử đổi giá trị theo slot ("850tr (trước: 700tr)"). */
  readonly history?: Record<string, readonly ValueHistory[]>;
  readonly insights?: readonly (FieldValue & { readonly insight_id: string; readonly field: string })[];
  readonly openingHint?: string;
  readonly nextActions?: readonly { readonly code: string; readonly label: string }[];
  readonly buyerFor?: BuyerFor;
  readonly stage?: SalesStage;
  readonly heatBand?: HeatBand;
  readonly heatScore?: number;
  /** Slot đã có (slot → giá trị thô); nhãn và định dạng do card lo. */
  readonly slots: Record<string, unknown>;
  readonly missing?: readonly string[];
  readonly evaded?: readonly string[];
  readonly barriers: readonly Pick<Barrier, "code" | "evidence_quote" | "session_id" | "turn_index">[];
};

export type OpportunityCardProps = {
  readonly opportunity: OpportunityCardData;
  readonly readOnly: boolean;
  /** TVV báo một insight sai — Admin (readOnly) không có nút này. */
  readonly onInsightFeedback?: (insightId: string) => void;
  /** Khối "Ưu đãi phù hợp" (Phase 5) — trang hồ sơ truyền vào khi cờ bật. */
  readonly offerSlot?: ReactNode;
};

function slotName(slot: string): string {
  return SLOT_LABELS[slot] ?? slot;
}

function breakdownTitle(parts: OpportunityCardData["heatBreakdown"]): string | undefined {
  if (!parts?.length) return undefined;
  return parts.map((part) => `${part.points > 0 ? "+" : ""}${part.points} ${part.detail}`).join("\n");
}

/**
 * Một nhu cầu mua (plan §2.1 tầng Cơ hội): cần gì, còn thiếu gì, khách né gì, vướng đâu,
 * nên làm gì tiếp. Trước khi bật Customer 360 hồ sơ dựng card từ slot phiên gần nhất nên
 * giai đoạn/độ nóng/gợi ý chỉ hiện khi có dữ liệu.
 */
export function OpportunityCard({ opportunity, readOnly, onInsightFeedback, offerSlot }: OpportunityCardProps) {
  const known = knownSlots(opportunity.slots);
  const heat = opportunity.heatBand ? HEAT_BAND_BADGES[opportunity.heatBand] : null;
  const stageIndex = opportunity.stage ? SALES_STAGE_ORDER.indexOf(opportunity.stage) : -1;
  const subtitle = [
    opportunity.buyerFor ? BUYER_FOR_LABELS[opportunity.buyerFor] : null,
    opportunity.status && opportunity.status !== "OPEN" ? OPPORTUNITY_STATUS_LABELS[opportunity.status] : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <article aria-label={opportunity.title} className="customer360-opportunity" data-readonly={readOnly || undefined}>
      <header>
        <div>
          <h3>{opportunity.title}</h3>
          {subtitle ? <small>{subtitle}</small> : null}
        </div>
        {heat ? (
          <span title={breakdownTitle(opportunity.heatBreakdown)}>
            <StatusBadge tone={heat.tone}>
              {heat.label}
              {opportunity.heatScore !== undefined ? ` · ${opportunity.heatScore}` : ""}
            </StatusBadge>
          </span>
        ) : null}
      </header>

      {stageIndex >= 0 ? (
        <ol aria-label="Giai đoạn" className="customer360-stages">
          {SALES_STAGE_ORDER.map((stage, index) => (
            <li aria-current={index === stageIndex ? "step" : undefined} data-reached={index <= stageIndex || undefined} key={stage}>
              {SALES_STAGE_LABELS[stage]}
            </li>
          ))}
        </ol>
      ) : null}

      {opportunity.openingHint ? (
        <p className="customer360-hint">
          <Lightbulb size={15} /> {opportunity.openingHint}
        </p>
      ) : null}

      <section>
        <h4>Nhu cầu đã có</h4>
        {known.length ? (
          <dl className="customer360-needs">
            {known.map((item) => {
              const previous = opportunity.history?.[item.slot]?.at(-1);
              return (
                <div key={item.slot}>
                  <dt>{item.label}</dt>
                  <dd>
                    {item.value}
                    {previous ? <small> (trước: {formatSlotValue(item.slot, previous.value) ?? previous.value})</small> : null}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <p className="customer360-empty">Chưa thu được thông tin nhu cầu.</p>
        )}
        {opportunity.missing?.length ? (
          <p className="customer360-gaps">
            <strong>Còn thiếu:</strong> {opportunity.missing.map(slotName).join(", ")}
          </p>
        ) : null}
        {opportunity.evaded?.length ? (
          <p className="customer360-gaps">
            <strong>Khách né:</strong> {opportunity.evaded.map(slotName).join(", ")}
          </p>
        ) : null}
      </section>

      <section>
        <h4>Rào cản</h4>
        <BarrierList items={opportunity.barriers} />
      </section>

      {opportunity.insights?.length ? (
        <section>
          <h4>Khách đã nói</h4>
          <ul className="customer360-insights">
            {opportunity.insights.map((insight) => (
              <li key={insight.insight_id}>
                <strong>{INSIGHT_FIELD_LABELS[insight.field] ?? insight.field}:</strong> {insight.value}
                {insight.evidence_quote ? <blockquote>“{insight.evidence_quote}”</blockquote> : null}
                {!readOnly && onInsightFeedback ? (
                  <button className="text-button" onClick={() => onInsightFeedback(insight.insight_id)} type="button">
                    <Flag size={13} /> Báo sai
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {offerSlot ? (
        <section>
          <h4>Ưu đãi phù hợp</h4>
          {offerSlot}
        </section>
      ) : null}

      {opportunity.nextActions?.length ? (
        <section>
          <h4>
            <ListChecks size={14} /> Việc cần làm
          </h4>
          <ul className="customer360-actions">
            {opportunity.nextActions.map((action) => (
              <li key={action.code}>{action.label}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </article>
  );
}
