import type { ReactNode } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import type { CustomerHeader, ViewerRole } from "@/types/customer360";

import { HEAT_BAND_BADGES } from "./customer360-labels";

export type CustomerSummaryData = Pick<
  CustomerHeader,
  "customer_id" | "display_name" | "phone_masked" | "phone" | "assigned_advisor_id" | "sessions_count" | "last_seen_at"
> &
  Partial<Pick<CustomerHeader, "heat_band" | "heat_score">>;

export type CustomerSummaryProps = {
  readonly customer: CustomerSummaryData;
  readonly role: ViewerRole;
  readonly readOnly: boolean;
  /** Nút thao tác (Vào chat / Gọi / Tiếp quản) — ẩn hoàn toàn khi `readOnly`. */
  readonly actions?: ReactNode;
};

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return iso;
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(value);
}

/**
 * Đầu hồ sơ: tầng Khách (plan §2.1). SĐT đầy đủ chỉ hiện khi backend trả `phone`
 * (TVV phụ trách) và người xem không ở chế độ chỉ xem; mọi trường hợp khác dùng bản đã che.
 */
export function CustomerSummary({ customer, role, readOnly, actions }: CustomerSummaryProps) {
  const name = customer.display_name || customer.customer_id;
  const phone = !readOnly && role === "advisor" && customer.phone ? customer.phone : customer.phone_masked;
  const heat = customer.heat_band ? HEAT_BAND_BADGES[customer.heat_band] : null;
  return (
    <div className="customer360-summary">
      <span aria-hidden="true" className="ops-avatar large">
        {initials(name)}
      </span>
      <div className="customer360-summary-copy">
        <strong>{name}</strong>
        <span className="mono-text">ID: {customer.customer_id}</span>
        <dl>
          <div>
            <dt>SĐT</dt>
            <dd>{phone || "Chưa có"}</dd>
          </div>
          <div>
            <dt>Phụ trách</dt>
            <dd>{customer.assigned_advisor_id || "Chưa phân công"}</dd>
          </div>
          <div>
            <dt>Số phiên</dt>
            <dd>{customer.sessions_count}</dd>
          </div>
          <div>
            <dt>Hoạt động gần nhất</dt>
            <dd>{formatWhen(customer.last_seen_at)}</dd>
          </div>
        </dl>
      </div>
      {heat ? (
        <StatusBadge tone={heat.tone}>
          {heat.label}
          {customer.heat_score !== null && customer.heat_score !== undefined ? ` · ${customer.heat_score}` : ""}
        </StatusBadge>
      ) : null}
      {!readOnly && actions ? <div className="customer360-summary-actions">{actions}</div> : null}
    </div>
  );
}
