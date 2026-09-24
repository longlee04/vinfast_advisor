"use client";

import { CheckCircle2, History, LogIn, RefreshCw, ShieldAlert, UserCheck, UserMinus, UserPlus, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { CustomerPicker } from "@/components/customer360/customer-picker";
import { HEAT_BAND_BADGES } from "@/components/customer360/customer360-labels";
import { customerProfileHref } from "@/components/customer360/profile-links";
import { StatusBadge } from "@/components/shared/status-badge";
import { type CustomerPickerItem, fetchCustomerPicker } from "@/lib/api/agent";
import {
  type AssignmentHistoryItem,
  type CustomerAssignment,
  assignCustomer,
  fetchAssignmentHistory,
  fetchAssignments,
  fetchAvailableCustomers,
  unassignCustomer,
} from "@/lib/api/assignments";
import { listUsers, type UserSummary } from "@/lib/api/auth";
import { useAuth } from "@/store/auth-store";

export function AssignmentCenter() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [assignments, setAssignments] = useState<CustomerAssignment[]>([]);
  const [total, setTotal] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("ACTIVE");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [availableCustomers, setAvailableCustomers] = useState<
    Array<{ customer_id: string; display_name: string; phone?: string; email?: string }>
  >([]);
  const [advisors, setAdvisors] = useState<readonly UserSummary[]>([]);

  const [dialog, setDialog] = useState<"assign" | "history" | null>(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>("");
  /** Khách nóng chưa ai phụ trách — gợi ý phân công trước (plan §2.6). */
  const [hotUnassigned, setHotUnassigned] = useState<readonly CustomerPickerItem[]>([]);
  const [selectedAdvisorId, setSelectedAdvisorId] = useState<string>("");
  const [targetAdvisorId, setTargetAdvisorId] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [historyItems, setHistoryItems] = useState<AssignmentHistoryItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [actionSuccessMessage, setActionSuccessMessage] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetchAssignments({
        status: statusFilter === "ALL" ? undefined : statusFilter,
        page: 1,
        pageSize: 50,
      });
      setAssignments(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      if (errMsg.includes("401") || errMsg.includes("authentication required")) {
        setLoadError("Chưa đăng nhập quyền Admin để truy vấn Database.");
      } else {
        setLoadError("Không thể tải danh sách phân công từ Database.");
      }
      setAssignments([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  const loadDependencies = useCallback(async () => {
    try {
      const [customersRes, advisorsRes] = await Promise.all([
        fetchAvailableCustomers().catch(() => []),
        listUsers({ role: "advisor", pageSize: 100 }).catch(() => ({ items: [] as UserSummary[], total: 0 })),
      ]);
      setAvailableCustomers(customersRes);
      setAdvisors(advisorsRes.items);
      const picked = await fetchCustomerPicker("", 50).catch(() => [] as readonly CustomerPickerItem[]);
      setHotUnassigned(picked.filter((item) => item.heat_band === "HOT" && !item.advisor_id).slice(0, 5));
    } catch {
      // Ignored if unauthenticated
    }
  }, []);

  useEffect(() => {
    void reload();
    void loadDependencies();
  }, [reload, loadDependencies, user]);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("customer");
    if (!requested) return;
    const current = assignments.find((item) => item.customer_id === requested && item.status === "ACTIVE");
    setSelectedCustomerId(requested);
    setSelectedAdvisorId(current?.advisor_id ?? "");
    setDialog("assign");
    // Chỉ một lần khi trang mở từ hồ sơ khách.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openAssignModal(customerId: string, currentAdvisorId?: string) {
    setSelectedCustomerId(customerId || "");
    setSelectedAdvisorId(currentAdvisorId || "");
    const initialTarget = currentAdvisorId || advisors[0]?.email || advisors[0]?.id || "";
    setTargetAdvisorId(initialTarget);
    setReason("");
    setActionSuccessMessage(null);
    setDialog("assign");
  }

  async function openHistoryModal(customerId: string) {
    setSelectedCustomerId(customerId);
    setSaving(true);
    setDialog("history");
    try {
      const res = await fetchAssignmentHistory(customerId);
      setHistoryItems(res.items || []);
    } catch {
      setHistoryItems([]);
    } finally {
      setSaving(false);
    }
  }

  async function handleAssignSubmit() {
    const finalCustomerId = selectedCustomerId.trim();
    const finalAdvisorId = targetAdvisorId.trim();
    if (!finalCustomerId || !finalAdvisorId) return;

    setSaving(true);
    setActionSuccessMessage(null);

    try {
      await assignCustomer(finalCustomerId, finalAdvisorId, reason.trim() || undefined);
      setDialog(null);
      setActionSuccessMessage(`Đã phân công thành công khách hàng "${finalCustomerId}" cho tư vấn viên "${finalAdvisorId}" vào Database!`);
      await reload();
      await loadDependencies();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi phân công: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleUnassign(customerId: string) {
    if (!window.confirm(`Xác nhận hủy phân công khách hàng ${customerId} trên Database?`)) return;
    setSaving(true);
    try {
      await unassignCustomer(customerId, "Admin manual unassignment");
      setActionSuccessMessage(`Đã hủy phân công khách hàng "${customerId}" trên Database.`);
      await reload();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Lỗi hủy phân công: ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  function formatDate(val: string | null | undefined): string {
    if (!val) return "—";
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(val));
  }

  return (
    <>
      <section className="ops-panel">
        <div className="ops-panel-heading">
          <div>
            <h2>Trung tâm Phân công Khách hàng (Assignment Center)</h2>
            <p>Điều phối quan hệ chăm sóc giữa Khách hàng và Tư vấn viên (Dữ liệu PostgreSQL trực tiếp)</p>
          </div>
          <div className="flex items-center gap-3">
            {isAdmin ? (
              <span className="status-badge status-success">
                <CheckCircle2 size={13} /> Quyền Admin ({user?.email})
              </span>
            ) : null}
            <button className="primary-button" disabled={!isAdmin} onClick={() => openAssignModal("")} type="button">
              <UserPlus size={17} /> Phân công khách hàng
            </button>
          </div>
        </div>

        {!isAdmin ? (
          <div className="mx-4 my-3 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-900 text-sm">
              <ShieldAlert size={18} className="text-amber-600 shrink-0" />
              <span>
                Bạn chưa đăng nhập quyền <strong>Quản trị viên (Admin)</strong>. Hãy đăng nhập để truy cập dữ liệu Database thực tế.
              </span>
            </div>
            <Link className="primary-button text-xs py-1.5 px-3" href="/staff-login">
              <LogIn size={14} /> Đăng nhập nhân sự
            </Link>
          </div>
        ) : null}

        {hotUnassigned.length ? (
          <div className="hot-unassigned" role="region" aria-label="Khách nóng chưa phân công">
            <strong>Khách nóng chưa có tư vấn viên</strong>
            <ul>
              {hotUnassigned.map((item) => (
                <li key={item.customer_id}>
                  <Link href={customerProfileHref(item.customer_id, "admin")}>{item.display_name || item.customer_id}</Link>
                  <StatusBadge tone={HEAT_BAND_BADGES.HOT.tone}>{`Nóng · ${item.heat_score ?? 0}`}</StatusBadge>
                  <button className="text-button" disabled={!isAdmin} onClick={() => void openAssignModal(item.customer_id)} type="button">
                    Phân công
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {actionSuccessMessage ? (
          <div className="mx-4 my-3 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-medium">
              <CheckCircle2 size={15} className="text-emerald-600" /> {actionSuccessMessage}
            </span>
            <button className="text-emerald-700 hover:text-emerald-900 font-bold" onClick={() => setActionSuccessMessage(null)} type="button">
              ✕
            </button>
          </div>
        ) : null}

        <div className="user-table-tools">
          <div className="catalog-filter-tabs">
            <button className={statusFilter === "ACTIVE" ? "is-active" : ""} onClick={() => setStatusFilter("ACTIVE")} type="button">
              Đang phụ trách (Active)
            </button>
            <button className={statusFilter === "TRANSFERRED" ? "is-active" : ""} onClick={() => setStatusFilter("TRANSFERRED")} type="button">
              Đã chuyển giao (Transferred)
            </button>
            <button className={statusFilter === "UNASSIGNED" ? "is-active" : ""} onClick={() => setStatusFilter("UNASSIGNED")} type="button">
              Đã hủy gán (Unassigned)
            </button>
            <button className={statusFilter === "ALL" ? "is-active" : ""} onClick={() => setStatusFilter("ALL")} type="button">
              Tất cả
            </button>
          </div>
          <button className="secondary-button" onClick={() => void reload()} title="Làm mới" type="button">
            <RefreshCw className={loading ? "animate-spin" : ""} size={15} /> Làm mới ({total} bản ghi)
          </button>
        </div>

        {loading ? <p className="catalog-result-note">Đang truy vấn dữ liệu từ Database...</p> : null}
        {loadError ? <p className="catalog-result-note text-red-600" role="alert">{loadError}</p> : null}
        {!loading && !loadError && assignments.length === 0 ? (
          <p className="catalog-result-note">Chưa có bản ghi phân công nào trong cơ sở dữ liệu.</p>
        ) : null}

        <div className="catalog-table-wrap">
          <table className="catalog-table">
            <thead>
              <tr>
                <th>Khách hàng</th>
                <th>Tư vấn viên phụ trách</th>
                <th>Lý do điều chuyển</th>
                <th>Trạng thái</th>
                <th>Thời điểm phân công</th>
                <th>Thao tác</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((item) => (
                <tr key={item.assignment_id}>
                  <td>
                    <Link href={customerProfileHref(item.customer_id, "admin")}>
                      <strong>{item.customer_id}</strong>
                    </Link>
                    <small>Gán bởi: {item.assigned_by}</small>
                  </td>
                  <td>
                    <span className="inline-flex items-center gap-1.5 font-medium text-slate-800">
                      <UserCheck size={15} className="text-emerald-600" /> {item.advisor_id}
                    </span>
                  </td>
                  <td>{item.reason || "Phân công mặc định"}</td>
                  <td>
                    <StatusBadge
                      tone={
                        item.status === "ACTIVE"
                          ? "success"
                          : item.status === "TRANSFERRED"
                          ? "info"
                          : "neutral"
                      }
                    >
                      {item.status === "ACTIVE"
                        ? "Đang phụ trách"
                        : item.status === "TRANSFERRED"
                        ? "Đã chuyển"
                        : "Đã hủy"}
                    </StatusBadge>
                  </td>
                  <td>{formatDate(item.assigned_at)}</td>
                  <td>
                    <div className="flex items-center gap-2">
                      <button
                        className="table-action"
                        onClick={() => openAssignModal(item.customer_id, item.advisor_id)}
                        title="Chuyển sang Advisor khác"
                        type="button"
                      >
                        Chuyển
                      </button>
                      <button
                        className="table-action"
                        onClick={() => openHistoryModal(item.customer_id)}
                        title="Lịch sử phân công"
                        type="button"
                      >
                        <History size={14} /> Lịch sử
                      </button>
                      {item.status === "ACTIVE" ? (
                        <button
                          className="table-action text-red-600 hover:text-red-700"
                          onClick={() => void handleUnassign(item.customer_id)}
                          title="Hủy phân công"
                          type="button"
                        >
                          <UserMinus size={14} /> Hủy gán
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Modal Phân công */}
      {dialog === "assign" ? (
        <div className="dialog-layer" role="dialog" aria-modal="true">
          <button className="dialog-backdrop" onClick={() => setDialog(null)} type="button" />
          <section className="mock-dialog">
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">Customer Lead Allocation</span>
                <h2>Phân công Tư vấn viên phụ trách</h2>
              </div>
              <button className="icon-button" onClick={() => setDialog(null)} type="button">
                <X size={19} />
              </button>
            </div>

            <div className="field-label">
              Chọn khách hàng
              <CustomerPicker
                onChange={(customerId, item) => {
                  setSelectedCustomerId(customerId);
                  setSelectedAdvisorId(item?.advisor_id ?? "");
                }}
                value={selectedCustomerId}
              />
              {selectedCustomerId ? <small>Đã chọn: {selectedCustomerId}</small> : null}
            </div>

            {selectedAdvisorId ? (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-sm mb-3">
                <span className="text-slate-500">Tư vấn viên hiện tại:</span> <strong>{selectedAdvisorId}</strong>
              </div>
            ) : null}

            <label className="field-label">
              Chọn Tư vấn viên phụ trách (Advisor trong Database)
              <select onChange={(e) => setTargetAdvisorId(e.target.value)} value={targetAdvisorId}>
                {advisors.map((adv) => (
                  <option key={adv.id} value={adv.email || adv.id}>
                    {adv.email} ({adv.id})
                  </option>
                ))}
              </select>
            </label>

            <label className="field-label">
              Lý do phân công / điều chuyển
              <textarea
                rows={2}
                onChange={(e) => setReason(e.target.value)}
                placeholder="VD: Phân công theo khu vực, TVV cũ nghỉ phép, Khách yêu cầu đổi TVV..."
                value={reason}
              />
            </label>

            <div className="dialog-actions">
              <button className="secondary-button" onClick={() => setDialog(null)} type="button">
                Hủy
              </button>
              <button
                className="primary-button"
                disabled={
                  saving ||
                  !selectedCustomerId.trim() ||
                  !targetAdvisorId.trim()
                }
                onClick={() => void handleAssignSubmit()}
                type="button"
              >
                {saving ? "Đang lưu vào DB..." : "Xác nhận phân công (Lưu DB)"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {/* Modal Lịch sử */}
      {dialog === "history" ? (
        <div className="dialog-layer" role="dialog" aria-modal="true">
          <button className="dialog-backdrop" onClick={() => setDialog(null)} type="button" />
          <section className="mock-dialog max-w-lg">
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">Assignment Audit Trail</span>
                <h2>Lịch sử phân công trong Database: {selectedCustomerId}</h2>
              </div>
              <button className="icon-button" onClick={() => setDialog(null)} type="button">
                <X size={19} />
              </button>
            </div>

            {historyItems.length === 0 ? (
              <p className="py-6 text-center text-slate-500">Chưa có lịch sử chuyển giao nào trong cơ sở dữ liệu.</p>
            ) : (
              <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
                {historyItems.map((h) => (
                  <div key={h.assignment_id} className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-sm space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-800 flex items-center gap-1">
                        <UserCheck size={14} className="text-emerald-600" /> {h.advisor_id}
                      </span>
                      <StatusBadge tone={h.status === "ACTIVE" ? "success" : "neutral"}>
                        {h.status}
                      </StatusBadge>
                    </div>
                    <div className="text-xs text-slate-500">
                      Gán bởi: <strong>{h.assigned_by}</strong> · Lúc: {formatDate(h.assigned_at)}
                    </div>
                    {h.unassigned_at ? (
                      <div className="text-xs text-slate-400">
                        Kết thúc: {formatDate(h.unassigned_at)}
                      </div>
                    ) : null}
                    {h.reason ? (
                      <div className="text-xs text-slate-700 bg-white p-1.5 rounded border border-slate-100 mt-1">
                        Lý do: {h.reason}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            )}

            <div className="dialog-actions">
              <button className="secondary-button" onClick={() => setDialog(null)} type="button">
                Đóng
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

