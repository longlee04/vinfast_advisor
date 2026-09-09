"use client";

import { CalendarCheck2, ExternalLink, Eye, Loader2, LogIn, MessageSquareText, RefreshCw, Search, ShieldAlert, UserCheck, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { type AdvisorConversationDetail, listAdvisorConversations } from "@/lib/api/agent";
import { type AssignedCustomerItem, fetchAdvisorCustomers } from "@/lib/api/assignments";
import { listUsers, type UserSummary } from "@/lib/api/auth";
import { useAuth } from "@/store/auth-store";

export function AdvisorCustomers() {
  const { user, login } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdvisor = user?.role === "advisor";
  const isStaff = isAdmin || isAdvisor;

  const [customers, setCustomers] = useState<AssignedCustomerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<AssignedCustomerItem | null>(null);
  const [customerSessions, setCustomerSessions] = useState<readonly AdvisorConversationDetail[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [advisors, setAdvisors] = useState<readonly UserSummary[]>([]);
  const [selectedAdvisorFilter, setSelectedAdvisorFilter] = useState<string>("");

  useEffect(() => {
    if (!selected) {
      setCustomerSessions([]);
      return;
    }
    setLoadingSessions(true);
    listAdvisorConversations(selected.customer_id)
      .then((res) => setCustomerSessions(res.items || []))
      .catch(() => setCustomerSessions([]))
      .finally(() => setLoadingSessions(false));
  }, [selected]);

  const reload = useCallback(async (targetAdvisor?: string) => {
    setLoading(true);
    setLoadError(null);
    try {
      const advParam = targetAdvisor ?? (selectedAdvisorFilter || undefined);
      const res = await fetchAdvisorCustomers(advParam);
      setCustomers(res.items || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401") || msg.includes("authentication required")) {
        setLoadError("Chưa đăng nhập tài khoản Tư vấn viên để truy vấn Database.");
      } else {
        setLoadError("Không thể tải danh sách khách hàng từ Database.");
      }
      setCustomers([]);
    } finally {
      setLoading(false);
    }
  }, [selectedAdvisorFilter]);

  useEffect(() => {
    void reload();
    listUsers({ role: "advisor", pageSize: 100 })
      .then((res) => setAdvisors(res.items || []))
      .catch(() => setAdvisors([]));
  }, [reload, user]);

  async function handleQuickAdvisorLogin(email: string) {
    setLoading(true);
    try {
      await login(email, "Admin@123456");
      await reload();
    } catch {
      setLoadError("Đăng nhập TVV thất bại.");
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    const q = query.toLowerCase().trim();
    if (!q) return customers;
    return customers.filter((c) => {
      const name = String(c.profile_payload?.name ?? c.customer_id).toLowerCase();
      const phone = String(c.profile_payload?.phone ?? "").toLowerCase();
      const email = String(c.profile_payload?.email ?? "").toLowerCase();
      return name.includes(q) || phone.includes(q) || email.includes(q) || c.customer_id.toLowerCase().includes(q);
    });
  }, [customers, query]);

  function formatDate(val: string | null | undefined): string {
    if (!val) return "—";
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(val));
  }

  function getDisplayName(item: AssignedCustomerItem): string {
    return (item.profile_payload?.name as string) || (item.profile_payload?.display_name as string) || item.customer_id;
  }

  function getAvatar(item: AssignedCustomerItem): string {
    const name = getDisplayName(item);
    const words = name.trim().split(" ");
    if (words.length >= 2) {
      return (words[0][0] + words[words.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }

  function getNeedSummary(item: AssignedCustomerItem): string {
    const budget = item.profile_payload?.budget_vnd;
    const model = item.profile_payload?.model_name || item.profile_payload?.vehicle_type;
    const usage = item.profile_payload?.usage_purpose;
    const parts = [];
    if (model) parts.push(`Mẫu quan tâm: ${model}`);
    if (budget) parts.push(`Ngân sách: ${Number(budget).toLocaleString("vi-VN")} đ`);
    if (usage) parts.push(`Mục đích: ${usage}`);
    return parts.length > 0 ? parts.join(" · ") : (item.reason || "Khách hàng phân công từ Admin Assignment Center");
  }

  return (
    <>
      <section className="ops-panel">
        <div className="ops-panel-heading">
          <div>
            <h2>Khách hàng được phân công</h2>
            <p>
              {isAdvisor
                ? `Danh sách khách hàng đang được phân công cho ${user?.email}`
                : "Danh sách khách hàng do Admin chỉ định hoặc tiếp quản chăm sóc trực tiếp (PostgreSQL)"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {isAdmin && advisors.length > 0 ? (
              <label className="text-xs text-slate-600 flex items-center gap-1.5 font-medium">
                Xem theo TVV:
                <select
                  className="p-1 border border-slate-300 rounded text-xs"
                  onChange={(e) => {
                    setSelectedAdvisorFilter(e.target.value);
                    void reload(e.target.value || undefined);
                  }}
                  value={selectedAdvisorFilter}
                >
                  <option value="">-- Mọi phân công / TVV hiện tại --</option>
                  {advisors.map((adv) => (
                    <option key={adv.id} value={adv.email || adv.id}>
                      {adv.email} ({adv.id})
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <label className="ops-search">
              <Search size={16} />
              <span className="sr-only">Tìm khách hàng</span>
              <input
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Tìm theo tên, ID, SĐT..."
                value={query}
              />
            </label>
            <button className="secondary-button" onClick={() => void reload()} title="Làm mới" type="button">
              <RefreshCw className={loading ? "animate-spin" : ""} size={15} /> Làm mới ({customers.length})
            </button>
          </div>
        </div>

        {!isStaff ? (
          <div className="mx-4 my-3 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-900 text-sm">
              <ShieldAlert size={18} className="text-amber-600 shrink-0" />
              <span>
                Bạn chưa đăng nhập quyền <strong>Tư vấn viên (Advisor)</strong>. Hãy đăng nhập để xem khách hàng được phân công.
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                className="primary-button text-xs py-1.5 px-3"
                onClick={() => void handleQuickAdvisorLogin("advisor@gmail.com")}
                type="button"
              >
                <LogIn size={14} /> Đăng nhập TVV (advisor@gmail.com)
              </button>
            </div>
          </div>
        ) : null}

        {loading ? <p className="catalog-result-note">Đang truy vấn danh sách khách hàng từ Database...</p> : null}
        {loadError ? <p className="catalog-result-note text-red-600" role="alert">{loadError}</p> : null}
        {!loading && !loadError && filtered.length === 0 ? (
          <p className="catalog-result-note">Chưa có khách hàng nào được phân công cho tài khoản này trong Database.</p>
        ) : null}

        <div className="advisor-customer-grid">
          {filtered.map((customer) => (
            <article key={customer.customer_id}>
              <div className="customer-card-top">
                <span className="ops-avatar">{getAvatar(customer)}</span>
                <StatusBadge tone="success">
                  <UserCheck size={12} /> Đang phụ trách
                </StatusBadge>
              </div>
              <h3>{getDisplayName(customer)}</h3>
              <p className="text-xs text-slate-500 font-mono">ID: {customer.customer_id}</p>
              <div className="customer-need-box">{getNeedSummary(customer)}</div>
              <dl>
                <div>
                  <dt>Phiên tư vấn</dt>
                  <dd>{customer.active_conversations_count} phiên</dd>
                </div>
                <div>
                  <dt>Gán lúc</dt>
                  <dd>{formatDate(customer.assigned_at)}</dd>
                </div>
              </dl>
              <button
                className="secondary-button full-button"
                onClick={() => setSelected(customer)}
                type="button"
              >
                <Eye size={16} /> Xem hồ sơ & lịch sử
              </button>
            </article>
          ))}
        </div>
      </section>

      {selected ? (
        <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="customer-detail-title">
          <button className="dialog-backdrop" aria-label="Đóng hồ sơ" onClick={() => setSelected(null)} type="button" />
          <section className="mock-dialog">
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">Hồ sơ được phân công</span>
                <h2 id="customer-detail-title">{getDisplayName(selected)}</h2>
              </div>
              <button className="icon-button" onClick={() => setSelected(null)} aria-label="Đóng" type="button">
                <X size={19} />
              </button>
            </div>
            <div className="customer-contact-summary">
              <span className="ops-avatar large">{getAvatar(selected)}</span>
              <div>
                <strong>{getDisplayName(selected)}</strong>
                <span>ID: {selected.customer_id} · Phụ trách: {selected.advisor_id}</span>
              </div>
            </div>
            <div className="need-summary-grid">
              <div>
                <span>Nhu cầu</span>
                <strong>{getNeedSummary(selected)}</strong>
              </div>
              <div>
                <span>Số phiên</span>
                <strong>{selected.active_conversations_count} phiên</strong>
              </div>
              <div>
                <span>Phân công lúc</span>
                <strong>{formatDate(selected.assigned_at)}</strong>
              </div>
            </div>
            {selected.reason ? (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700">
                Ghi chú điều chuyển: <strong>{selected.reason}</strong>
              </div>
            ) : null}
            <div className="mini-activity-list">
              <article>
                <MessageSquareText size={17} />
                <div>
                  <strong>Tổng số phiên tư vấn</strong>
                  <small>{selected.active_conversations_count} cuộc hội thoại đã thực hiện</small>
                </div>
              </article>
              <article>
                <CalendarCheck2 size={17} />
                <div>
                  <strong>Hoạt động gần nhất</strong>
                  <small>{formatDate(selected.last_activity_at)}</small>
                </div>
              </article>
            </div>

            <div className="customer-conversations-section mt-4 pt-4 border-t border-slate-200">
              <h4 className="text-xs font-semibold uppercase text-slate-500 mb-2 tracking-wider flex items-center justify-between">
                <span>Danh sách phiên chat ({customerSessions.length})</span>
                {loadingSessions ? <Loader2 size={13} className="animate-spin text-slate-400" /> : null}
              </h4>
              {customerSessions.length === 0 && !loadingSessions ? (
                <p className="text-xs text-slate-500 italic py-2">Chưa có phiên chat nào từ khách hàng này.</p>
              ) : null}
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {customerSessions.map((conv) => {
                  const isClosed = conv.status === "COMPLETED" || conv.status === "CLOSED";
                  const isWaiting = conv.status === "WAITING_ADVISOR";
                  return (
                    <div
                      key={conv.conversation_id}
                      className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-semibold text-slate-800">
                            #{conv.conversation_id.slice(0, 8)}
                          </span>
                          <StatusBadge tone={isClosed ? "neutral" : isWaiting ? "warning" : "success"}>
                            {isClosed ? "Đã đóng" : isWaiting ? "Chờ Advisor" : "Đang hoạt động"}
                          </StatusBadge>
                        </div>
                        <p className="text-[11px] text-slate-500 truncate max-w-[240px] mt-0.5" title={conv.last_message_preview}>
                          {conv.last_message_preview || "Phiên hội thoại"}
                        </p>
                      </div>
                      <Link
                        href={`/advisor/conversations/${conv.conversation_id}`}
                        className="secondary-button text-xs py-1 px-2.5 shrink-0 inline-flex items-center gap-1"
                      >
                        <ExternalLink size={12} /> {isClosed ? "Xem lại" : "Mở chat"}
                      </Link>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="dialog-actions">
              <button className="secondary-button" onClick={() => setSelected(null)} type="button">
                Đóng
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
