"use client";

import { Braces, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import type { EligibilityRules } from "@/lib/api/promotions";

/**
 * Bộ dựng `eligibility_rules` (plan Customer 360 §2.6). Dạng bảng cho trường hợp thường gặp —
 * một nhóm "tất cả / một trong" các điều kiện phẳng; luật lồng nhau thì chuyển sang JSON.
 * Kiểm hợp lệ luôn ở backend (`/validate-rules`), nơi bộ đánh giá sống.
 */

type Operator = "eq" | "in" | "gte" | "lte" | "exists";
type Row = { field: string; operator: Operator; value: string };
type Group = { combinator: "all" | "any"; rows: Row[] };

export const RULE_FIELD_LABELS: Record<string, string> = {
  vehicle_type: "Loại xe",
  vehicle_model: "Mẫu xe",
  budget_max_vnd: "Ngân sách tối đa (VND)",
  registration_province: "Tỉnh đăng ký",
  purpose_bucket: "Mục đích",
  home_charging: "Sạc tại nhà",
  passenger_count: "Số người",
  payment_method: "Hình thức thanh toán",
  trade_in: "Đổi xe cũ",
  current_vehicle_brand: "Hãng xe đang đi",
  customer_group: "Nhóm khách",
  purchase_timeframe: "Thời điểm định mua",
};
const OPERATOR_LABELS: Record<Operator, string> = {
  eq: "bằng",
  in: "thuộc (cách nhau dấu phẩy)",
  gte: "≥",
  lte: "≤",
  exists: "đã có / chưa có",
};

function toValue(row: Row, fieldType: string | undefined): unknown {
  if (row.operator === "exists") return row.value !== "false";
  if (row.operator === "in") return row.value.split(",").map((item) => item.trim()).filter(Boolean);
  if (row.operator === "gte" || row.operator === "lte" || fieldType === "number") return Number(row.value);
  if (fieldType === "bool") return row.value === "true";
  return row.value.trim();
}

/** Luật phẳng all/any → bảng; luật khác (lồng, rỗng) → `null` = mở chế độ JSON. */
export function rulesToGroup(rules: EligibilityRules): Group | null {
  if (!rules || Object.keys(rules).length === 0) return { combinator: "all", rows: [] };
  const combinator = "all" in rules ? "all" : "any" in rules ? "any" : null;
  const children = combinator ? rules[combinator] : [rules];
  if (!Array.isArray(children)) return null;
  const rows: Row[] = [];
  for (const child of children) {
    if (!child || typeof child !== "object" || !("field" in child)) return null;
    const { field, ...rest } = child as Record<string, unknown>;
    const [operator, value] = Object.entries(rest)[0] ?? [];
    if (!operator) return null;
    rows.push({
      field: String(field),
      operator: operator as Operator,
      value: Array.isArray(value) ? value.join(", ") : String(value),
    });
  }
  return { combinator: combinator ?? "all", rows };
}

export function groupToRules(group: Group, fieldTypes: Record<string, string>): EligibilityRules {
  if (group.rows.length === 0) return {};
  return {
    [group.combinator]: group.rows.map((row) => ({ field: row.field, [row.operator]: toValue(row, fieldTypes[row.field]) })),
  };
}

export function EligibilityRuleBuilder({
  value,
  onChange,
  fieldTypes,
}: Readonly<{ value: EligibilityRules; onChange: (rules: EligibilityRules) => void; fieldTypes: Record<string, string> }>) {
  const parsed = rulesToGroup(value);
  const [jsonMode, setJsonMode] = useState(parsed === null);
  const [jsonText, setJsonText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const group = parsed ?? { combinator: "all" as const, rows: [] };
  const fields = Object.keys(fieldTypes).length ? Object.keys(fieldTypes) : Object.keys(RULE_FIELD_LABELS);

  function update(next: Group) {
    const rules = groupToRules(next, fieldTypes);
    setJsonText(JSON.stringify(rules, null, 2));
    onChange(rules);
  }

  if (jsonMode) {
    return (
      <div className="rule-builder">
        <textarea
          aria-label="Luật (JSON)"
          onChange={(event) => {
            setJsonText(event.target.value);
            try {
              const next = JSON.parse(event.target.value) as EligibilityRules;
              setJsonError(null);
              onChange(next);
            } catch {
              setJsonError("JSON chưa hợp lệ");
            }
          }}
          rows={8}
          value={jsonText}
        />
        {jsonError ? <small className="rule-builder-error">{jsonError}</small> : null}
        {rulesToGroup(value) !== null ? (
          <button className="text-button" onClick={() => setJsonMode(false)} type="button">
            Về dạng bảng
          </button>
        ) : (
          <small>Luật lồng nhau hoặc chưa đúng dạng — chỉ sửa được bằng JSON.</small>
        )}
      </div>
    );
  }

  return (
    <div className="rule-builder">
      <label className="rule-builder-combinator">
        Khách phải thỏa
        <select
          onChange={(event) => update({ ...group, combinator: event.target.value as "all" | "any" })}
          value={group.combinator}
        >
          <option value="all">tất cả điều kiện</option>
          <option value="any">ít nhất một điều kiện</option>
        </select>
      </label>
      {group.rows.length === 0 ? <p className="customer360-empty">Không có điều kiện — mọi khách đều hợp.</p> : null}
      {group.rows.map((row, index) => (
        <div className="rule-builder-row" key={index}>
          <select
            aria-label={`Trường điều kiện ${index + 1}`}
            onChange={(event) => update({ ...group, rows: group.rows.map((item, i) => (i === index ? { ...item, field: event.target.value } : item)) })}
            value={row.field}
          >
            {fields.map((name) => (
              <option key={name} value={name}>
                {RULE_FIELD_LABELS[name] ?? name}
              </option>
            ))}
          </select>
          <select
            aria-label={`Toán tử ${index + 1}`}
            onChange={(event) =>
              update({ ...group, rows: group.rows.map((item, i) => (i === index ? { ...item, operator: event.target.value as Operator } : item)) })
            }
            value={row.operator}
          >
            {(Object.keys(OPERATOR_LABELS) as Operator[]).map((operator) => (
              <option key={operator} value={operator}>
                {OPERATOR_LABELS[operator]}
              </option>
            ))}
          </select>
          <input
            aria-label={`Giá trị ${index + 1}`}
            onChange={(event) => update({ ...group, rows: group.rows.map((item, i) => (i === index ? { ...item, value: event.target.value } : item)) })}
            placeholder={row.operator === "in" ? "HN, HCM" : row.operator === "exists" ? "true / false" : "Giá trị"}
            value={row.value}
          />
          <button
            aria-label={`Xoá điều kiện ${index + 1}`}
            className="icon-button"
            onClick={() => update({ ...group, rows: group.rows.filter((_, i) => i !== index) })}
            type="button"
          >
            <Trash2 size={15} />
          </button>
        </div>
      ))}
      <div className="rule-builder-actions">
        <button
          className="text-button"
          onClick={() => update({ ...group, rows: [...group.rows, { field: fields[0], operator: "eq", value: "" }] })}
          type="button"
        >
          <Plus size={14} /> Thêm điều kiện
        </button>
        <button className="text-button" onClick={() => setJsonMode(true)} type="button">
          <Braces size={14} /> Sửa JSON
        </button>
      </div>
    </div>
  );
}
