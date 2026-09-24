/**
 * Quản trị ưu đãi (Admin) + ưu đãi theo cơ hội (TVV) — plan Customer 360, Phase 5.
 *
 * Luật `eligibility_rules` là DSL JSON, đánh giá TẤT ĐỊNH ở backend; màn Admin chỉ dựng và
 * gửi lên kiểm (`/validate-rules`), không tự suy kết quả.
 */
import { csrfHeader, withSessionRetry } from "@/lib/api/session";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export class PromotionApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    public readonly errors: readonly string[] = [],
  ) {
    super(code);
    this.name = "PromotionApiError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const attempt = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: { "Content-Type": "application/json", ...init.headers, ...csrfHeader() },
    });
  const response = await withSessionRetry(attempt);
  const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
  if (!response.ok) {
    const detail = body.detail;
    if (detail && typeof detail === "object" && "code" in detail) {
      const typed = detail as { code: string; errors?: string[] };
      throw new PromotionApiError(typed.code, response.status, typed.errors ?? []);
    }
    throw new PromotionApiError(typeof detail === "string" ? detail : "request_failed", response.status);
  }
  return body as T;
}

export type EligibilityRules = Record<string, unknown>;
export type PromotionStatus = "DRAFT" | "UNVERIFIED" | "ACTIVE" | "EXPIRED" | "CANCELLED";
export type PromotionTypeCode = "FIXED_DISCOUNT" | "PERCENT_DISCOUNT" | "GIFT" | "FINANCING" | "REGISTRATION_SUPPORT" | "OTHER";

export type AdminPromotion = {
  readonly promotion_id: string;
  readonly promotion_code: string;
  readonly title: string;
  readonly description: string | null;
  readonly promotion_type: PromotionTypeCode;
  readonly discount_amount_vnd: number | null;
  readonly discount_percent: number | null;
  readonly eligibility_rules: EligibilityRules;
  readonly status: PromotionStatus;
  readonly valid_from: string;
  readonly valid_to: string | null;
  readonly stackable: boolean;
  readonly priority: number;
  readonly max_uses: number | null;
  readonly used_count: number;
  readonly requires_advisor_approval: boolean;
  readonly advisor_max_discount_vnd: number | null;
  readonly source_meta: Record<string, unknown>;
  readonly created_by: string | null;
  readonly rules_valid: boolean;
};

export type PromotionInput = Partial<
  Pick<
    AdminPromotion,
    | "promotion_code"
    | "title"
    | "description"
    | "promotion_type"
    | "discount_amount_vnd"
    | "discount_percent"
    | "eligibility_rules"
    | "valid_from"
    | "valid_to"
    | "stackable"
    | "priority"
    | "max_uses"
    | "requires_advisor_approval"
    | "advisor_max_discount_vnd"
  >
> & { readonly status?: Exclude<PromotionStatus, "ACTIVE"> };

export type RuleSchema = {
  readonly fields: Record<string, "enum" | "str" | "number" | "bool">;
  readonly operators: readonly string[];
  readonly question_hints: Record<string, string>;
};

export type PromotionStats = {
  readonly promotion_code: string;
  readonly suggested?: number;
  readonly approved?: number;
  readonly sent?: number;
  readonly engaged?: number;
  readonly converted?: number;
  readonly expired?: number;
  readonly dismissed?: number;
  readonly conversion_rate: number;
};

export const listPromotions = (status?: PromotionStatus) =>
  request<readonly AdminPromotion[]>(`/admin/promotions${status ? `?status_filter=${status}` : ""}`);
export const fetchRuleSchema = () => request<RuleSchema>("/admin/promotions/rule-schema");
export const validatePromotionRules = (rules: EligibilityRules) =>
  request<{ ok: boolean; errors: string[] }>("/admin/promotions/validate-rules", {
    method: "POST",
    body: JSON.stringify({ rules }),
  });
export const createPromotion = (input: PromotionInput) =>
  request<AdminPromotion>("/admin/promotions", { method: "POST", body: JSON.stringify(input) });
export const updatePromotion = (promotionId: string, input: PromotionInput) =>
  request<AdminPromotion>(`/admin/promotions/${promotionId}`, { method: "PATCH", body: JSON.stringify(input) });
export const activatePromotion = (promotionId: string) =>
  request<AdminPromotion>(`/admin/promotions/${promotionId}/activate`, { method: "POST" });
export const cancelPromotion = (promotionId: string) =>
  request<AdminPromotion>(`/admin/promotions/${promotionId}`, { method: "DELETE" });
export const fetchPromotionStats = () => request<readonly PromotionStats[]>("/admin/promotion-stats");

// ---------------------------------------------------------------- ưu đãi theo cơ hội (TVV)

export type EligibleOffer = {
  readonly promotion_code: string;
  readonly title: string;
  readonly promotion_type: PromotionTypeCode;
  readonly discount_amount_vnd: number | null;
  readonly discount_percent: number | null;
  readonly stackable: boolean;
  readonly advisor_max_discount_vnd: number | null;
  readonly reasons?: readonly string[];
  readonly missing_fields?: readonly string[];
  readonly question_hints?: readonly string[];
};

export type OpportunityOffer = {
  readonly offer_id: string;
  readonly opportunity_id: string;
  readonly promotion_code: string;
  readonly status: "SUGGESTED" | "APPROVED" | "SENT" | "ENGAGED" | "CONVERTED" | "EXPIRED" | "DISMISSED";
  readonly discount_vnd: number | null;
  readonly needs_manager_approval: boolean;
};

export const fetchEligibleOffers = (opportunityId: string) =>
  request<{ eligible: readonly EligibleOffer[]; need_info: readonly EligibleOffer[] }>(
    `/advisor/opportunities/${opportunityId}/eligible-offers`,
  );
export const proposeOffer = (opportunityId: string, promotionCode: string, proposedValue: Record<string, unknown> = {}) =>
  request<OpportunityOffer>(`/advisor/opportunities/${opportunityId}/offers`, {
    method: "POST",
    body: JSON.stringify({ promotion_code: promotionCode, proposed_value: proposedValue }),
  });
export const offerAction = (offerId: string, action: "send" | "engage" | "convert" | "dismiss") =>
  request<OpportunityOffer>(`/advisor/opportunity-offers/${offerId}/${action}`, { method: "POST" });
export const approveOffer = (offerId: string) =>
  request<OpportunityOffer>(`/admin/opportunity-offers/${offerId}/approve`, { method: "POST" });
export const fetchCustomerOffers = (customerId: string) =>
  request<readonly (OpportunityOffer & { readonly sent_at: string | null; readonly updated_at: string })[]>(
    `/advisor/customers/${encodeURIComponent(customerId)}/offers`,
  );

/** Thông báo nội bộ cho TVV khi Admin kích hoạt ưu đãi (plan §2.6 — nút tạo thông báo). */
export const publishPromotionNotice = (title: string, content: string) =>
  request<{ notice_id: string }>("/agent/notices", {
    method: "POST",
    body: JSON.stringify({ title, content, priority: "NORMAL" }),
  });
