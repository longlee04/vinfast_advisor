"use client";

import { AlertCircle, ChevronLeft, ChevronRight, ExternalLink, LogIn, Maximize2, MessageSquare, PanelRightClose, RotateCcw, Search, ShieldAlert, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import { bottleneckLabel } from "@/components/advisor/offer-state-labels";
import { HEAT_BAND_BADGES, needSummary } from "@/components/customer360/customer360-labels";
import { customerProfileHref } from "@/components/customer360/profile-links";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  type AdvisorConversationDetail,
  closeAdvisorConversation,
  fetchAdvisorConversation,
  listAdvisorConversations,
} from "@/lib/api/agent";
import { getLiveChatSession, subscribeLiveChatSession } from "@/lib/live-chat-session";
import { useAuth } from "@/store/auth-store";
import type { ChatSession } from "@/types/chat-observability";

/**
 * Bảng phiên chat DÙNG CHUNG cho hai phía (plan Customer 360, Phase 1).
 *
 * Trước đây `/advisor/conversations` và `/admin/chat-sessions` mỗi bên tự viết một
 * bảng dù cùng gọi `listAdvisorConversations` — hai cách chuẩn hoá trạng thái, hai
 * cách lọc, hai lỗi khác nhau. Giờ dữ liệu, lọc, KPI nằm ở đây; `scope` chỉ quyết
 * định phần khác nhau thật sự:
 *
 * - `"mine"` (TVV): nút Vào chat / Đóng phiên, xem nhanh bên phải.
 * - `"all"` (Admin): cột + bộ lọc Advisor, khoảng ngày, link sang trang trace, và
 *   gộp phiên khách đang mở trong chính trình duyệt này (demo "Trực tiếp").
 *
 * Phạm vi dữ liệu do BACKEND quyết (Phase 0): TVV chỉ nhận phiên của mình, nên
 * `scope` ở đây không phải cơ chế phân quyền.
 */

export type ChatSessionScope = "mine" | "all";
export type ChatSessionRowStatus = "ACTIVE" | "WAITING_ADVISOR" | "CLOSED";

export type ChatSessionRow = {
  readonly id: string;
  readonly customerId: string;
  readonly customerName: string;
  readonly customerSub: string;
  readonly advisorId: string | null;
  readonly status: ChatSessionRowStatus;
  readonly lastMessagePreview: string;
  readonly lastActivityAt: string | null;
  readonly isLive: boolean;
  /** AI | PENDING_HANDOFF | HUMAN — backend Phase 3. */
  readonly ownership: string;
  /** Tóm tắt nhu cầu từ slot — hiện ở dòng phụ khi đã có tên khách. */
  readonly needSummary: string | null;
  readonly heatBand: "HOT" | "WARM" | "COLD" | null;
  readonly bottlenecks: readonly string[];
  readonly source: AdvisorConversationDetail | null;
};

type StatusFilter = "ALL" | "ACTIVE" | "WAITING" | "CLOSED" | "STALE" | "HOT";

/** "Khách chờ > 5 phút" (plan §2.5). */
export const WAITING_STALE_MS = 5 * 60_000;
/** "Đang online": có hoạt động trong 15 phút gần nhất. */
const ONLINE_WINDOW_MS = 15 * 60_000;
type DayRange = "ALL" | "TODAY" | "WEEK" | "MONTH";

const PAGE_SIZE = 10;
const DAY_MS = 86_400_000;
const DAY_RANGE_LABELS: Record<DayRange, string> = { ALL: "Tất cả", TODAY: "Hôm nay", WEEK: "7 ngày", MONTH: "30 ngày" };

type ScopeCopy = {
  readonly searchPlaceholder: string;
  readonly waitingKpi: string;
  readonly waitingStatus: string;
  readonly emptyTitle: string;
  readonly emptyHint: string | null;
};

