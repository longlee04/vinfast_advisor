"use client";

import { Flag } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useState } from "react";

import type {
  Barrier,
  BuyerFor,
  CustomerFieldKey,
  FieldValue,
  HeatBand,
  OpeningBasis,
  OpportunityStatus,
  SalesStage,
  StageMark,
  ValueHistory,
  VehicleInterest,
  ViewerRole,
} from "@/types/customer360";

import { BarrierRows } from "./barrier-rows";
import {
  INSIGHT_FIELD_LABELS,
  SLOT_LABELS,
  formatSlotValue,
  knownSlots,
  nextActionLabel,
  openingBasisText,
} from "./customer360-labels";
import { type NeedCell, NeedGrid } from "./need-grid";
import { VehicleInterestCard } from "./vehicle-interest-card";

export type OpportunityCardData = {
  readonly title: string;
  readonly status?: OpportunityStatus;
  readonly heatBreakdown?: readonly { readonly code: string; readonly points: number; readonly detail: string }[];
  /** Lịch sử đổi giá trị theo slot ("850tr (trước: 700tr)"). */
  readonly history?: Record<string, readonly ValueHistory[]>;
  readonly insights?: readonly (FieldValue & { readonly insight_id: string; readonly field: string })[];
  readonly openingHint?: string;
  readonly openingBasis?: OpeningBasis;
  readonly nextActions?: readonly { readonly code: string; readonly label: string }[];
  readonly buyerFor?: BuyerFor;
  readonly stage?: SalesStage;
  readonly stageHistory?: readonly StageMark[];
  readonly heatBand?: HeatBand;
  readonly heatScore?: number;
  /** Slot đã có (slot → giá trị thô); nhãn và định dạng do card lo. */
  readonly slots: Record<string, unknown>;
  readonly missing?: readonly string[];
  readonly evaded?: readonly string[];
  readonly evadedDetail?: readonly { readonly slot: string; readonly ask_count: number }[];
  readonly barriers: readonly Pick<Barrier, "code" | "evidence_quote" | "session_id" | "turn_index" | "at">[];
  readonly vehicles?: readonly VehicleInterest[];
};

export type OpportunityOverviewProps = {
  readonly opportunity: OpportunityCardData;
  readonly role: ViewerRole;
  readonly readOnly: boolean;
  /** Thông tin tầng Khách (chỉ có khi đọc từ `/overview`) — ô Thanh toán/Xe đang đi, mục "Khách tự kể". */
  readonly customerFields?: Partial<Record<CustomerFieldKey, FieldValue>>;
  readonly latestSummary?: string | null;
  /** Phiên để mở "toàn bộ hội thoại". */
  readonly conversationHref?: string | null;
  /** TVV báo một insight sai — Admin (readOnly) không có nút này. */
  readonly onInsightFeedback?: (insightId: string) => void;
  /** Khối "Ưu đãi phù hợp" (Phase 5) — trang hồ sơ truyền vào khi cờ bật. */
  readonly offerSlot?: ReactNode;
};

/** Ô lưới nhu cầu lấy từ tầng Khách khi slot không có — đúng thứ tự mockup. */
const CUSTOMER_GRID_FIELDS: readonly CustomerFieldKey[] = ["registration_province", "home_charging", "payment_method", "current_vehicle"];
/** Thông tin tầng Khách KHÔNG nằm trong lưới → mục "Khách tự kể". */
const CUSTOMER_STORY_FIELDS: readonly CustomerFieldKey[] = ["decision_maker", "trade_in"];
const GRID_HIDDEN_SLOTS = new Set(["habit_need_tags"]);

function fieldLabel(key: string): string {
  return SLOT_LABELS[key] ?? INSIGHT_FIELD_LABELS[key] ?? key;
}

