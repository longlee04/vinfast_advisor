"use client";

import { Info, LoaderCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
  claimCustomer,
  type CustomerPoolItem,
  fetchCustomerPool,
  fetchMyCustomers,
  fetchOpportunitySummary,
  type MyCustomerItem,
  type OpportunityFilters,
  type OpportunitySummary,
} from "@/lib/api/agent";
import type { ViewerRole } from "@/types/customer360";

import {
  POOL_TEXT,
  PROFILE_SAVE_EXPLAINER,
  QUEUE_FILTER_LABELS,
  QUEUE_FOOTNOTE,
  QUEUE_KPI_LABELS,
  QUEUE_NO_ACTION,
  QUEUE_NO_NEED,
  type QueueFilter,
  barrierLabel,
  budgetText,
  nextActionLabel,
  relativeAge,
} from "./customer360-labels";
import { HeatPill } from "./heat-pill";
import { KpiTile } from "./kpi-tile";
import { customerProfileHref } from "./profile-links";
import { StageBar } from "./stage-bar";
import { useClock } from "./use-clock";

type Tab = "MINE" | "POOL";

const FILTERS: readonly QueueFilter[] = ["ALL", "HOT", "WAITING", "TEST_DRIVE"];

const FILTER_QUERY: Record<QueueFilter, OpportunityFilters> = {
  ALL: {},
  HOT: { band: "HOT" },
  WAITING: { waiting: true },
  TEST_DRIVE: { hasTestDrive: true },
};

/** Tên hiển thị: tên khách khai → email (đã che) → mã khách. */
function customerName(item: { display_name: string | null; email?: string | null; customer_id: string }): string {
  return item.display_name || item.email || item.customer_id;
}

function customerSubline(item: MyCustomerItem): string {
  if (item.waiting) return "Yêu cầu gặp người thật";
  const sessions = item.sessions_count ? `${item.sessions_count} phiên` : "Chưa chat";
  return [sessions, item.has_phone ? "để lại SĐT" : null].filter(Boolean).join(" · ");
}

/**
 * "Khách hàng" (plan §17–§20): hai tab — **Đã nhận** (mọi khách mình phụ trách, có nhu cầu hay
 * chưa) và **Chưa nhận** (hàng chờ, bấm "Nhận khách" để chuyển sang "Đã nhận"). Dòng giải thích
 * cho biết hồ sơ khách được lưu khi nào. Chỉ hiện khi cờ `customer360_ui` BẬT.
 */
export function OpportunityQueue({ role = "advisor" }: Readonly<{ role?: ViewerRole }>) {
  const [tab, setTab] = useState<Tab>("MINE");
  const [mine, setMine] = useState<readonly MyCustomerItem[] | null>(null);
  const [pool, setPool] = useState<readonly CustomerPoolItem[] | null>(null);
  const [mineTotal, setMineTotal] = useState<number | null>(null);
  const [summary, setSummary] = useState<OpportunitySummary | null>(null);
  const [filter, setFilter] = useState<QueueFilter>("ALL");
  const [error, setError] = useState<string | null>(null);

  const loadPool = useCallback(() => {
    fetchCustomerPool(200)
      .then(setPool)
      .catch(() => setPool([]));
  }, []);

  useEffect(() => {
    let active = true;
    fetchOpportunitySummary()
      .then((result) => {
        if (active) setSummary(result);
      })
      .catch(() => undefined);
    // Đếm tab "Đã nhận" theo danh sách KHÔNG lọc, để con số không đổi khi đổi bộ lọc.
    fetchMyCustomers({ limit: 500 })
      .then((rows) => {
        if (active) setMineTotal(rows.length);
      })
      .catch(() => undefined);
    loadPool();
    return () => {
      active = false;
    };
  }, [loadPool]);

  useEffect(() => {
    let active = true;
    fetchMyCustomers({ ...FILTER_QUERY[filter], limit: 500 })
      .then((rows) => {
        if (active) {
          setMine(rows);
          setError(null);
        }
      })
      .catch(() => {
        if (active) setError("Không tải được danh sách khách.");
      });
    return () => {
      active = false;
    };
  }, [filter]);

  function choose(next: QueueFilter) {
    if (next === filter) return;
    setMine(null);
    setFilter(next);
  }

  const tabs: readonly { key: Tab; label: string; count: number | null }[] = [
    { key: "MINE", label: "Đã nhận", count: mineTotal },
    { key: "POOL", label: "Chưa nhận", count: pool?.length ?? null },
  ];

  return (
    <section aria-label="Danh sách khách" className="c360-queue">
      <p className="c360-explainer">
        <Info aria-hidden="true" size={15} /> {PROFILE_SAVE_EXPLAINER}
      </p>

      <div aria-label="Nhóm khách" className="customer360-tabs" role="tablist">
        {tabs.map((item) => (
          <button
            aria-controls={`customers-panel-${item.key}`}
            aria-selected={tab === item.key}
            id={`customers-tab-${item.key}`}
            key={item.key}
            onClick={() => setTab(item.key)}
            role="tab"
            type="button"
          >
            {item.label}
            {item.count !== null ? ` (${item.count})` : ""}
          </button>
        ))}
      </div>

      <div aria-labelledby={`customers-tab-${tab}`} className="c360-queue" id={`customers-panel-${tab}`} role="tabpanel">
        {tab === "MINE" ? (
          <MyCustomers error={error} filter={filter} items={mine} onFilter={choose} role={role} summary={summary} />
        ) : (
          <CustomerPool
            items={pool}
            onClaimed={() => {
              loadPool();
              setMineTotal((count) => (count === null ? count : count + 1));
            }}
            onConflict={loadPool}
            role={role}
          />
        )}
      </div>
      <p className="c360-footnote">{QUEUE_FOOTNOTE}</p>
    </section>
  );
}

