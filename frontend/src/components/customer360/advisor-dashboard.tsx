"use client";

import { LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { NoticeCard } from "@/components/advisor/notice-card";
import { HorizontalBarChart } from "@/components/shared/horizontal-bar-chart";
import {
  fetchCustomerPool,
  fetchOpportunities,
  fetchOpportunitySummary,
  type OpportunityListItem,
  type OpportunitySummary,
} from "@/lib/api/agent";

import {
  DASHBOARD_TEXT,
  QUEUE_KPI_LABELS,
  SALES_STAGE_LABELS,
  SALES_STAGE_ORDER,
  actionPriority,
  barrierLabel,
  nextActionLabel,
  relativeAge,
} from "./customer360-labels";
import { HeatPill } from "./heat-pill";
import { KpiTile } from "./kpi-tile";
import { customerProfileHref } from "./profile-links";
import { useClock } from "./use-clock";

/** Số việc hiện trên dashboard — hơn thế thì sang "Khách hàng". */
const TODO_LIMIT = 8;

type DashboardData = {
  readonly summary: OpportunitySummary | null;
  readonly opportunities: readonly OpportunityListItem[];
  readonly poolCount: number | null;
};

/** Việc cần làm hôm nay: mỗi khách một việc (việc đầu của khách), gấp trước, nóng trước. */
export function todayTodos(items: readonly OpportunityListItem[]): OpportunityListItem[] {
  const seen = new Set<string>();
  return items
    .filter((item) => item.next_action)
    .sort(
      (left, right) =>
        actionPriority(left.next_action?.code ?? "") - actionPriority(right.next_action?.code ?? "") || right.heat_score - left.heat_score,
    )
    .filter((item) => (seen.has(item.customer_id) ? false : (seen.add(item.customer_id), true)))
    .slice(0, TODO_LIMIT);
}

/** Rào cản phổ biến: số cơ hội có mỗi rào cản (một khách lo giá ở 3 phiên vẫn tính 1). */
export function barrierCounts(items: readonly OpportunityListItem[]): { label: string; value: number }[] {
  const counts = new Map<string, number>();
  for (const item of items) for (const code of new Set(item.barriers)) counts.set(code, (counts.get(code) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).map(([code, value]) => ({ label: barrierLabel(code), value }));
}

/**
 * "Tổng quan" của tư vấn viên (plan §15, §17): tình hình KHÁCH CỦA TÔI — hôm nay làm gì trước,
 * khách đang ở giai đoạn nào, hay vướng gì, còn bao nhiêu khách chưa ai nhận. Chỉ ghép từ
 * API đã có (cùng phạm vi TVV): thẻ số, danh sách cơ hội, hàng chờ.
 */
export function AdvisorDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [failed, setFailed] = useState(false);
  const now = useClock();

  useEffect(() => {
    let active = true;
    Promise.allSettled([fetchOpportunitySummary(), fetchOpportunities({ limit: 200 }), fetchCustomerPool(200)]).then(
      ([summary, opportunities, pool]) => {
        if (!active) return;
        if (opportunities.status === "rejected") {
          setFailed(true);
          return;
        }
        setData({
          summary: summary.status === "fulfilled" ? summary.value : null,
          opportunities: opportunities.value,
          poolCount: pool.status === "fulfilled" ? pool.value.length : null,
        });
      },
    );
    return () => {
      active = false;
    };
  }, []);

  const opportunities = data?.opportunities ?? [];
  const todos = todayTodos(opportunities);
  const stages = SALES_STAGE_ORDER.map((stage) => ({
    label: SALES_STAGE_LABELS[stage],
    value: opportunities.filter((item) => item.stage === stage).length,
  }));
  const barriers = barrierCounts(opportunities);

  return (
    <section aria-label="Tổng quan" className="c360-queue">
      {failed ? (
        <p className="catalog-result-note" role="alert">
          {DASHBOARD_TEXT.failed}
        </p>
      ) : null}

      <div className="c360-kpi-grid">
        {(Object.keys(QUEUE_KPI_LABELS) as (keyof typeof QUEUE_KPI_LABELS)[]).map((key) => (
          <KpiTile
            emphasis={key === "hot"}
            hint={QUEUE_KPI_LABELS[key].hint}
            key={key}
            title={QUEUE_KPI_LABELS[key].title}
            value={data?.summary ? data.summary[key] : null}
          />
        ))}
      </div>

      {data === null && !failed ? (
        <div aria-busy="true" className="ops-state">
          <LoaderCircle className="spin" size={22} />
        </div>
      ) : null}

      {data ? (
        <div className="c360-overview-grid">
          <section aria-labelledby="c360-todo-today" className="c360-card c360-section">
            <div className="c360-section-head">
              <h2 id="c360-todo-today">{DASHBOARD_TEXT.todoTitle}</h2>
              <span className="c360-muted">{DASHBOARD_TEXT.todoHint}</span>
            </div>
            {todos.length ? (
              <ul className="c360-today">
                {todos.map((item) => {
                  const name = item.display_name || item.customer_id;
                  return (
                    <li key={item.opportunity_id}>
                      <HeatPill band={item.heat_band} score={item.heat_score} />
                      <div>
                        <strong>{name}</strong>
                        <span>{item.next_action ? nextActionLabel(item.next_action) : ""}</span>
                      </div>
                      <small className="c360-muted">{relativeAge(item.last_seen_at, now)}</small>
                      <Link aria-label={`Mở hồ sơ ${name}`} href={customerProfileHref(item.customer_id)}>
                        Mở hồ sơ
                      </Link>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="customer360-empty">{DASHBOARD_TEXT.todoEmpty}</p>
            )}
          </section>

          <div className="c360-column">
            <NoticeCard />
            <section aria-labelledby="c360-pool-card" className="c360-card c360-section">
              <h2 id="c360-pool-card">{DASHBOARD_TEXT.poolTitle}</h2>
              <p className="c360-pool-count">
                <strong>{data.poolCount ?? "—"}</strong> {DASHBOARD_TEXT.poolUnit}
              </p>
              <Link href="/advisor/customers">{DASHBOARD_TEXT.poolLink}</Link>
            </section>
            <div className="c360-card c360-section">
              <HorizontalBarChart data={stages} emptyText={DASHBOARD_TEXT.chartEmpty} title={DASHBOARD_TEXT.funnelTitle} />
            </div>
            <div className="c360-card c360-section">
              <HorizontalBarChart data={barriers} emptyText={DASHBOARD_TEXT.barrierEmpty} title={DASHBOARD_TEXT.barrierTitle} />
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
