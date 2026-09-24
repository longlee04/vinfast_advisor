"use client";

import { ArrowLeft, CalendarDays, Gift, Hand, LayoutDashboard, LoaderCircle, MessageSquareText, Phone, UserCog } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { moveSessionOpportunity, sendInsightFeedback } from "@/lib/api/agent";
import { CustomerProfileUnavailableError, type CustomerProfileView, loadCustomerProfile } from "@/lib/api/customer360";
import type { TestDriveItem, ViewerRole } from "@/types/customer360";

import { INSIGHT_FIELD_LABELS, formatSlotValue } from "./customer360-labels";
import { CustomerSummary } from "./customer-summary";
import { EligibleOfferList } from "./eligible-offer-list";
import { IssuedOfferList } from "./issued-offer-list";
import { OpportunityCard } from "./opportunity-card";
import { SessionList } from "./session-list";

type TabKey = "overview" | "sessions" | "test-drives" | "offers";

const TABS: readonly { key: TabKey; label: string; icon: typeof LayoutDashboard }[] = [
  { key: "overview", label: "Tổng quan", icon: LayoutDashboard },
  { key: "sessions", label: "Phiên chat", icon: MessageSquareText },
  { key: "test-drives", label: "Lái thử", icon: CalendarDays },
  { key: "offers", label: "Ưu đãi đã cấp", icon: Gift },
];

const BOOKING_BADGES: Record<string, { tone: "success" | "warning" | "neutral"; label: string }> = {
  REQUESTED: { tone: "warning", label: "Chờ xác nhận" },
  CONFIRMED: { tone: "success", label: "Đã xác nhận" },
  CANCELLED: { tone: "neutral", label: "Đã hủy" },
};

