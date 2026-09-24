"use client";

import { Eye, LogIn, RefreshCw, Search, ShieldAlert, UserCheck } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { customerProfileHref } from "@/components/customer360/profile-links";
import { StatusBadge } from "@/components/shared/status-badge";
import { type AssignedCustomerItem, fetchAdvisorCustomers } from "@/lib/api/assignments";
import { listUsers, type UserSummary } from "@/lib/api/auth";
import { useAuth } from "@/store/auth-store";

export function AdvisorCustomers() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const isAdvisor = user?.role === "advisor";
  const isStaff = isAdmin || isAdvisor;

  const [customers, setCustomers] = useState<AssignedCustomerItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [advisors, setAdvisors] = useState<readonly UserSummary[]>([]);
  const [selectedAdvisorFilter, setSelectedAdvisorFilter] = useState<string>("");

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

  // Danh sách khách chưa kèm slot (backend chỉ trả tên/SĐT đã che/email) — nhu cầu đầy đủ
  // nằm ở trang hồ sơ; ở đây chỉ hiện ghi chú phân công.
  function getNeedSummary(item: AssignedCustomerItem): string {
    return item.reason || "Mở hồ sơ để xem nhu cầu";
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
            <Link className="primary-button text-xs py-1.5 px-3" href="/staff-login">
              <LogIn size={14} /> Đăng nhập nhân sự
            </Link>
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
              <Link
                className="secondary-button full-button"
                href={customerProfileHref(customer.customer_id, isAdmin ? "admin" : "advisor")}
              >
                <Eye size={16} /> Xem hồ sơ & lịch sử
              </Link>
            </article>
          ))}
        </div>
      </section>

    </>
  );
}
