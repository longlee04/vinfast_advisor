"use client";

import { ArrowLeft, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { joinAdvisorConversation, moveSessionOpportunity, releaseCustomer, sendInsightFeedback } from "@/lib/api/agent";
import { CustomerProfileUnavailableError, type CustomerProfileView, loadCustomerProfile } from "@/lib/api/customer360";
import type { TestDriveItem, ViewerRole } from "@/types/customer360";

import { BUYER_FOR_LABELS, HEAT_BAND_BADGES, POOL_TEXT } from "./customer360-labels";
import { CustomerSummary } from "./customer-summary";
import { EligibleOfferList } from "./eligible-offer-list";
import { IssuedOfferList } from "./issued-offer-list";
import { OpportunityOverview } from "./opportunity-card";
import { SessionList } from "./session-list";
import { StageBar } from "./stage-bar";

type TabKey = "overview" | "sessions" | "test-drives" | "offers";

const TABS: readonly { key: TabKey; label: string }[] = [
  { key: "overview", label: "Tổng quan" },
  { key: "sessions", label: "Phiên chat" },
  { key: "test-drives", label: "Lái thử" },
  { key: "offers", label: "Ưu đãi đã cấp" },
];

const BOOKING_BADGES: Record<string, { tone: "success" | "warning" | "neutral"; label: string }> = {
  REQUESTED: { tone: "warning", label: "Chờ xác nhận" },
  CONFIRMED: { tone: "success", label: "Đã xác nhận" },
  CANCELLED: { tone: "neutral", label: "Đã hủy" },
};

/** Phiên AI còn giữ hoặc khách đang chờ người — TVV tiếp quản được. */
const TAKEOVER_OWNERSHIP = new Set(["AI", "PENDING_HANDOFF"]);

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

/** Hồ sơ khách 360 (mockup 02) — dùng chung cho `/advisor/customers/[id]` và `/admin/customers/[id]`. */
export function CustomerProfilePage({ customerId, role, readOnly }: CustomerProfilePageProps) {
  const router = useRouter();
  const [profile, setProfile] = useState<CustomerProfileView | null>(null);
  const [error, setError] = useState<"forbidden" | "failed" | null>(null);
  const [tab, setTab] = useState<TabKey>("overview");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [takeover, setTakeover] = useState<"idle" | "busy" | "failed">("idle");
  const [releaseFailed, setReleaseFailed] = useState(false);

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

  // Chỉ TVV, và chỉ khi dữ liệu đến từ Customer 360 (màn dự phòng chưa có cơ hội để tách/gộp).
  const editable = !readOnly && profile?.source === "overview";
  const backHref =
    role === "admin" ? "/admin/chat-sessions" : "/advisor/customers";
  const backLabel = role === "admin" ? "Phiên chat" : "Khách hàng";

  async function moveSession(sessionId: string, target: string | null) {
    await moveSessionOpportunity(sessionId, target === null ? { action: "SPLIT" } : { action: "MOVE", opportunity_id: target });
    await load();
  }

  async function reportInsight(insightId: string) {
    await sendInsightFeedback(insightId, "WRONG");
    await load();
  }

  async function takeOver(sessionId: string) {
    setTakeover("busy");
    try {
      await joinAdvisorConversation(sessionId);
      router.push(`/advisor/conversations/${sessionId}`);
    } catch {
      setTakeover("failed");
    }
  }

  async function release() {
    if (!window.confirm("Trả khách về hàng chờ? Tư vấn viên khác sẽ nhận được khách này.")) return;
    try {
      await releaseCustomer(customerId);
      router.push("/advisor/customers");
    } catch {
      setReleaseFailed(true);
    }
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
    const selected = profile.opportunities.find((item) => item.id === selectedId) ?? profile.opportunities[0];
    const focus = profile.focusSessionId;
    const conversationHref = focus ? `/${role}/conversations/${focus}` : null;
    const canTakeOver = !readOnly && focus !== null && TAKEOVER_OWNERSHIP.has(profile.openOwnership ?? "");
    // Admin chỉ xem (lo kỹ thuật): không nhận/trả/phân công khách — người phụ trách là tư vấn viên.
    const actions = readOnly ? (
      conversationHref ? (
        <Link className="secondary-button" href={conversationHref}>
          Xem hội thoại
        </Link>
      ) : null
    ) : (
      <>
        {conversationHref ? (
          <Link className="secondary-button" href={conversationHref}>
            Xem hội thoại
          </Link>
        ) : null}
        {profile.header.phone ? (
          <a className="secondary-button" href={`tel:${profile.header.phone}`}>
            Gọi khách
          </a>
        ) : null}
        {profile.header.assigned_advisor_id ? (
          <button className="secondary-button" onClick={() => void release()} type="button">
            {POOL_TEXT.release}
          </button>
        ) : null}
        {canTakeOver && focus ? (
          <button className="primary-button" disabled={takeover === "busy"} onClick={() => void takeOver(focus)} type="button">
            {takeover === "busy" ? "Đang tiếp quản..." : "Tiếp quản hội thoại"}
          </button>
        ) : null}
      </>
    );

    body = (
      <>
        <CustomerSummary actions={actions} customer={profile.header} ownership={profile.openOwnership} turnsTotal={profile.turnsTotal}>
          {selected?.stage ? <StageBar history={selected.stageHistory} stage={selected.stage} /> : null}
        </CustomerSummary>
        {releaseFailed ? (
          <p className="catalog-result-note" role="alert">
            Không trả được khách — chỉ tư vấn viên đang phụ trách mới trả được.
          </p>
        ) : null}
        {takeover === "failed" ? (
          <p className="catalog-result-note" role="alert">
            Không tiếp quản được — phiên đã có người nhận hoặc đã kết thúc.
          </p>
        ) : null}

        {profile.opportunities.length > 1 ? (
          <div aria-label="Chọn nhu cầu mua" className="c360-filter-group c360-opportunity-switch" role="group">
            {profile.opportunities.map((item) => (
              <button aria-pressed={item.id === selected?.id} key={item.id} onClick={() => setSelectedId(item.id)} type="button">
                {[
                  item.title,
                  item.buyerFor ? BUYER_FOR_LABELS[item.buyerFor].toLowerCase() : null,
                  item.heatBand ? `${HEAT_BAND_BADGES[item.heatBand].label} ${item.heatScore ?? ""}`.trim() : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </button>
            ))}
          </div>
        ) : null}

        <div aria-label="Mục hồ sơ" className="customer360-tabs" role="tablist">
          {TABS.filter((item) => item.key !== "offers" || profile.offers.lifecycle).map(({ key, label }) => (
            <button
              aria-controls={`customer360-panel-${key}`}
              aria-selected={tab === key}
              id={`customer360-tab-${key}`}
              key={key}
              onClick={() => setTab(key)}
              role="tab"
              type="button"
            >
              {label}
              {key === "sessions" ? ` (${profile.sessions.length})` : key === "test-drives" ? ` (${profile.testDrives.length})` : ""}
            </button>
          ))}
        </div>

        <div aria-labelledby={`customer360-tab-${tab}`} className="customer360-panel-body" id={`customer360-panel-${tab}`} role="tabpanel">
          {tab === "overview" && selected ? (
            <OpportunityOverview
              conversationHref={conversationHref}
              customerFields={profile.fields}
              latestSummary={profile.latestSummary}
              offerSlot={profile.offers.rules ? <EligibleOfferList opportunityId={selected.id} readOnly={readOnly || !profile.offers.lifecycle} /> : undefined}
              onInsightFeedback={editable ? (id) => void reportInsight(id) : undefined}
              opportunity={selected}
              readOnly={readOnly}
              role={role}
            />
          ) : null}
          {tab === "overview" && !selected ? <p className="customer360-empty">Khách chưa có nhu cầu mua nào được ghi nhận.</p> : null}
          {tab === "sessions" ? (
            <section className="c360-card c360-section">
              <SessionList
                onMove={editable ? (sessionId, target) => void moveSession(sessionId, target) : undefined}
                opportunities={profile.opportunities.map((item) => ({ id: item.id, title: item.title }))}
                readOnly={readOnly}
                role={role}
                sessions={profile.sessions}
              />
            </section>
          ) : null}
          {tab === "test-drives" ? (
            <section className="c360-card c360-section">
              <TestDriveList items={profile.testDrives} />
            </section>
          ) : null}
          {tab === "offers" ? (
            <section className="c360-card c360-section">
              <IssuedOfferList customerId={customerId} readOnly={readOnly} />
            </section>
          ) : null}
        </div>
      </>
    );
  }

  return (
    <div className="customer360-page c360-page">
      <Link className="c360-back" href={backHref}>
        <ArrowLeft size={14} /> {backLabel}
      </Link>
      {body}
    </div>
  );
}
