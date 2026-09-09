"use client";

import { CheckCircle2, LockKeyhole, MoreHorizontal, Plus, RefreshCw, Search, UserRoundCheck, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type { MouseEvent } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import {
  activateUser,
  changeUserRole,
  createStaff,
  disableUser,
  enableUser,
  listUsers,
  type UserSummary,
} from "@/lib/api/auth";

type RoleFilter = "all" | UserSummary["role"];
type Dialog = "create" | "detail" | null;
type StaffRole = Extract<UserSummary["role"], "advisor" | "admin">;
type DisableableState = Exclude<UserSummary["state"], "disabled">;

type StatusMeta = {
  readonly label: string;
  readonly tone: "neutral" | "info" | "success" | "warning" | "danger";
};

const roleLabels: Record<UserSummary["role"], string> = {
  customer: "Khách hàng",
  advisor: "Tư vấn viên",
  admin: "Admin",
};
const statusMeta: Record<UserSummary["state"], StatusMeta> = {
  active: { label: "Hoạt động", tone: "success" },
  pending_verification: { label: "Chờ xác nhận", tone: "warning" },
  temporary_password: { label: "Mật khẩu tạm", tone: "info" },
  disabled: { label: "Đã khoá", tone: "danger" },
};
const roleFilters: readonly RoleFilter[] = ["all", "customer", "advisor", "admin"];
const disableableStates: readonly DisableableState[] = ["active", "pending_verification", "temporary_password"];

function parseStaffRole(value: string): StaffRole {
  return value === "admin" ? "admin" : "advisor";
}

function isDisableableState(state: UserSummary["state"]): state is DisableableState {
  return disableableStates.some((value) => value === state);
}

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function UserManagementPreview() {
  const [filter, setFilter] = useState<RoleFilter>("all");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [users, setUsers] = useState<readonly UserSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<UserSummary | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);
  const [staffRole, setStaffRole] = useState<StaffRole>("advisor");
  const pageSize = 20;
  const requestSequence = useRef(0);
  const modalRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLButtonElement | null>(null);
  const pageCount = Math.max(1, Math.ceil(total / pageSize));

  const reload = useCallback(async (isPolling = false) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    if (!isPolling) setLoading(true);
    setLoadError(null);
    try {
      const result = await listUsers({ role: filter === "all" ? undefined : filter, q: query.trim() || undefined, page, pageSize });
      if (sequence !== requestSequence.current) return;
      setUsers(result.items);
      setTotal(result.total);
    } catch {
      if (sequence !== requestSequence.current) return;
      if (!isPolling) setLoadError("Không tải được danh sách người dùng.");
    } finally {
      if (sequence === requestSequence.current && !isPolling) setLoading(false);
    }
  }, [filter, page, query]);

  useEffect(() => {
    void reload();
    const timer = setInterval(() => {
      void reload(true);
    }, 4000);
    return () => clearInterval(timer);
  }, [reload]);

  function closeDialog(): void {
    setDialog(null);
    returnFocusRef.current?.focus();
    returnFocusRef.current = null;
  }

  useEffect(() => {
    if (!dialog) return;
    const modal = modalRef.current;
    if (!modal) return;
    const focusable = Array.from(modal.querySelectorAll<HTMLElement>("button, input, select, textarea, [tabindex]:not([tabindex='-1'])"));
    focusable[0]?.focus();
    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeDialog();
        return;
      }
      if (event.key !== "Tab" || focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [dialog]);

  function selectRole(nextRole: RoleFilter): void {
    setFilter(nextRole);
    setPage(1);
  }

  function openDetail(user: UserSummary, event: MouseEvent<HTMLButtonElement>): void {
    returnFocusRef.current = event.currentTarget;
    setSelected(user);
    setDialog("detail");
  }

  function openCreate(event: MouseEvent<HTMLButtonElement>): void {
    returnFocusRef.current = event.currentTarget;
    setEmail("");
    setEmailError(null);
    setStaffRole("advisor");
    setDialog("create");
  }

  function validateEmail(value: string): string | null {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim()) ? null : "Vui lòng nhập email hợp lệ.";
  }

  async function submitCreate(): Promise<void> {
    const normalizedEmail = email.trim();
    const validationError = validateEmail(normalizedEmail);
    setEmailError(validationError);
    if (validationError) return;
    setSaving(true);
    try {
      await createStaff(normalizedEmail, staffRole);
      closeDialog();
      await reload();
    } catch {
      setLoadError("Không tạo được tài khoản nhân sự.");
    } finally {
      setSaving(false);
    }
  }

  async function updateRole(role: StaffRole): Promise<void> {
    if (!selected || selected.role === role) return;
    setSaving(true);
    try {
      await changeUserRole(selected.id, role);
      closeDialog();
      await reload();
    } catch {
      setLoadError("Không cập nhật được vai trò người dùng.");
    } finally {
      setSaving(false);
    }
  }

  async function handleActivate(user: UserSummary): Promise<void> {
    setSaving(true);
    try {
      await activateUser(user.id);
      closeDialog();
      await reload();
    } catch {
      setLoadError("Không xác nhận kích hoạt được tài khoản.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleStatus(user: UserSummary): Promise<void> {
    if (user.state === "disabled") {
      setSaving(true);
      try {
        await enableUser(user.id);
        closeDialog();
        await reload();
      } catch {
        setLoadError("Không mở khoá được người dùng.");
      } finally {
        setSaving(false);
      }
      return;
    }
    if (!isDisableableState(user.state)) {
      setLoadError("Tài khoản đang ở trạng thái không thể khoá.");
      return;
    }
    if (!window.confirm(`Khoá tài khoản ${user.email}?`)) return;
    setSaving(true);
    try {
      await disableUser(user.id);
      closeDialog();
      await reload();
    } catch {
      setLoadError("Không khoá được người dùng.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="ops-panel">
        <div className="ops-panel-heading">
          <div><h2>Danh sách người dùng</h2><p>Phân quyền CUSTOMER / ADVISOR / ADMIN</p></div>
          <button className="primary-button" onClick={openCreate} type="button"><Plus size={17} /> Thêm người dùng</button>
        </div>
        <div className="user-table-tools">
          <div className="catalog-filter-tabs">
            {roleFilters.map((role) => <button className={filter === role ? "is-active" : ""} key={role} onClick={() => selectRole(role)} type="button">{role === "all" ? "Tất cả" : roleLabels[role]}</button>)}
          </div>
          <div className="flex items-center gap-2">
            <label className="ops-search"><Search size={16} /><span className="sr-only">Tìm người dùng</span><input onChange={(event) => { setQuery(event.target.value); setPage(1); }} placeholder="Email người dùng..." value={query} /></label>
            <button className="secondary-button" onClick={() => void reload()} title="Làm mới danh sách" type="button"><RefreshCw className={loading ? "animate-spin" : ""} size={15} /> Làm mới</button>
          </div>
        </div>
        {loading ? <p className="catalog-result-note">Đang tải danh sách người dùng...</p> : null}
        {loadError ? <p className="catalog-result-note" role="alert">{loadError} <button className="table-action" onClick={() => void reload()} type="button">Thử lại</button></p> : null}
        {!loading && !loadError && users.length === 0 ? <p className="catalog-result-note">Không có người dùng phù hợp.</p> : null}
        <div className="catalog-table-wrap">
          <table className="catalog-table">
            <thead><tr><th>Người dùng</th><th>Vai trò</th><th>Trạng thái</th><th>Hoạt động cuối</th><th>Hành động</th></tr></thead>
            <tbody>
              {users.map((user) => {
                const meta = statusMeta[user.state];
                return (
                  <tr key={user.id}>
                    <td><strong>{user.email}</strong><small>ID: {user.id}</small></td>
                    <td>{roleLabels[user.role]}</td>
                    <td>
                      <StatusBadge tone={meta.tone}>
                        {user.state === "disabled" ? <LockKeyhole size={13} /> : <UserRoundCheck size={13} />}
                        {meta.label}
                      </StatusBadge>
                    </td>
                    <td>{formatDate(user.last_activity_at)}</td>
                    <td>
                      <div className="flex items-center gap-2">
                        {user.state === "pending_verification" ? (
                          <button
                            className="px-2.5 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-300 rounded-lg text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer shadow-xs"
                            disabled={saving}
                            onClick={() => void handleActivate(user)}
                            type="button"
                            title="Xác nhận kích hoạt tài khoản"
                          >
                            <CheckCircle2 size={13} /> Xác nhận
                          </button>
                        ) : null}
                        <button className="table-action" onClick={(event) => openDetail(user, event)} type="button">
                          <MoreHorizontal size={17} /> Chi tiết
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {pageCount > 1 ? <nav aria-label="Phân trang người dùng" className="catalog-next-actions"><span aria-current="page">Trang {page} / {pageCount} · {total} người dùng</span><div><button aria-label="Trang trước" className="secondary-button" disabled={page === 1} onClick={() => setPage((current) => current - 1)} type="button">Trước</button><button aria-label="Trang sau" className="secondary-button" disabled={page === pageCount} onClick={() => setPage((current) => current + 1)} type="button">Sau</button></div></nav> : null}
      </section>
      {dialog ? (
        <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="user-dialog-title">
          <button className="dialog-backdrop" aria-label="Đóng hộp thoại" onClick={closeDialog} type="button" />
          <section className="mock-dialog" ref={modalRef}>
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">Auth user management</span>
                <h2 id="user-dialog-title">{dialog === "create" ? "Thêm người dùng" : selected?.email}</h2>
              </div>
              <button className="icon-button" onClick={closeDialog} aria-label="Đóng" type="button"><X size={19} /></button>
            </div>
            {dialog === "create" ? (
              <>
                <label className="field-label">Email
                  <input
                    aria-describedby={emailError ? "user-email-error" : undefined}
                    aria-invalid={emailError ? "true" : "false"}
                    onChange={(event) => { setEmail(event.target.value); setEmailError(validateEmail(event.target.value)); }}
                    placeholder="name@example.com"
                    type="email"
                    value={email}
                  />
                  {emailError ? <span id="user-email-error" role="alert">{emailError}</span> : null}
                </label>
                <label className="field-label">Vai trò
                  <select onChange={(event) => setStaffRole(parseStaffRole(event.target.value))} value={staffRole}>
                    <option value="advisor">Tư vấn viên</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </>
            ) : selected ? (
              <>
                <div className="customer-contact-summary">
                  <span className="ops-avatar large">{selected.email.slice(0, 2).toUpperCase()}</span>
                  <div><strong>{selected.email}</strong><span>ID: {selected.id}</span></div>
                </div>
                <div className="vehicle-detail-grid">
                  <div><span>Vai trò</span><strong>{roleLabels[selected.role]}</strong></div>
                  <div><span>Trạng thái</span><strong>{statusMeta[selected.state].label}</strong></div>
                  <div><span>Hoạt động cuối</span><strong>{formatDate(selected.last_activity_at)}</strong></div>
                  <div><span>Tạo lúc</span><strong>{formatDate(selected.created_at)}</strong></div>
                </div>
                <label className="field-label">Đổi vai trò
                  <select
                    defaultValue={selected.role === "customer" ? "advisor" : selected.role}
                    disabled={selected.role === "customer" || saving}
                    onChange={(event) => void updateRole(parseStaffRole(event.target.value))}
                  >
                    <option value="advisor">Tư vấn viên</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </>
            ) : null}
            <div className="dialog-actions">
              <button className="secondary-button" onClick={closeDialog} type="button">Đóng</button>
              {dialog === "create" ? (
                <button
                  className="primary-button"
                  disabled={saving || Boolean(emailError) || !email.trim()}
                  onClick={() => void submitCreate()}
                  type="button"
                >
                  {saving ? "Đang tạo..." : "Tạo tài khoản"}
                </button>
              ) : selected ? (
                <div className="flex items-center gap-2">
                  {selected.state === "pending_verification" ? (
                    <button
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                      disabled={saving}
                      onClick={() => void handleActivate(selected)}
                      type="button"
                    >
                      <CheckCircle2 size={15} /> {saving ? "Đang xử lý..." : "Xác nhận kích hoạt"}
                    </button>
                  ) : null}
                  <button
                    className={selected.state === "disabled" ? "primary-button" : "danger-button"}
                    disabled={saving}
                    onClick={() => void toggleStatus(selected)}
                    type="button"
                  >
                    {saving ? "Đang cập nhật..." : selected.state === "disabled" ? "Mở khoá" : "Khoá tài khoản"}
                  </button>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}