function TestDriveList({ items }: Readonly<{ items: readonly TestDriveItem[] }>) {
  if (items.length === 0) return <p className="customer360-empty">Khách chưa đặt lịch lái thử nào.</p>;
  return (
    <ul className="customer360-session-list">
      {items.map((item) => {
        const badge = BOOKING_BADGES[item.status] ?? { tone: "neutral" as const, label: item.status };
        return (
          <li key={item.booking_id}>
            <div>
              <div className="customer360-session-head">
                <strong>{item.vehicle_id}</strong>
                <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
              </div>
              <p>{item.showroom}</p>
              <small>{new Intl.DateTimeFormat("vi-VN", { dateStyle: "full", timeStyle: "short" }).format(new Date(item.scheduled_at))}</small>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export type CustomerProfilePageProps = {
  readonly customerId: string;
  readonly role: ViewerRole;
  /** Admin xem hồ sơ ở chế độ chỉ xem (plan §2.6): thao tác duy nhất là phân công lại. */
  readonly readOnly: boolean;
};

/** Hồ sơ khách 360 — dùng chung cho `/advisor/customers/[id]` và `/admin/customers/[id]`. */
export function CustomerProfilePage({ customerId, role, readOnly }: CustomerProfilePageProps) {
  const [profile, setProfile] = useState<CustomerProfileView | null>(null);
  const [error, setError] = useState<"forbidden" | "failed" | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");

  const load = useCallback(async () => {
    setError(null);
    try {
      setProfile(await loadCustomerProfile(customerId, role));
    } catch (err: unknown) {
      setProfile(null);
      const status = (err as { status?: number }).status;
      setError(err instanceof CustomerProfileUnavailableError || status === 403 || status === 404 ? "forbidden" : "failed");
    }
  }, [customerId, role]);

  useEffect(() => {
    void load();
  }, [load]);

  const backHref = role === "admin" ? "/admin/assignments" : "/advisor/customers";
  // Chỉ TVV, và chỉ khi dữ liệu đến từ Customer 360 (màn dự phòng chưa có cơ hội để tách/gộp).
  const editable = !readOnly && profile?.source === "overview";

  async function moveSession(sessionId: string, target: string | null) {
    await moveSessionOpportunity(sessionId, target === null ? { action: "SPLIT" } : { action: "MOVE", opportunity_id: target });
    await load();
  }

  async function reportInsight(insightId: string) {
    await sendInsightFeedback(insightId, "WRONG");
    await load();
  }

  let body: ReactNode;
  if (error === "forbidden") {
    body = (
      <div className="ops-state" role="alert">
        <h2>Không xem được hồ sơ này</h2>
        <p>Khách hàng không thuộc phạm vi phụ trách của bạn, hoặc không tồn tại.</p>
      </div>
    );
  } else if (error === "failed") {
    body = (
      <div className="ops-state" role="alert">
        <h2>Không tải được hồ sơ khách</h2>
        <button className="secondary-button" onClick={() => void load()} type="button">
          Thử lại
        </button>
      </div>
    );
  } else if (profile === null) {
    body = (
      <div className="ops-state" aria-busy="true">
        <LoaderCircle className="spin" size={24} />
        <p>Đang tải hồ sơ khách...</p>
      </div>
    );
  } else {
    const phone = profile.header.phone;
    const actions = readOnly ? null : (
      <>
        {profile.focusSessionId ? (
          <Link className="primary-button" href={`/advisor/conversations/${profile.focusSessionId}`}>
            <MessageSquareText size={15} /> Vào chat
          </Link>
        ) : null}
        {phone ? (
          <a className="secondary-button" href={`tel:${phone}`}>
            <Phone size={15} /> Gọi
          </a>
        ) : null}
        {profile.waitingSessionId ? (
          <Link className="secondary-button" href={`/advisor/conversations/${profile.waitingSessionId}`}>
            <Hand size={15} /> Tiếp quản
          </Link>
        ) : null}
      </>
    );
    body = (
      <>
        <section className="ops-panel customer360-header">
          <CustomerSummary actions={actions} customer={profile.header} readOnly={readOnly} role={role} />
          {profile.fields && Object.keys(profile.fields).length ? (
            <dl aria-label="Thông tin khách đã nói" className="customer360-needs">
              {Object.entries(profile.fields).map(([field, value]) =>
                value ? (
                  <div key={field}>
                    <dt>{INSIGHT_FIELD_LABELS[field] ?? field}</dt>
                    <dd title={value.evidence_quote ?? undefined}>
                      {formatSlotValue(field, value.value) ?? value.value}
                      {value.history.length ? <small> (trước: {value.history.at(-1)?.value})</small> : null}
                    </dd>
                  </div>
                ) : null,
              )}
            </dl>
          ) : null}
          {readOnly ? (
            <div className="customer360-summary-actions">
              <Link className="secondary-button" href={`/admin/assignments?customer=${encodeURIComponent(customerId)}`}>
                <UserCog size={15} /> Phân công lại
              </Link>
            </div>
          ) : null}
        </section>

        <div aria-label="Mục hồ sơ" className="customer360-tabs" role="tablist">
          {TABS.filter((item) => item.key !== "offers" || profile.offers.lifecycle).map(({ key, label, icon: Icon }) => (
            <button
              aria-controls={`customer360-panel-${key}`}
              aria-selected={tab === key}
              id={`customer360-tab-${key}`}
              key={key}
              onClick={() => setTab(key)}
              role="tab"
              type="button"
            >
              <Icon size={15} /> {label}
              {key === "sessions" ? ` (${profile.sessions.length})` : key === "test-drives" ? ` (${profile.testDrives.length})` : ""}
            </button>
          ))}
        </div>

        <section aria-labelledby={`customer360-tab-${tab}`} className="ops-panel customer360-panel" id={`customer360-panel-${tab}`} role="tabpanel">
          {tab === "overview"
            ? profile.opportunities.map((opportunity) => (
                <OpportunityCard
                  key={opportunity.id}
                  offerSlot={
                    profile.offers.rules ? <EligibleOfferList opportunityId={opportunity.id} readOnly={readOnly || !profile.offers.lifecycle} /> : undefined
                  }
                  onInsightFeedback={editable ? (id) => void reportInsight(id) : undefined}
                  opportunity={opportunity}
                  readOnly={readOnly}
                />
              ))
            : null}
          {tab === "overview" && profile.opportunities.length === 0 ? (
            <p className="customer360-empty">Khách chưa có nhu cầu mua nào được ghi nhận.</p>
          ) : null}
          {tab === "sessions" ? (
            <SessionList
              onMove={editable ? (sessionId, target) => void moveSession(sessionId, target) : undefined}
              opportunities={profile.opportunities.map((item) => ({ id: item.id, title: item.title }))}
              readOnly={readOnly}
              role={role}
              sessions={profile.sessions}
            />
          ) : null}
          {tab === "test-drives" ? <TestDriveList items={profile.testDrives} /> : null}
          {tab === "offers" ? <IssuedOfferList customerId={customerId} readOnly={readOnly} /> : null}
        </section>
      </>
    );
  }

  return (
    <div className="customer360-page">
      <Link className="vehicle-detail-back" href={backHref}>
        <ArrowLeft size={16} /> {role === "admin" ? "Khách hàng & phân công" : "Khách hàng"}
      </Link>
      {body}
    </div>
  );
}
