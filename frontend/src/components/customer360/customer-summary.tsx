"use client";

import type { ReactNode } from "react";

import type { CustomerHeader } from "@/types/customer360";

import { OWNERSHIP_LABELS, relativeAge } from "./customer360-labels";
import { HeatPill } from "./heat-pill";
import { useClock } from "./use-clock";

export type CustomerSummaryData = Pick<
  CustomerHeader,
  "customer_id" | "display_name" | "phone_masked" | "phone" | "address" | "assigned_advisor_id" | "sessions_count" | "last_seen_at"
> &
  Partial<Pick<CustomerHeader, "heat_band" | "heat_score">>;

export type CustomerSummaryProps = {
  readonly customer: CustomerSummaryData;
  readonly turnsTotal?: number | null;
  /** Ai đang giữ phiên đang mở — hiện "AI đang trả lời"… */
  readonly ownership?: string | null;
  /** Nút thao tác bên phải (Xem hội thoại / Gọi khách / Tiếp quản, hoặc Phân công lại cho Admin). */
  readonly actions?: ReactNode;
  /** Thanh giai đoạn + chọn nhu cầu — nằm trong cùng thẻ đầu trang. */
  readonly children?: ReactNode;
};

function initials(name: string): string {
  const words = name.trim().split(/\s+/);
  if (words.length >= 2) return (words[0][0] + words[words.length - 1][0]).toUpperCase();
  return name.slice(0, 2).toUpperCase();
}

/** Mã khách dài (UUID/số) thì rút gọn khi chưa có tên. */
function shortId(id: string): string {
  return id.length > 14 ? `${id.slice(0, 8)}…` : id;
}

/**
 * Thẻ đầu hồ sơ (mockup 02): avatar, tên, độ nóng, dòng meta, nút thao tác. SĐT luôn hiện bản
 * đã che — số đầy đủ (chỉ backend trả cho TVV phụ trách) chỉ dùng cho nút "Gọi khách".
 */
export function CustomerSummary({ customer, turnsTotal, ownership, actions, children }: CustomerSummaryProps) {
  const now = useClock();
  const name = customer.display_name || shortId(customer.customer_id);
  const age = relativeAge(customer.last_seen_at, now);
  const meta = [
    customer.phone_masked,
    `${customer.sessions_count} phiên chat${typeof turnsTotal === "number" ? ` · ${turnsTotal} lượt` : ""}`,
    age ? (age === "Vừa xong" ? "Vừa hoạt động" : `Hoạt động ${age === "Hôm qua" ? "hôm qua" : `${age} trước`}`) : null,
    ownership ? (OWNERSHIP_LABELS[ownership] ?? null) : null,
  ].filter(Boolean);
  return (
    <section aria-label="Thông tin khách" className="c360-card c360-profile-head">
      <div className="c360-profile-top">
        <div className="c360-profile-identity">
          <span aria-hidden="true" className="c360-avatar">
            {initials(name)}
          </span>
          <div>
            <div className="c360-profile-name">
              <h1 title={customer.customer_id}>{name}</h1>
              {customer.heat_band ? <HeatPill band={customer.heat_band} score={customer.heat_score} /> : null}
            </div>
            <p className="c360-profile-meta">
              {meta.map((item) => (
                <span key={item as string}>{item}</span>
              ))}
            </p>
            {customer.address ? <p className="c360-profile-address">{customer.address}</p> : null}
          </div>
        </div>
        {actions ? <div className="c360-profile-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}
