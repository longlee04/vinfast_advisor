/**
 * Kiểu dữ liệu hồ sơ khách 360 (plan `docs/PLAN_CUSTOMER_360.md`).
 *
 * Nguồn định nghĩa DUY NHẤT của các enum là backend (`src/agents/domain/sales_stage.py`,
 * `heat_score.py`, `opportunity_attach.py`); file này chỉ phản chiếu để TypeScript
 * bắt lỗi khi hai phía lệch. `CustomerOverview` khớp `GET /advisor/customers/{id}/overview`
 * (Phase 4) — trước khi endpoint đó có, các component nhận phần dữ liệu đã có sẵn.
 */

export type SalesStage = "DISCOVER" | "COMPARE" | "QUOTE" | "TEST_DRIVE" | "CLOSE";
export type HeatBand = "HOT" | "WARM" | "COLD";
export type OpportunityStatus = "OPEN" | "DORMANT" | "WON" | "LOST" | "REPLACED";
export type BuyerFor = "SELF" | "FAMILY" | "COMPANY" | "OTHER";
export type SessionKind = "SALES" | "SUPPORT" | "UNASSIGNED";
export type AttachDecider = "RULE" | "LLM" | "ADVISOR";
export type InsightSource = "SLOT" | "LLM" | "ADVISOR";
export type BarrierSource = "BOTTLENECK" | "INSIGHT";

/** Ai đang xem: TVV thao tác được, Admin chỉ xem (plan §2.7). */
export type ViewerRole = "advisor" | "admin";

export type ValueHistory = { readonly value: string; readonly at: string };

export type FieldValue = {
  readonly value: string;
  readonly value_code?: string;
  readonly source: InsightSource;
  readonly evidence_quote?: string;
  readonly turn_index?: number;
  readonly at: string;
  readonly history: readonly ValueHistory[];
};

export type CustomerFieldKey =
  | "registration_province"
  | "home_charging"
  | "decision_maker"
  | "payment_method"
  | "current_vehicle"
  | "trade_in";

export type CustomerHeader = {
  readonly customer_id: string;
  readonly display_name: string | null;
  readonly phone_masked: string | null;
  /** Chỉ backend trả cho TVV phụ trách — không bao giờ có ở chế độ Admin. */
  readonly phone?: string;
  readonly assigned_advisor_id: string | null;
  readonly heat_band: HeatBand | null;
  readonly heat_score: number | null;
  readonly sessions_count: number;
  readonly last_seen_at: string | null;
  readonly fields: Partial<Record<CustomerFieldKey, FieldValue>>;
};

export type Barrier = {
  readonly code: string;
  readonly source: BarrierSource;
  /** Đã qua `redact_pii` ở backend. */
  readonly evidence_quote: string;
  readonly turn_index: number | null;
  readonly session_id: string;
  readonly status: string;
};

export type NeedSlot = { readonly slot: string; readonly value: string; readonly history: readonly ValueHistory[] };

export type Opportunity = {
  readonly opportunity_id: string;
  readonly vehicle_type: string | null;
  readonly buyer_for: BuyerFor;
  readonly status: OpportunityStatus;
  readonly stage: SalesStage;
  readonly heat_score: number;
  readonly heat_band: HeatBand;
  readonly heat_breakdown: readonly { readonly code: string; readonly points: number; readonly detail: string }[];
  readonly needs: { readonly known: readonly NeedSlot[]; readonly missing: readonly string[]; readonly evaded: readonly string[] };
  readonly barriers: readonly Barrier[];
  readonly insights: readonly (FieldValue & { readonly insight_id: string; readonly field: string })[];
  readonly opening_hint: string;
  readonly next_actions: readonly { readonly code: string; readonly label: string }[];
};

export type SessionRow = {
  readonly session_id: string;
  readonly started_at: string | null;
  readonly last_activity_at: string;
  readonly status: "ACTIVE" | "WAITING_ADVISOR" | "CLOSED";
  readonly ownership?: string;
  readonly kind: SessionKind;
  readonly opportunity_id: string | null;
  readonly needs_review: boolean;
  readonly decided_by: AttachDecider | null;
  readonly turn_count: number | null;
  readonly summary_excerpt: string | null;
};

export type TestDriveItem = {
  readonly booking_id: string;
  readonly vehicle_id: string;
  readonly showroom: string;
  readonly scheduled_at: string;
  readonly status: string;
};

export type CustomerOverview = {
  readonly customer: CustomerHeader;
  readonly opportunities: readonly Opportunity[];
  readonly sessions: readonly SessionRow[];
  readonly test_drives: readonly TestDriveItem[];
};