const SCOPE_COPY: Record<ChatSessionScope, ScopeCopy> = {
  mine: {
    searchPlaceholder: "Tìm mã phiên, khách hàng...",
    waitingKpi: "Cần bạn xử lý",
    waitingStatus: "Cần bạn xử lý",
    emptyTitle: "Không tìm thấy phiên chat nào phù hợp.",
    emptyHint: null,
  },
  all: {
    searchPlaceholder: "Tìm customer / session / trace...",
    waitingKpi: "Chờ Advisor",
    waitingStatus: "Chờ Advisor",
    emptyTitle: "Không tìm thấy phiên chat",
    emptyHint: "Thử điều chỉnh từ khóa hoặc bộ lọc.",
  },
};

const STATUS_TONES: Record<ChatSessionRowStatus, "info" | "warning" | "success"> = {
  ACTIVE: "info",
  WAITING_ADVISOR: "warning",
  CLOSED: "success",
};

function normalizeStatus(raw: string | undefined): ChatSessionRowStatus {
  const status = raw?.toUpperCase();
  if (status === "WAITING_ADVISOR") return "WAITING_ADVISOR";
  if (status === "COMPLETED" || status === "CLOSED") return "CLOSED";
  return "ACTIVE";
}

/** Chuẩn hoá một dòng backend — nơi DUY NHẤT hai phía đọc `AdvisorConversationDetail`. */
export function toChatSessionRow(item: AdvisorConversationDetail): ChatSessionRow {
  const isAnonymous = item.customer_id.startsWith("anon-");
  return {
    id: item.conversation_id,
    customerId: item.customer_id,
    customerName: item.customer_display || needSummary(item.slots) || (isAnonymous ? "Khách vãng lai" : "Khách hàng"),
    customerSub: isAnonymous ? "Khách vãng lai" : item.customer_id,
    advisorId: item.assigned_advisor_id ?? null,
    status: normalizeStatus(item.status),
    lastMessagePreview: item.last_message_preview || "",
    lastActivityAt: item.last_activity_at || null,
    isLive: false,
    ownership: item.ownership ?? "AI",
    needSummary: item.customer_display ? needSummary(item.slots) : null,
    heatBand: item.heat_band ?? null,
    bottlenecks: item.bottlenecks ?? [],
    source: item,
  };
}

function liveToRow(session: ChatSession): ChatSessionRow {
  return {
    id: session.id,
    customerId: session.customer.id,
    customerName: session.customer.name,
    customerSub: session.customer.email,
    advisorId: session.advisor?.id ?? null,
    status: normalizeStatus(session.status),
    lastMessagePreview: "",
    lastActivityAt: null,
    isLive: true,
    ownership: "AI",
    needSummary: null,
    heatBand: null,
    bottlenecks: [],
    source: null,
  };
}

export type ChatSessionKpiCounts = { total: number; active: number; waiting: number; closed: number };

/**
 * KPI trên TOÀN BỘ phiên, trước tìm kiếm/lọc.
 *
 * "Đang hoạt động" giữ đúng nghĩa cũ của từng màn: TVV đếm mọi phiên chưa đóng
 * (phiên chờ mình cũng là phiên đang sống), Admin đếm riêng ACTIVE để ba thẻ cộng
 * lại khớp tổng. Thống nhất nghĩa là việc của Phase 3 (bộ KPI mới).
 */
export function computeChatSessionKpis(rows: readonly ChatSessionRow[], scope: ChatSessionScope): ChatSessionKpiCounts {
  let active = 0;
  let waiting = 0;
  let closed = 0;
  for (const row of rows) {
    if (row.status === "CLOSED") closed += 1;
    else if (row.status === "WAITING_ADVISOR") {
      waiting += 1;
      if (scope === "mine") active += 1;
    } else active += 1;
  }
  return { total: rows.length, active, waiting, closed };
}

function ageMs(row: ChatSessionRow, now: number): number | null {
  if (row.lastActivityAt === null) return null;
  const at = new Date(row.lastActivityAt).getTime();
  return Number.isNaN(at) ? null : now - at;
}

/** Phiên khách đang chờ người quá 5 phút — mốc là lần hoạt động cuối của phiên. */
export function isStaleWaiting(row: ChatSessionRow, now: number): boolean {
  const age = ageMs(row, now);
  return row.status === "WAITING_ADVISOR" && age !== null && age > WAITING_STALE_MS;
}

