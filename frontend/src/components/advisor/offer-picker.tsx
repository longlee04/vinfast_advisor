"use client";

import { useState } from "react";

import type { MatchedPromotion, OfferAdjustment, OfferAdjustmentPolicy, PromotionType } from "@/types/agent";
import { PROMOTION_TYPE_LABELS } from "./offer-state-labels";

type FieldKey = "amount_vnd" | "percent" | "months" | "gift_code";
type Bound = { readonly min: number | null; readonly max: number | null };

const FIELDS: Record<PromotionType, readonly FieldKey[]> = {
  FIXED_DISCOUNT: ["amount_vnd"],
  PERCENT_DISCOUNT: ["percent"],
  GIFT: ["gift_code", "amount_vnd"],
  FINANCING: ["months", "amount_vnd"],
  REGISTRATION_SUPPORT: ["amount_vnd"],
  OTHER: ["amount_vnd"],
};
const LABELS: Record<FieldKey, string> = {
  amount_vnd: "Giá trị (VND)", percent: "Phần trăm (%)", months: "Số tháng trả góp", gift_code: "Mã quà tặng",
};

function numeric(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function offerBound(field: FieldKey, policy: OfferAdjustmentPolicy, type: PromotionType): Bound {
  if (field === "percent") return { min: numeric(policy.adjust_min_percent), max: numeric(policy.adjust_max_percent) };
  if (field === "months") return { min: numeric(policy.financing_months_min), max: numeric(policy.financing_months_max) };
  if (field === "gift_code") return { min: null, max: null };
  switch (type) {
    case "FIXED_DISCOUNT": return { min: numeric(policy.adjust_min_vnd), max: numeric(policy.adjust_max_vnd) };
    case "GIFT": return { min: null, max: numeric(policy.gift_value_max_vnd) };
    case "FINANCING": return { min: null, max: numeric(policy.financing_support_max_vnd) };
    case "REGISTRATION_SUPPORT": return { min: 0, max: numeric(policy.registration_support_max_vnd) };
    case "OTHER": return { min: 0, max: numeric(policy.other_max_vnd) };
    case "PERCENT_DISCOUNT": return { min: null, max: null };
  }
}

function violates(raw: string, bound: Bound): boolean {
  if (raw.trim() === "") return false;
  const value = Number(raw);
  return !Number.isFinite(value) || (bound.min !== null && value < bound.min) || (bound.max !== null && value > bound.max);
}

/**
 * `readOnly` (Admin xem hồ sơ, plan Customer 360 §2.7): chỉ liệt kê chương trình phù hợp,
 * không có ô nhập hay nút gửi — Admin không cấp ưu đãi thay TVV.
 */
export function OfferPicker({ promotions, policies, busy, onSubmit, readOnly = false }: Readonly<{
  promotions: readonly MatchedPromotion[];
  policies: readonly OfferAdjustmentPolicy[];
  busy: boolean;
  onSubmit?: (adjustment: OfferAdjustment) => void;
  readOnly?: boolean;
}>) {
  const [code, setCode] = useState("");
  const [values, setValues] = useState<Record<FieldKey, string>>({ amount_vnd: "", percent: "", months: "", gift_code: "" });
  const selected = promotions.find((promotion) => promotion.promotion_code === code) ?? null;
  const policy = selected === null ? null : policies.find((candidate) => candidate.promotion_type === selected.promotion_type) ?? null;
  const fields = selected === null ? [] : FIELDS[selected.promotion_type];
  const invalid = selected !== null && policy !== null && fields.some((field) => {
    if (field === "gift_code") return policy.allowed_gift_codes !== null && policy.allowed_gift_codes !== undefined && values.gift_code !== "" && !policy.allowed_gift_codes.includes(values.gift_code);
    return violates(values[field], offerBound(field, policy, selected.promotion_type));
  });
  const blocked = selected === null || policy === null || invalid || busy;

  function submit(): void {
    if (selected === null || blocked || onSubmit === undefined) return;
    onSubmit({
      promotion_code: selected.promotion_code,
      promotion_type: selected.promotion_type,
      adjustment_type: selected.promotion_type === "PERCENT_DISCOUNT" ? "PERCENT" : selected.promotion_type === "FINANCING" ? "MONTHS" : selected.promotion_type === "GIFT" ? "GIFT_CODE" : "VND",
      amount_vnd: values.amount_vnd === "" ? null : Number(values.amount_vnd),
      percent: values.percent === "" ? null : Number(values.percent),
      months: values.months === "" ? null : Number(values.months),
      gift_code: values.gift_code === "" ? null : values.gift_code,
      new_value: values.percent || values.months || values.gift_code || values.amount_vnd,
    });
  }

  if (readOnly) {
    return <section className="signal-offer-picker" aria-label="Ưu đãi phù hợp"><h2>Ưu đãi phù hợp</h2>{promotions.length ? <ul>{promotions.map((promotion) => <li key={promotion.promotion_code}>{promotion.promotion_code} · {PROMOTION_TYPE_LABELS[promotion.promotion_type]}</li>)}</ul> : <p className="customer360-empty">Chưa có chương trình phù hợp.</p>}</section>;
  }

  return <section className="signal-offer-picker" aria-label="Cấp ưu đãi"><h2>Cấp ưu đãi</h2><label className="field-label">Chương trình ưu đãi<select value={code} onChange={(event) => setCode(event.target.value)}><option value="">Chọn chương trình</option>{promotions.map((promotion) => <option key={promotion.promotion_code} value={promotion.promotion_code}>{promotion.promotion_code} · {PROMOTION_TYPE_LABELS[promotion.promotion_type]}</option>)}</select></label>{policy === null && selected !== null ? <p className="inline-warning">Chưa có biên độ ADMIN cấu hình cho loại ưu đãi này.</p> : null}{fields.map((field) => { const bound = policy === null || selected === null ? null : offerBound(field, policy, selected.promotion_type); return <label className="field-label" key={field}>{LABELS[field]}<input disabled={policy === null} max={bound?.max ?? undefined} min={bound?.min ?? undefined} onChange={(event) => setValues((current) => ({ ...current, [field]: event.target.value }))} type={field === "gift_code" ? "text" : "number"} value={values[field]} /></label>; })}{invalid ? <p className="inline-warning">Giá trị vượt biên độ cho phép. Kiểm tra lại trước khi gửi.</p> : null}<button className="primary-button" disabled={blocked} onClick={submit} type="button">Gửi ưu đãi</button></section>;
}