/** Ô lưới nhu cầu: slot đã có → thiếu/khách né → thông tin tầng Khách. */
export function needCells(
  opportunity: OpportunityCardData,
  customerFields?: Partial<Record<CustomerFieldKey, FieldValue>>,
): NeedCell[] {
  const known = knownSlots(opportunity.slots).filter((item) => !GRID_HIDDEN_SLOTS.has(item.slot));
  // Con số khách NÓI RA thắng trần đã nới biên — cùng luật `needSummary`.
  const hasStated = known.some((item) => item.slot === "budget_stated_vnd");
  const cells: NeedCell[] = known
    .filter((item) => !(hasStated && (item.slot === "budget_max_vnd" || item.slot === "budget_min_vnd")))
    .map((item) => {
      const previous = opportunity.history?.[item.slot]?.at(-1);
      return {
        key: item.slot,
        label: item.label,
        value: item.value,
        previous: previous ? (formatSlotValue(item.slot, previous.value) ?? previous.value) : null,
      };
    });
  const asked = new Map((opportunity.evadedDetail ?? []).map((item) => [item.slot, item.ask_count]));
  const evaded = new Set([...(opportunity.evaded ?? []), ...asked.keys()]);
  for (const slot of opportunity.missing ?? []) {
    if (cells.some((cell) => cell.key === slot)) continue;
    cells.push({ key: slot, label: fieldLabel(slot), value: null, evaded: evaded.has(slot), evadedAskCount: asked.get(slot) });
  }
  if (customerFields) {
    for (const key of CUSTOMER_GRID_FIELDS) {
      const field = customerFields[key];
      const value = field ? (formatSlotValue(key, field.value) ?? field.value) : null;
      const index = cells.findIndex((cell) => cell.key === key);
      if (index >= 0) {
        if (cells[index].value === null && value) cells[index] = { ...cells[index], value };
        continue;
      }
      cells.push({ key, label: fieldLabel(key), value });
    }
  }
  return cells;
}

function habitTags(slots: Record<string, unknown>): string[] {
  const raw = slots.habit_need_tags;
  if (Array.isArray(raw)) return raw.map(String).filter(Boolean);
  if (typeof raw === "string") return raw.split(",").map((item) => item.trim()).filter(Boolean);
  return [];
}

type StoryRow = { readonly key: string; readonly label: string; readonly value: string; readonly quote?: string; readonly insightId?: string };

function storyRows(opportunity: OpportunityCardData, customerFields?: Partial<Record<CustomerFieldKey, FieldValue>>): StoryRow[] {
  const rows: StoryRow[] = (opportunity.insights ?? []).map((insight) => ({
    key: insight.insight_id,
    label: INSIGHT_FIELD_LABELS[insight.field] ?? insight.field,
    value: insight.value,
    quote: insight.evidence_quote,
    insightId: insight.insight_id,
  }));
  for (const key of CUSTOMER_STORY_FIELDS) {
    const field = customerFields?.[key];
    if (field) rows.push({ key, label: INSIGHT_FIELD_LABELS[key] ?? key, value: field.value, quote: field.evidence_quote });
  }
  return rows;
}