/** Khách nóng còn đang online: độ nóng HOT, phiên chưa đóng, hoạt động trong 15 phút. */
export function isHotOnline(row: ChatSessionRow, now: number): boolean {
  const age = ageMs(row, now);
  return row.heatBand === "HOT" && row.status !== "CLOSED" && age !== null && age <= ONLINE_WINDOW_MS;
}

/** Đồng hồ 30 giây cho KPI theo thời gian — render vẫn thuần, chỉ đọc snapshot. */
function subscribeClock(callback: () => void): () => void {
  const timer = setInterval(callback, 30_000);
  return () => clearInterval(timer);
}

function clockSnapshot(): number {
  return Math.floor(Date.now() / 30_000) * 30_000;
}

function useNow(): number {
  return useSyncExternalStore(subscribeClock, clockSnapshot, () => 0);
}

function matchesStatus(row: ChatSessionRow, filter: StatusFilter, now: number): boolean {
  if (filter === "ALL") return true;
  if (filter === "STALE") return isStaleWaiting(row, now);
  if (filter === "HOT") return isHotOnline(row, now);
  if (filter === "CLOSED") return row.status === "CLOSED";
  if (filter === "WAITING") return row.status === "WAITING_ADVISOR";
  return row.status !== "CLOSED";
}

function matchesDayRange(row: ChatSessionRow, range: DayRange, now: number): boolean {
  if (range === "ALL" || row.lastActivityAt === null) return true;
  const at = new Date(row.lastActivityAt).getTime();
  if (Number.isNaN(at)) return true;
  const days = (now - at) / DAY_MS;
  return range === "TODAY" ? days < 1 : range === "WEEK" ? days <= 7 : days <= 30;
}

function formatDateTime(iso: string | null): { time: string; date: string } {
  if (!iso) return { time: "Trực tiếp", date: "Đang diễn ra" };
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return { time: iso, date: "" };
  return {
    time: value.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }),
    date: value.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" }),
  };
}

/** Phiên khách đang mở trong trình duyệt này (cùng tab hoặc tab khác qua storage event). */
function useLiveRow(enabled: boolean): ChatSessionRow | null {
  const { user } = useAuth();
  const live = useSyncExternalStore(
    subscribeLiveChatSession,
    () => (enabled ? getLiveChatSession(user?.email) : null),
    () => null,
  );
  return useMemo(() => (live ? liveToRow(live) : null), [live]);
}

/** Tải + gộp dòng phiên. Dùng lại cho bảng đầy đủ và khối "phiên gần đây" của dashboard. */
export function useChatSessionRows(scope: ChatSessionScope, customerId?: string) {
  const { user } = useAuth();
  const [backendRows, setBackendRows] = useState<readonly ChatSessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await listAdvisorConversations(customerId);
      setBackendRows((response.items || []).map(toChatSessionRow));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setError(
        message.includes("401") || message.includes("authentication required")
          ? "Chưa đăng nhập tài khoản nhân sự để xem danh sách phiên."
          : "Không thể tải danh sách phiên chat.",
      );
      setBackendRows([]);
    } finally {
      setLoading(false);
    }
  }, [customerId]);

  useEffect(() => {
    void reload();
  }, [reload, user]);

  const liveRow = useLiveRow(scope === "all" && customerId === undefined);
  // Backend trước, phiên live ghi đè nếu trùng id — không bao giờ nhân đôi một phiên.
  const rows = useMemo(() => {
    const byId = new Map<string, ChatSessionRow>();
    for (const row of backendRows) byId.set(row.id, row);
    if (liveRow) byId.set(liveRow.id, liveRow);
    return Array.from(byId.values());
  }, [backendRows, liveRow]);

  return { rows, loading, error, reload };
}

type KpiCardProps = {
  label: string;
  value: number;
  note: string;
  selected: boolean;
  onSelect: () => void;
};

function KpiCard({ label, value, note, selected, onSelect }: Readonly<KpiCardProps>) {
  return (
    <article
      aria-pressed={selected}
      className={selected ? "metric-card is-selected" : "metric-card"}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") onSelect();
      }}
      role="button"
      tabIndex={0}
    >
      <span>{label}</span>
      <strong>{value.toLocaleString("vi-VN")}</strong>
      <small>{note}</small>
    </article>
  );
}