function MyCustomers({
  items,
  summary,
  filter,
  onFilter,
  error,
  role,
}: Readonly<{
  items: readonly MyCustomerItem[] | null;
  summary: OpportunitySummary | null;
  filter: QueueFilter;
  onFilter: (next: QueueFilter) => void;
  error: string | null;
  role: ViewerRole;
}>) {
  const now = useClock();
  return (
    <>
      <header className="c360-queue-head">
        <div aria-label="Lọc khách" className="c360-filter-group" role="group">
          {FILTERS.map((value) => (
            <button aria-pressed={filter === value} key={value} onClick={() => onFilter(value)} type="button">
              {QUEUE_FILTER_LABELS[value]}
            </button>
          ))}
        </div>
      </header>

      <div className="c360-kpi-grid">
        {(Object.keys(QUEUE_KPI_LABELS) as (keyof typeof QUEUE_KPI_LABELS)[]).map((key) => {
          const tile = QUEUE_KPI_LABELS[key];
          const target = tile.filter;
          return (
            <KpiTile
              emphasis={key === "hot"}
              hint={tile.hint}
              key={key}
              onSelect={target ? () => onFilter(target) : undefined}
              selected={target ? filter === target : undefined}
              title={tile.title}
              value={summary ? summary[key] : null}
            />
          );
        })}
      </div>

      {error ? (
        <p className="catalog-result-note" role="alert">
          {error}
        </p>
      ) : null}
      {items === null && !error ? (
        <div aria-busy="true" className="ops-state">
          <LoaderCircle className="spin" size={22} />
        </div>
      ) : null}
      {items !== null && items.length === 0 ? (
        <div className="ops-state c360-card">
          <Sparkles size={24} />
          <h2>{filter === "ALL" ? "Bạn chưa nhận khách nào" : "Không có khách nào khớp bộ lọc"}</h2>
          {filter === "ALL" ? <p>Sang tab “Chưa nhận” để nhận khách — nhận xong khách sẽ nằm ở đây.</p> : null}
        </div>
      ) : null}
      {items?.length ? (
        <div className="c360-card c360-queue-table-wrap">
          <table className="c360-queue-table">
            <thead>
              <tr>
                <th scope="col">Độ nóng</th>
                <th scope="col">Khách</th>
                <th scope="col">Xe quan tâm</th>
                <th scope="col">Ngân sách</th>
                <th scope="col">Rào cản chính</th>
                <th scope="col">Giai đoạn</th>
                <th scope="col">Lần cuối</th>
                <th scope="col">Việc nên làm</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const href = customerProfileHref(item.customer_id, role);
                const name = customerName(item);
                const budget = budgetText(item.slots);
                const [barrier, ...moreBarriers] = item.barriers;
                const next = item.next_action
                  ? nextActionLabel(item.next_action)
                  : item.opportunity_id
                    ? QUEUE_NO_ACTION
                    : QUEUE_NO_NEED;
                return (
                  <tr key={item.customer_id}>
                    <td data-label="Độ nóng">
                      {item.heat_band ? <HeatPill band={item.heat_band} score={item.heat_score} /> : <span className="c360-muted">—</span>}
                    </td>
                    <td data-label="Khách">
                      <Link className="c360-customer-link" href={href}>
                        {name}
                      </Link>
                      <small className="c360-muted">{customerSubline(item)}</small>
                    </td>
                    <td className="c360-strong" data-label="Xe quan tâm">
                      {item.top_vehicle_name || "—"}
                    </td>
                    <td data-empty={!budget || undefined} data-label="Ngân sách">
                      {budget ?? "Chưa nói"}
                    </td>
                    <td data-label="Rào cản chính">
                      {barrier ? (
                        <span className="c360-chip">
                          {barrierLabel(barrier)}
                          {moreBarriers.length ? (
                            <span aria-label={`và ${moreBarriers.length} rào cản khác`}> +{moreBarriers.length}</span>
                          ) : null}
                        </span>
                      ) : (
                        <span className="c360-muted">—</span>
                      )}
                    </td>
                    <td data-label="Giai đoạn">
                      {item.stage ? <StageBar stage={item.stage} variant="compact" /> : <span className="c360-muted">—</span>}
                    </td>
                    <td className="c360-muted" data-label="Lần cuối">
                      {relativeAge(item.last_seen_at, now)}
                    </td>
                    <td data-label="Việc nên làm">
                      <div className="c360-next-cell">
                        <span>{next}</span>
                        <Link aria-label={`Mở hồ sơ ${name}`} href={href}>
                          Mở hồ sơ
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

/** Hàng chờ khách chưa ai phụ trách: khách đang chờ người trước, rồi nóng nhất (backend sắp). */
function CustomerPool({
  items,
  role,
  onClaimed,
  onConflict,
}: Readonly<{ items: readonly CustomerPoolItem[] | null; role: ViewerRole; onClaimed: () => void; onConflict: () => void }>) {
  const router = useRouter();
  const now = useClock();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function claim(customerId: string) {
    setBusy(customerId);
    setError(null);
    try {
      await claimCustomer(customerId);
      onClaimed();
      router.push(customerProfileHref(customerId, role));
    } catch (err: unknown) {
      setBusy(null);
      setError((err as { status?: number }).status === 409 ? POOL_TEXT.taken : "Không nhận được khách.");
      onConflict();
    }
  }

  return (
    <>
      <p className="c360-muted c360-pool-hint">{POOL_TEXT.hint}</p>
      {error ? (
        <p className="catalog-result-note" role="alert">
          {error}
        </p>
      ) : null}
      {items === null ? (
        <div aria-busy="true" className="ops-state">
          <LoaderCircle className="spin" size={22} />
        </div>
      ) : null}
      {items !== null && items.length === 0 ? (
        <div className="ops-state c360-card">
          <Sparkles size={24} />
          <h2>{POOL_TEXT.empty}</h2>
        </div>
      ) : null}
      {items?.length ? (
        <div className="c360-card c360-queue-table-wrap">
          <table className="c360-queue-table">
            <thead>
              <tr>
                <th scope="col">Độ nóng</th>
                <th scope="col">Khách</th>
                <th scope="col">Ngân sách</th>
                <th scope="col">Giai đoạn</th>
                <th scope="col">Lần cuối</th>
                <th scope="col">
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const budget = budgetText(item.slots);
                const name = customerName(item);
                const subline = [
                  item.waiting ? "Yêu cầu gặp người thật" : null,
                  item.sessions_count ? `${item.sessions_count} phiên` : "Chưa chat",
                  item.phone,
                ]
                  .filter(Boolean)
                  .join(" · ");
                return (
                  <tr key={item.customer_id}>
                    <td data-label="Độ nóng">
                      {item.heat_band ? <HeatPill band={item.heat_band} score={item.heat_score} /> : <span className="c360-muted">—</span>}
                    </td>
                    <td data-label="Khách">
                      <span className="c360-customer-link">{name}</span>
                      <small className="c360-muted">{subline}</small>
                    </td>
                    <td data-empty={!budget || undefined} data-label="Ngân sách">
                      {budget ?? "Chưa nói"}
                    </td>
                    <td data-label="Giai đoạn">
                      {item.stage ? <StageBar stage={item.stage} variant="compact" /> : <span className="c360-muted">—</span>}
                    </td>
                    <td className="c360-muted" data-label="Lần cuối">
                      {relativeAge(item.last_seen_at, now)}
                    </td>
                    <td data-label="Thao tác">
                      <button
                        aria-label={`${POOL_TEXT.claim} ${name}`}
                        className="primary-button"
                        disabled={busy !== null}
                        onClick={() => void claim(item.customer_id)}
                        type="button"
                      >
                        {busy === item.customer_id ? "Đang nhận..." : POOL_TEXT.claim}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}