function NextActionChecklist({ actions, readOnly }: Readonly<{ actions: readonly { code: string; label: string }[]; readOnly: boolean }>) {
  // Chỉ đánh dấu phía trình duyệt — CHƯA lưu (plan §13, việc cho lượt sau).
  const [done, setDone] = useState<ReadonlySet<string>>(new Set());
  if (readOnly) {
    return (
      <ul className="c360-todo" data-readonly="true">
        {actions.map((action) => (
          <li key={action.code}>{nextActionLabel(action)}</li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="c360-todo">
      {actions.map((action) => {
        const id = `c360-todo-${action.code}`;
        return (
          <li key={action.code}>
            <input
              checked={done.has(action.code)}
              id={id}
              onChange={(event) => {
                const next = new Set(done);
                if (event.target.checked) next.add(action.code);
                else next.delete(action.code);
                setDone(next);
              }}
              type="checkbox"
            />
            <label htmlFor={id}>{nextActionLabel(action)}</label>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * Tab "Tổng quan" của MỘT nhu cầu mua (mockup 02): cột trái gợi ý mở lời, rào cản, nhu cầu,
 * khách tự kể; cột phải việc cần làm, xe quan tâm, ưu đãi, tóm tắt. Khối nào không có dữ liệu
 * thì ẨN — nguồn dự phòng (cờ tắt) chỉ còn lưới nhu cầu.
 */
export function OpportunityOverview({
  opportunity,
  role,
  readOnly,
  customerFields,
  latestSummary,
  conversationHref,
  onInsightFeedback,
  offerSlot,
}: OpportunityOverviewProps) {
  const cells = needCells(opportunity, customerFields);
  const filled = cells.filter((cell) => cell.value !== null).length;
  const tags = habitTags(opportunity.slots);
  const stories = storyRows(opportunity, customerFields);
  const basis = openingBasisText(opportunity.openingBasis);
  const vehicles = opportunity.vehicles ?? [];
  const actions = opportunity.nextActions ?? [];

  return (
    <div className="c360-overview-grid">
      <div className="c360-column">
        {opportunity.openingHint ? (
          <section aria-label="Gợi ý mở lời" className="c360-hint-card">
            <p className="c360-eyebrow">Gợi ý mở lời</p>
            <p className="c360-hint-text">{opportunity.openingHint}</p>
            {basis ? <p className="c360-hint-basis">{basis}</p> : null}
          </section>
        ) : null}

        {opportunity.barriers.length ? (
          <section aria-labelledby="c360-barriers-title" className="c360-card c360-section">
            <div className="c360-section-head">
              <h2 id="c360-barriers-title">Rào cản khách đã nói ra</h2>
              <span className="c360-muted">Bấm để mở đúng đoạn hội thoại</span>
            </div>
            <BarrierRows items={opportunity.barriers} role={role} />
          </section>
        ) : null}

        {cells.length || tags.length ? (
          <section aria-labelledby="c360-needs-title" className="c360-card c360-section">
            <div className="c360-section-head">
              <h2 id="c360-needs-title">Nhu cầu</h2>
              {cells.length ? (
                <span className="c360-muted">
                  {filled}/{cells.length} thông tin đã có
                </span>
              ) : null}
            </div>
            <NeedGrid cells={cells} tags={tags} />
          </section>
        ) : null}

        {stories.length ? (
          <section aria-labelledby="c360-story-title" className="c360-card c360-section">
            <h2 id="c360-story-title">Khách tự kể trong hội thoại</h2>
            <dl className="c360-story">
              {stories.map((row) => (
                <div key={row.key}>
                  <dt>{row.label}</dt>
                  <dd>
                    <strong>{row.value}</strong>
                    {row.quote ? <span className="c360-muted"> · “{row.quote}”</span> : null}
                    {!readOnly && onInsightFeedback && row.insightId ? (
                      <button className="text-button" onClick={() => onInsightFeedback(row.insightId as string)} type="button">
                        <Flag size={13} /> Báo sai
                      </button>
                    ) : null}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}
      </div>

      <div className="c360-column">
        {actions.length ? (
          <section aria-labelledby="c360-todo-title" className="c360-card c360-section">
            <h2 id="c360-todo-title">Việc cần làm</h2>
            <NextActionChecklist actions={actions} readOnly={readOnly} />
          </section>
        ) : null}

        {vehicles.length ? (
          <section aria-labelledby="c360-vehicles-title" className="c360-card c360-section">
            <h2 id="c360-vehicles-title">Xe quan tâm</h2>
            <ul className="c360-vehicle-list">
              {vehicles.map((vehicle, index) => (
                <VehicleInterestCard key={vehicle.vehicle_id} primary={index === 0} vehicle={vehicle} />
              ))}
            </ul>
          </section>
        ) : null}

        {offerSlot ? (
          <section aria-labelledby="c360-offers-title" className="c360-card c360-section">
            <h2 id="c360-offers-title">Ưu đãi phù hợp</h2>
            {offerSlot}
          </section>
        ) : null}

        {latestSummary ? (
          <section aria-labelledby="c360-summary-title" className="c360-card c360-section">
            <h2 id="c360-summary-title">Tóm tắt của AI</h2>
            <p className="c360-summary-text">{latestSummary}</p>
            {conversationHref ? <Link href={conversationHref}>Mở toàn bộ hội thoại</Link> : null}
          </section>
        ) : null}
      </div>
    </div>
  );
}