export type ChatSessionTableProps = {
  /** `"mine"`: màn TVV. `"all"`: màn Admin. */
  readonly scope: ChatSessionScope;
  /** Chỉ lấy phiên của một khách — dùng ở tab Phiên chat của hồ sơ khách. */
  readonly customerId?: string;
  /** Ẩn KPI khi nhúng trong trang khác (hồ sơ khách). */
  readonly showKpis?: boolean;
};

export function ChatSessionTable({ scope, customerId, showKpis = true }: ChatSessionTableProps) {
  const { user } = useAuth();
  const isStaff = user?.role === "advisor" || user?.role === "admin";
  const copy = SCOPE_COPY[scope];
  const { rows, loading, error, reload } = useChatSessionRows(scope, customerId);

  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [advisorFilter, setAdvisorFilter] = useState("ALL");
  const [dayRange, setDayRange] = useState<DayRange>("ALL");
  // Mốc "bây giờ" chốt lúc chọn khoảng ngày — render phải thuần, không gọi Date.now() trong đó.
  const [dayAnchor, setDayAnchor] = useState<number | null>(null);
  const [page, setPage] = useState(1);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [preview, setPreview] = useState<AdvisorConversationDetail | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [toClose, setToClose] = useState<ChatSessionRow | null>(null);
  const [closing, setClosing] = useState(false);

  const canPreview = scope === "mine";

  useEffect(() => {
    if (!canPreview || !selectedId) {
      setPreview(null);
      return;
    }
    let active = true;
    setPreviewLoading(true);
    fetchAdvisorConversation(selectedId)
      .then((data) => {
        if (active) setPreview(data);
      })
      .catch(() => {
        if (active) setPreview(null);
      })
      .finally(() => {
        if (active) setPreviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [canPreview, selectedId]);

  const now = useNow();
  const kpis = useMemo(() => computeChatSessionKpis(rows, scope), [rows, scope]);
  const staleCount = useMemo(() => rows.filter((row) => isStaleWaiting(row, now)).length, [rows, now]);
  const hasHeat = rows.some((row) => row.heatBand !== null);
  const hotCount = useMemo(() => rows.filter((row) => isHotOnline(row, now)).length, [rows, now]);
  const advisors = useMemo(
    () => Array.from(new Set(rows.flatMap((row) => (row.advisorId ? [row.advisorId] : [])))),
    [rows],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (!matchesStatus(row, statusFilter, now)) return false;
      if (scope === "all" && advisorFilter !== "ALL" && row.advisorId !== advisorFilter) return false;
      if (scope === "all" && dayAnchor !== null && !matchesDayRange(row, dayRange, dayAnchor)) return false;
      if (!needle) return true;
      return [row.id, row.customerId, row.customerName, row.customerSub, row.lastMessagePreview, row.advisorId ?? ""].some(
        (value) => value.toLowerCase().includes(needle),
      );
    });
  }, [rows, query, statusFilter, advisorFilter, dayRange, dayAnchor, scope, now]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageRows = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  function selectStatus(next: StatusFilter) {
    setStatusFilter(next);
    setPage(1);
  }

  async function confirmClose() {
    if (!toClose) return;
    setClosing(true);
    try {
      await closeAdvisorConversation(toClose.id);
      if (selectedId === toClose.id) setSelectedId(null);
      setToClose(null);
      await reload();
    } catch (err: unknown) {
      alert("Không thể kết thúc phiên: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setClosing(false);
    }
  }

  const detailHref = (id: string) => (scope === "all" ? `/admin/chat-sessions/${id}` : `/advisor/conversations/${id}`);

  return (
    <>
      {showKpis && scope === "all" ? (
        <div className="metric-grid chat-kpi-grid">
          <KpiCard
            label="Tổng phiên"
            note={`${kpis.active} đang hoạt động · ${kpis.closed} đã đóng`}
            onSelect={() => selectStatus("ALL")}
            selected={statusFilter === "ALL"}
            value={kpis.total}
          />
          <KpiCard
            label="Đang hoạt động"
            note={kpis.active > 0 ? `${kpis.active} phiên cần theo dõi` : "Không có phiên trực tiếp"}
            onSelect={() => selectStatus("ACTIVE")}
            selected={statusFilter === "ACTIVE"}
            value={kpis.active}
          />
          <KpiCard
            label={copy.waitingKpi}
            note={kpis.waiting > 0 ? `${kpis.waiting} yêu cầu cần can thiệp` : "Không có phiên cần can thiệp"}
            onSelect={() => selectStatus("WAITING")}
            selected={statusFilter === "WAITING"}
            value={kpis.waiting}
          />
        </div>
      ) : null}
      {/* Plan §2.5: màn TVV thay ba thẻ đếm trùng nhau bằng ba thẻ "việc cần làm". */}
      {showKpis && scope === "mine" ? (
        <div className="metric-grid chat-kpi-grid">
          <KpiCard
            label="Cần bạn xử lý"
            note={kpis.waiting > 0 ? `${kpis.waiting} khách đang chờ tư vấn viên` : "Không có phiên cần can thiệp"}
            onSelect={() => selectStatus("WAITING")}
            selected={statusFilter === "WAITING"}
            value={kpis.waiting}
          />
          <KpiCard
            label="Khách chờ > 5 phút"
            note={staleCount > 0 ? "Ưu tiên nhận ngay" : "Không ai chờ lâu"}
            onSelect={() => selectStatus("STALE")}
            selected={statusFilter === "STALE"}
            value={staleCount}
          />
          {hasHeat ? (
            <KpiCard
              label="Khách nóng đang online"
              note="Hoạt động trong 15 phút gần nhất"
              onSelect={() => selectStatus("HOT")}
              selected={statusFilter === "HOT"}
              value={hotCount}
            />
          ) : (
            <KpiCard
              label="Tổng phiên"
              note={`${kpis.active} đang hoạt động · ${kpis.closed} đã đóng`}
              onSelect={() => selectStatus("ALL")}
              selected={statusFilter === "ALL"}
              value={kpis.total}
            />
          )}
        </div>
      ) : null}

      <section className="chat-session-list ops-panel">
        <div className="chat-session-toolbar">
          <label className="ops-search">
            <Search size={16} />
            <span className="sr-only">Tìm phiên chat</span>
            <input
              onChange={(event) => {
                setQuery(event.target.value);
                setPage(1);
              }}
              placeholder={copy.searchPlaceholder}
              value={query}
            />
          </label>
          <div className="chat-session-selects">
            <label>
              <span>Trạng thái</span>
              <select onChange={(event) => selectStatus(event.target.value as StatusFilter)} value={statusFilter}>
                <option value="ALL">Tất cả</option>
                <option value="ACTIVE">Đang hoạt động</option>
                <option value="WAITING">{copy.waitingStatus}</option>
                <option value="CLOSED">Đã đóng</option>
                {scope === "mine" ? <option value="STALE">Khách chờ quá 5 phút</option> : null}
                {scope === "mine" && hasHeat ? <option value="HOT">Khách nóng đang online</option> : null}
              </select>
            </label>
            {scope === "all" ? (
              <>
                <label>
                  <span>Advisor</span>
                  <select onChange={(event) => setAdvisorFilter(event.target.value)} value={advisorFilter}>
                    <option value="ALL">Tất cả</option>
                    {advisors.map((id) => (
                      <option key={id} value={id}>
                        {id}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Khoảng ngày</span>
                  <select
                    onChange={(event) => {
                      setDayRange(event.target.value as DayRange);
                      setDayAnchor(Date.now());
                      setPage(1);
                    }}
                    value={dayRange}
                  >
                    {Object.entries(DAY_RANGE_LABELS).map(([key, label]) => (
                      <option key={key} value={key}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              </>
            ) : null}
            <button className="secondary-button" onClick={() => void reload()} title="Làm mới dữ liệu" type="button">
              <RotateCcw size={13} /> Làm mới
            </button>
          </div>
        </div>

        {!isStaff ? (
          <div className="inline-warning" role="status">
            <ShieldAlert size={16} /> Bạn chưa đăng nhập tài khoản nhân sự.{" "}
            <Link href="/staff-login">
              <LogIn size={14} /> Đăng nhập
            </Link>
          </div>
        ) : null}

        <div className="chat-session-result">
          <span>
            <strong>{filtered.length}</strong> phiên hiển thị
          </span>
          <span>{rows.length ? "Dữ liệu phiên thực tế từ hệ thống" : "Chưa có phiên chat nào"}</span>
        </div>

        {loading && rows.length === 0 ? <p className="catalog-result-note">Đang tải danh sách phiên chat...</p> : null}
        {error ? (
          <p className="catalog-result-note" role="alert">
            {error}
          </p>
        ) : null}

        {!loading && !error && filtered.length === 0 ? (
          <div className="ops-state">
            <MessageSquare size={28} />
            <h2>{copy.emptyTitle}</h2>
            {copy.emptyHint ? <p>{copy.emptyHint}</p> : null}
          </div>
        ) : null}

        {filtered.length > 0 ? (
          <div className={selectedId && canPreview ? "chat-session-split" : undefined}>
            <div className="chat-table-wrap">
              <table className="chat-table">
                <thead>
                  <tr>
                    <th>Mã phiên</th>
                    <th>Khách hàng</th>
                    {scope === "all" ? <th>Advisor</th> : null}
                    <th>Trạng thái</th>
                    <th>Tin nhắn cuối</th>
                    <th>Cập nhật</th>
                    <th>
                      <span className="sr-only">Hành động</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const { time, date } = formatDateTime(row.lastActivityAt);
                    const shortId = scope === "mine" && row.id.length > 12 ? `${row.id.slice(0, 8)}…` : row.id;
                    return (
                      <tr
                        className={[row.isLive ? "is-live" : "", selectedId === row.id ? "is-selected" : ""].join(" ").trim() || undefined}
                        key={row.id}
                        onClick={canPreview ? () => setSelectedId(row.id) : undefined}
                      >
                        <td data-label="Mã phiên">
                          <div className="session-id-row">
                            <strong className="mono-text" title={row.id}>
                              {shortId}
                            </strong>
                            {row.isLive ? <span className="live-pill">Trực tiếp</span> : null}
                          </div>
                        </td>
                        <td data-label="Khách hàng">
                          {row.isLive ? (
                            <strong>{row.customerName}</strong>
                          ) : (
                            <Link className="customer-profile-link" href={customerProfileHref(row.customerId, scope === "all" ? "admin" : "advisor")}>
                              <strong>{row.customerName}</strong>
                            </Link>
                          )}
                          <small title={row.customerSub}>{row.needSummary ?? row.customerSub}</small>
                          {row.heatBand || row.bottlenecks.length ? (
                            <span className="chat-row-chips">
                              {row.heatBand ? (
                                <StatusBadge tone={HEAT_BAND_BADGES[row.heatBand].tone}>{HEAT_BAND_BADGES[row.heatBand].label}</StatusBadge>
                              ) : null}
                              {row.bottlenecks.map((code) => (
                                <StatusBadge key={code} tone="neutral">
                                  {bottleneckLabel(code)}
                                </StatusBadge>
                              ))}
                            </span>
                          ) : null}
                        </td>
                        {scope === "all" ? (
                          <td data-label="Advisor">{row.advisorId ? <strong>{row.advisorId}</strong> : <small>Chưa phân công</small>}</td>
                        ) : null}
                        <td data-label="Trạng thái">
                          <StatusBadge tone={STATUS_TONES[row.status]}>
                            {row.status === "WAITING_ADVISOR" ? copy.waitingStatus : row.status === "CLOSED" ? "Đã đóng" : "Đang hoạt động"}
                          </StatusBadge>
                        </td>
                        <td data-label="Tin nhắn cuối">
                          {row.lastMessagePreview ? <small title={row.lastMessagePreview}>{row.lastMessagePreview}</small> : <small>—</small>}
                        </td>
                        <td data-label="Cập nhật">
                          <strong>{time}</strong>
                          {date ? <small>{date}</small> : null}
                        </td>
                        <td onClick={(event) => event.stopPropagation()}>
                          <div className="chat-row-actions">
                            <Link className="table-action" href={detailHref(row.id)}>
                              {scope === "all" ? "Xem trace" : row.status === "CLOSED" ? "Xem lại" : "Vào chat"} <ChevronRight size={14} />
                            </Link>
                            {scope === "mine" && row.status !== "CLOSED" ? (
                              <button className="secondary-button" onClick={() => setToClose(row)} title="Đóng phiên tư vấn" type="button">
                                <X size={13} />
                                <span>Đóng</span>
                              </button>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {canPreview && selectedId ? (
              <aside aria-label="Xem nhanh phiên" className="chat-session-preview">
                <header>
                  <span className="mono-text">#{selectedId.slice(0, 8)}</span>
                  <span>{preview?.customer_display || preview?.customer_id || "Đang tải..."}</span>
                  <Link href={`/advisor/conversations/${selectedId}`} title="Mở toàn màn hình">
                    <Maximize2 size={15} />
                  </Link>
                  <button onClick={() => setSelectedId(null)} title="Đóng xem nhanh" type="button">
                    <PanelRightClose size={15} />
                  </button>
                </header>
                <div className="chat-session-preview-body">
                  {previewLoading ? (
                    <p>Đang nạp hội thoại...</p>
                  ) : preview ? (
                    preview.messages?.length ? (
                      preview.messages.map((message, index) => (
                        <div className={`preview-message is-${message.sender_type.toLowerCase()}`} key={message.message_id || index}>
                          <small>{message.sender_type === "ADVISOR" ? "Bạn (TVV)" : message.sender_type === "CUSTOMER" ? "Khách hàng" : "Trợ lý AI"}</small>
                          <p>{message.content}</p>
                        </div>
                      ))
                    ) : (
                      <p>Chưa có tin nhắn trong phiên này.</p>
                    )
                  ) : (
                    <p>Không tải được thông tin phiên.</p>
                  )}
                </div>
                <footer>
                  <Link className="primary-button" href={`/advisor/conversations/${selectedId}`}>
                    Mở phòng chat <ExternalLink size={13} />
                  </Link>
                </footer>
              </aside>
            ) : null}
          </div>
        ) : null}

        {filtered.length > PAGE_SIZE ? (
          <div className="chat-session-pagination">
            <span>
              {(currentPage - 1) * PAGE_SIZE + 1}–{Math.min(currentPage * PAGE_SIZE, filtered.length)} / {filtered.length} phiên
            </span>
            <button disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)} title="Trang trước" type="button">
              <ChevronLeft size={15} />
            </button>
            <span>
              {currentPage} / {totalPages}
            </span>
            <button disabled={currentPage === totalPages} onClick={() => setPage(currentPage + 1)} title="Trang tiếp theo" type="button">
              <ChevronRight size={15} />
            </button>
          </div>
        ) : null}
      </section>

      {toClose ? (
        <div className="chat-confirm-backdrop" role="presentation">
          <section aria-labelledby="end-chat-title" aria-modal="true" className="chat-confirm-dialog" role="dialog">
            <button aria-label="Huỷ đóng phiên" className="chat-confirm-close" onClick={() => setToClose(null)} type="button">
              <X size={18} />
            </button>
            <span className="eyebrow">
              <AlertCircle size={14} /> Đóng phiên tư vấn
            </span>
            <h2 id="end-chat-title">Đóng phiên tư vấn này?</h2>
            <p>
              Bạn có chắc muốn kết thúc phiên tư vấn cho khách hàng (<strong>{toClose.customerName}</strong>)? Bạn vẫn có thể xem lại toàn bộ lịch sử sau khi đóng.
            </p>
            <div className="chat-confirm-actions">
              <button className="secondary-button" disabled={closing} onClick={() => setToClose(null)} type="button">
                Huỷ
              </button>
              <button className="primary-button" disabled={closing} onClick={() => void confirmClose()} type="button">
                {closing ? "Đang đóng..." : "Xác nhận kết thúc"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
