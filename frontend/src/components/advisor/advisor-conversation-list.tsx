"use client";

import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  LogIn,
  Mail,
  Maximize2,
  MessageSquare,
  PanelRightClose,
  RotateCcw,
  Search,
  ShieldAlert,
  UserRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type AdvisorConversationDetail,
  closeAdvisorConversation,
  fetchAdvisorConversation,
  listAdvisorConversations,
} from "@/lib/api/agent";
import { useAuth } from "@/store/auth-store";

function formatDateTime(dateStr?: string): { time: string; date: string } {
  if (!dateStr) return { time: "—", date: "" };
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) return { time: dateStr, date: "" };
  const time = date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  const dayMonthYear = date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
  return { time, date: dayMonthYear };
}

const PAGE_SIZE = 10;

export function AdvisorConversationList() {
  const { user, login } = useAuth();
  const isStaff = user?.role === "advisor" || user?.role === "admin";

  const [conversations, setConversations] = useState<readonly AdvisorConversationDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [currentPage, setCurrentPage] = useState(1);

  // Selected session for split view / quick preview
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [previewDetail, setPreviewDetail] = useState<AdvisorConversationDetail | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // State for closing a session
  const [sessionToClose, setSessionToClose] = useState<AdvisorConversationDetail | null>(null);
  const [closing, setClosing] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await listAdvisorConversations();
      setConversations(res.items || []);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes("401") || msg.includes("authentication required")) {
        setLoadError("Chưa đăng nhập tài khoản Tư vấn viên để truy vấn danh sách phiên.");
      } else {
        setLoadError("Không thể tải danh sách phiên chat từ Database.");
      }
      setConversations([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData, user]);

  // Load preview conversation when a session is selected
  useEffect(() => {
    if (!selectedSessionId) {
      setPreviewDetail(null);
      return;
    }
    setPreviewLoading(true);
    fetchAdvisorConversation(selectedSessionId)
      .then((data) => setPreviewDetail(data))
      .catch(() => setPreviewDetail(null))
      .finally(() => setPreviewLoading(false));
  }, [selectedSessionId]);

  async function handleQuickAdvisorLogin(email: string) {
    setLoading(true);
    try {
      await login(email, "Admin@123456");
      await loadData();
    } catch {
      setLoadError("Đăng nhập TVV thất bại.");
    } finally {
      setLoading(false);
    }
  }

  async function handleConfirmClose() {
    if (!sessionToClose) return;
    setClosing(true);
    try {
      await closeAdvisorConversation(sessionToClose.conversation_id);
      setSessionToClose(null);
      if (selectedSessionId === sessionToClose.conversation_id) {
        setSelectedSessionId(null);
      }
      await loadData();
    } catch (err: unknown) {
      alert("Không thể kết thúc phiên: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      setClosing(false);
    }
  }

  // Dynamic KPI calculations
  const kpis = useMemo(() => {
    const total = conversations.length;
    let active = 0;
    let waiting = 0;
    let closed = 0;

    for (const item of conversations) {
      const st = item.status?.toUpperCase();
      if (st === "WAITING_ADVISOR") {
        waiting += 1;
        active += 1;
      } else if (st === "COMPLETED" || st === "CLOSED") {
        closed += 1;
      } else {
        active += 1;
      }
    }
    return { total, active, waiting, closed };
  }, [conversations]);

  // Search and status filtering
  const filteredItems = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    return conversations.filter((item) => {
      const st = item.status?.toUpperCase();
      const isClosed = st === "COMPLETED" || st === "CLOSED";
      const isWaiting = st === "WAITING_ADVISOR";
      const isActive = !isClosed;

      if (statusFilter === "ACTIVE" && !isActive) return false;
      if (statusFilter === "WAITING" && !isWaiting) return false;
      if (statusFilter === "CLOSED" && !isClosed) return false;

      if (!q) return true;

      const convId = (item.conversation_id || "").toLowerCase();
      const custId = (item.customer_id || "").toLowerCase();
      const custDisplay = (item.customer_display || "").toLowerCase();
      const lastMsg = (item.last_message_preview || "").toLowerCase();

      return convId.includes(q) || custId.includes(q) || custDisplay.includes(q) || lastMsg.includes(q);
    });
  }, [conversations, searchQuery, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE));
  const paginatedItems = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredItems.slice(start, start + PAGE_SIZE);
  }, [filteredItems, currentPage]);

  const startRecord = filteredItems.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const endRecord = Math.min(currentPage * PAGE_SIZE, filteredItems.length);

  return (
    <div className="advisor-conversations-wrapper space-y-6">
      {/* Actionable / Clickable Metric KPIs as Filters */}
      <div className="metric-grid chat-kpi-grid">
        <article
          className={`metric-card cursor-pointer transition-all ${
            statusFilter === "ALL" ? "ring-2 ring-blue-600 bg-blue-50/40" : "hover:bg-slate-50"
          }`}
          onClick={() => {
            setStatusFilter("ALL");
            setCurrentPage(1);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setStatusFilter("ALL");
              setCurrentPage(1);
            }
          }}
          title="Bấm để xem tất cả phiên"
        >
          <span>Tổng phiên</span>
          <strong>{kpis.total.toLocaleString("vi-VN")}</strong>
          <small className="text-slate-600 font-medium">
            {kpis.active} đang hoạt động · {kpis.closed} đã đóng
          </small>
        </article>

        <article
          className={`metric-card cursor-pointer transition-all ${
            statusFilter === "ACTIVE" ? "ring-2 ring-emerald-600 bg-emerald-50/40" : "hover:bg-slate-50"
          }`}
          onClick={() => {
            setStatusFilter("ACTIVE");
            setCurrentPage(1);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setStatusFilter("ACTIVE");
              setCurrentPage(1);
            }
          }}
          title="Bấm để lọc phiên đang hoạt động"
        >
          <span>Đang hoạt động</span>
          <strong className="text-emerald-700">{kpis.active.toLocaleString("vi-VN")}</strong>
          <small className="text-slate-600 font-medium">
            {kpis.active > 0 ? `${kpis.active} phiên cần theo dõi` : "Không có phiên trực tiếp"}
          </small>
        </article>

        <article
          className={`metric-card cursor-pointer transition-all ${
            statusFilter === "WAITING" ? "ring-2 ring-amber-600 bg-amber-50/40" : "hover:bg-slate-50"
          }`}
          onClick={() => {
            setStatusFilter("WAITING");
            setCurrentPage(1);
          }}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              setStatusFilter("WAITING");
              setCurrentPage(1);
            }
          }}
          title="Bấm để lọc phiên cần bạn xử lý"
        >
          <span>Cần bạn xử lý</span>
          <strong className={kpis.waiting > 0 ? "text-amber-600" : "text-slate-700"}>
            {kpis.waiting.toLocaleString("vi-VN")}
          </strong>
          <small className="text-slate-600 font-medium">
            {kpis.waiting > 0 ? `${kpis.waiting} yêu cầu cần can thiệp` : "Không có phiên cần can thiệp"}
          </small>
        </article>
      </div>

      {/* 1. Card Container (Khung bao ngoài) */}
      <section className="bg-white rounded-xl shadow-sm border border-slate-200/80 overflow-hidden">
        {/* Card Header (Tiêu đề + Bộ lọc) */}
        <div className="p-4 border-b border-slate-200/80 bg-white flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Danh sách Phiên hội thoại</h2>
            <p className="text-xs text-slate-500 mt-0.5">Quản lý và tiếp nhận các phiên hội thoại được phân công cho bạn.</p>
          </div>

          {/* Bộ lọc (Filter & Search) */}
          <div className="flex flex-wrap items-center gap-3">
            <span className="px-2.5 py-1 bg-slate-100 border border-slate-200/80 rounded-md text-xs font-semibold text-slate-700 shrink-0">
              {filteredItems.length} phiên
            </span>

            {/* Dropdown trạng thái */}
            <div className="relative">
              <label className="sr-only" htmlFor="status-filter">Lọc trạng thái</label>
              <select
                id="status-filter"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setCurrentPage(1);
                }}
                className="py-1.5 px-3 border border-slate-200 rounded-lg text-xs bg-white text-slate-700 font-medium focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all cursor-pointer shadow-2xs"
              >
                <option value="ALL">Tất cả trạng thái</option>
                <option value="ACTIVE">Đang hoạt động</option>
                <option value="WAITING">Cần bạn xử lý</option>
                <option value="CLOSED">Đã đóng</option>
              </select>
            </div>

            {/* Ô tìm kiếm viền mảnh */}
            <div className="relative flex items-center">
              <Search size={15} className="absolute left-3 text-slate-400 pointer-events-none" />
              <label className="sr-only" htmlFor="search-input">Tìm phiên chat</label>
              <input
                id="search-input"
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1);
                }}
                placeholder="Tìm mã phiên, khách hàng..."
                className="pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all w-52 sm:w-64 shadow-2xs"
              />
            </div>

            {/* Nút Làm mới gọn gàng */}
            <button
              type="button"
              onClick={() => void loadData()}
              title="Làm mới dữ liệu"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 hover:border-slate-300 rounded-lg transition-all shadow-2xs shrink-0"
            >
              <RotateCcw size={13} className={loading ? "animate-spin text-blue-600" : "text-slate-500"} />
              <span>Làm mới</span>
            </button>
          </div>
        </div>

        {!isStaff ? (
          <div className="m-4 p-4 bg-amber-50 border border-amber-200 rounded-lg flex items-center justify-between">
            <div className="flex items-center gap-2 text-amber-900 text-sm">
              <ShieldAlert size={18} className="text-amber-600 shrink-0" />
              <span>
                Bạn chưa đăng nhập quyền <strong>Tư vấn viên (Advisor)</strong>.
              </span>
            </div>
            <button
              className="primary-button text-xs py-1.5 px-3 rounded-lg"
              onClick={() => void handleQuickAdvisorLogin("advisor@gmail.com")}
              type="button"
            >
              <LogIn size={14} /> Đăng nhập TVV (advisor@gmail.com)
            </button>
          </div>
        ) : null}

        {loading ? <p className="catalog-result-note p-8 text-center text-xs text-slate-500">Đang tải danh sách phiên chat...</p> : null}
        {loadError ? <p className="catalog-result-note p-8 text-center text-xs text-red-600" role="alert">{loadError}</p> : null}
        {!loading && !loadError && filteredItems.length === 0 ? (
          <p className="catalog-result-note p-8 text-center text-xs text-slate-500">Không tìm thấy phiên chat nào phù hợp.</p>
        ) : null}

        {!loading && !loadError && filteredItems.length > 0 ? (
          <div className={selectedSessionId ? "grid grid-cols-1 lg:grid-cols-12 border-t border-slate-200/80" : ""}>
            {/* 2. Cấu trúc Bảng (Table Structure & Spacing) */}
            <div className={selectedSessionId ? "lg:col-span-7 border-r border-slate-200/80 overflow-x-auto" : "overflow-x-auto"}>
              <table className="w-full border-collapse text-left">
                {/* Header (<thead>) */}
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/80">
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 w-[18%] min-w-[150px]">
                      Mã phiên
                    </th>
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 w-[22%] min-w-[170px]">
                      Khách hàng
                    </th>
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 w-[16%] min-w-[130px]">
                      Trạng thái
                    </th>
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 min-w-[160px]">
                      Tin nhắn cuối
                    </th>
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-right w-[13%] min-w-[100px]">
                      Cập nhật
                    </th>
                    <th className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-right w-[190px] min-w-[190px]">
                      Hành động
                    </th>
                  </tr>
                </thead>

                {/* Hàng dữ liệu (<tbody> <tr>) */}
                <tbody className="divide-y divide-slate-200/80 text-xs">
                  {paginatedItems.map((item) => {
                    const st = item.status?.toUpperCase();
                    const isClosed = st === "COMPLETED" || st === "CLOSED";
                    const isWaiting = st === "WAITING_ADVISOR";
                    const isSelected = selectedSessionId === item.conversation_id;
                    const { time, date } = formatDateTime(item.last_activity_at);

                    return (
                      <tr
                        key={item.conversation_id}
                        className={`cursor-pointer transition-colors ${
                          isSelected ? "bg-blue-50/60" : "hover:bg-slate-50/70"
                        }`}
                        onClick={() => setSelectedSessionId(item.conversation_id)}
                      >
                        {/* 3.1 Mã phiên: Icon loại tin nhắn bo tròn nền nhạt */}
                        <td className="py-3.5 px-4 align-middle">
                          <div className="flex items-center gap-3">
                            <span className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 border border-blue-100 flex items-center justify-center shrink-0">
                              <Mail size={15} />
                            </span>
                            <div className="min-w-0">
                              <span
                                className="font-mono text-xs font-semibold block text-slate-800 hover:text-blue-600 transition-colors truncate"
                                title={item.conversation_id}
                              >
                                {item.conversation_id.slice(0, 8)}...
                              </span>
                              <span className="text-[11px] text-slate-500 block leading-tight mt-0.5">
                                {isWaiting ? "Cần hỗ trợ" : "Tư vấn"}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* 3.2 Khách hàng: Avatar hình tròn gọn gàng + mã ID cắt ngắn */}
                        <td className="py-3.5 px-4 align-middle">
                          <div className="flex items-center gap-3">
                            <span className="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-100 flex items-center justify-center shrink-0">
                              <UserRound size={15} />
                            </span>
                            <div className="min-w-0">
                              <span className="text-xs font-semibold text-slate-900 block truncate">
                                {item.customer_display || "Khách hàng"}
                              </span>
                              <span
                                className="text-xs font-mono text-slate-400 block truncate leading-tight mt-0.5 max-w-[140px]"
                                title={item.customer_id}
                              >
                                {item.customer_id.length > 16 ? `${item.customer_id.slice(0, 16)}...` : item.customer_id}
                              </span>
                            </div>
                          </div>
                        </td>

                        {/* 3.3 Trạng thái (Badge/Pill với chấm tròn) */}
                        <td className="py-3.5 px-4 align-middle whitespace-nowrap">
                          {isWaiting ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200/60">
                              <span className="w-1.5 h-1.5 rounded-full bg-amber-500"></span>
                              Cần bạn xử lý
                            </span>
                          ) : isClosed ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200/60">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                              Đã đóng
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200/60">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                              Đang hoạt động
                            </span>
                          )}
                        </td>

                        {/* 3.4 Tin nhắn cuối: Preview 1 dòng ngắn gọn */}
                        <td className="py-3.5 px-4 align-middle">
                          {item.last_message_preview ? (
                            <p className="text-xs text-slate-500 truncate max-w-[220px]" title={item.last_message_preview}>
                              {item.last_message_preview}
                            </p>
                          ) : (
                            <span className="text-slate-300 text-xs">—</span>
                          )}
                        </td>

                        {/* 3.5 Thời gian (Cập nhật): Tách giờ và ngày rõ ràng */}
                        <td className="py-3.5 px-4 align-middle text-right whitespace-nowrap">
                          <span className="text-xs font-semibold text-slate-700 block">
                            {time}
                          </span>
                          {date ? (
                            <span className="text-xs text-slate-400 block leading-tight mt-0.5">
                              {date}
                            </span>
                          ) : null}
                        </td>

                        {/* 3.6 Hành động (Action Buttons) */}
                        <td className="py-3.5 px-4 align-middle text-right whitespace-nowrap w-[190px] min-w-[190px]" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-2 whitespace-nowrap shrink-0">
                            {/* Nút "Vào chat" nổi bật */}
                            <Link
                              href={`/advisor/conversations/${item.conversation_id}`}
                              className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg shadow-sm transition-all shrink-0"
                            >
                              <MessageSquare size={13} />
                              <span>{isClosed ? "Xem lại" : "Vào chat"}</span>
                            </Link>

                            {/* Nút "Đóng" phụ viền mảnh */}
                            {!isClosed ? (
                              <button
                                type="button"
                                onClick={() => setSessionToClose(item)}
                                title="Đóng phiên tư vấn"
                                className="inline-flex items-center justify-center gap-1 px-2.5 py-1.5 border border-slate-200 hover:bg-rose-50 hover:text-rose-600 hover:border-rose-200 text-slate-600 text-xs rounded-lg transition-all shrink-0 font-medium bg-white"
                              >
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

            {/* Split View: Live Preview Panel */}
            {selectedSessionId ? (
              <div className="lg:col-span-5 bg-white flex flex-col h-[600px]">
                {/* Preview Header */}
                <div className="p-3.5 border-b border-slate-200/80 flex items-center justify-between bg-slate-50/80">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-xs font-semibold text-slate-800">
                      #{selectedSessionId.slice(0, 8)}
                    </span>
                    <span className="text-xs text-slate-500 truncate">
                      {previewDetail?.customer_display || previewDetail?.customer_id || "Đang tải..."}
                    </span>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <Link
                      className="p-1.5 text-slate-600 hover:text-blue-600 rounded-lg hover:bg-slate-200 transition-colors"
                      href={`/advisor/conversations/${selectedSessionId}`}
                      title="Mở toàn màn hình"
                    >
                      <Maximize2 size={15} />
                    </Link>
                    <button
                      className="p-1.5 text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors"
                      onClick={() => setSelectedSessionId(null)}
                      title="Đóng xem nhanh"
                      type="button"
                    >
                      <PanelRightClose size={15} />
                    </button>
                  </div>
                </div>

                {/* Preview Content */}
                <div className="flex-1 p-4 overflow-y-auto space-y-3">
                  {previewLoading ? (
                    <div className="text-center py-12 text-xs text-slate-500 flex flex-col items-center gap-2">
                      <RotateCcw className="animate-spin text-blue-600" size={18} />
                      <span>Đang nạp hội thoại...</span>
                    </div>
                  ) : previewDetail ? (
                    <>
                      {/* Status and info snippet */}
                      <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs flex items-center justify-between">
                        <div>
                          <span className="text-slate-500 block text-[11px]">Trạng thái phiên</span>
                          <strong className="text-slate-900 font-semibold">
                            {previewDetail.status === "COMPLETED" || previewDetail.status === "CLOSED"
                              ? "Đã đóng"
                              : previewDetail.status === "WAITING_ADVISOR"
                              ? "Cần bạn xử lý"
                              : "Đang hoạt động"}
                          </strong>
                        </div>
                        {previewDetail.status !== "COMPLETED" && previewDetail.status !== "CLOSED" ? (
                          <button
                            className="text-xs py-1 px-2.5 text-rose-600 border border-rose-200 hover:bg-rose-50 font-medium rounded-lg transition-all"
                            onClick={() => setSessionToClose(previewDetail)}
                            type="button"
                          >
                            Đóng phiên
                          </button>
                        ) : null}
                      </div>

                      {/* Messages list preview */}
                      <div className="space-y-2 pt-1">
                        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 block">
                          Lịch sử trao đổi ({previewDetail.messages?.length || 0})
                        </span>
                        {previewDetail.messages?.length === 0 ? (
                          <p className="text-xs text-slate-500 italic">Chưa có tin nhắn trong phiên này.</p>
                        ) : (
                          previewDetail.messages?.map((msg: { message_id?: string; role?: string; sender_type?: string; content?: string; text?: string }, idx: number) => {
                            const isAdvisor = msg.role === "ADVISOR";
                            const isUser = msg.role === "USER" || msg.sender_type === "CUSTOMER";
                            return (
                              <div
                                key={msg.message_id || idx}
                                className={`p-2.5 rounded-lg text-xs leading-relaxed ${
                                  isAdvisor
                                    ? "bg-blue-600 text-white ml-6"
                                    : isUser
                                    ? "bg-slate-100 text-slate-800 mr-6"
                                    : "bg-amber-50/80 border border-amber-200 text-amber-900 mx-2 text-[11px]"
                                }`}
                              >
                                <div className="text-[10px] opacity-75 font-semibold mb-0.5">
                                  {isAdvisor ? "Bạn (TVV)" : isUser ? "Khách hàng" : "Trợ lý AI"}
                                </div>
                                <div>{msg.content || msg.text}</div>
                              </div>
                            );
                          })
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="text-center py-12 text-xs text-slate-500">
                      Không tải được thông tin phiên.
                    </div>
                  )}
                </div>

                {/* Preview Footer */}
                <div className="p-3 border-t border-slate-200/80 bg-slate-50 rounded-b-lg flex items-center justify-between">
                  <span className="text-xs text-slate-500">Mở phòng chat đầy đủ để tương tác trực tiếp</span>
                  <Link
                    className="inline-flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg transition-all"
                    href={`/advisor/conversations/${selectedSessionId}`}
                  >
                    <span>Mở phòng chat</span> <ExternalLink size={13} />
                  </Link>
                </div>
              </div>
            ) : null}
          </div>
        ) : null}

        {/* 4. Phân trang (Pagination footer) */}
        {!loading && !loadError && filteredItems.length > 0 ? (
          <div className="p-3.5 border-t border-slate-200/80 bg-slate-50/50 flex items-center justify-between text-xs text-slate-500">
            <div>
              Hiển thị <span className="font-semibold text-slate-700">{startRecord}–{endRecord}</span> trên <span className="font-semibold text-slate-700">{filteredItems.length}</span> phiên
            </div>
            <div className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => setCurrentPage((prev) => Math.max(prev - 1, 1))}
                disabled={currentPage === 1}
                className="inline-flex items-center justify-center p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-2xs"
                title="Trang trước"
              >
                <ChevronLeft size={15} />
              </button>
              <span className="px-2 py-1 font-medium text-slate-700">
                {currentPage} / {totalPages}
              </span>
              <button
                type="button"
                onClick={() => setCurrentPage((prev) => Math.min(prev + 1, totalPages))}
                disabled={currentPage === totalPages}
                className="inline-flex items-center justify-center p-1.5 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 hover:border-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-2xs"
                title="Trang tiếp theo"
              >
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {/* Confirmation Dialog to Close Session */}
      {sessionToClose ? (
        <div className="chat-confirm-backdrop" role="presentation">
          <section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="end-chat-title">
            <button
              className="chat-confirm-close"
              onClick={() => setSessionToClose(null)}
              type="button"
              aria-label="Đóng"
            >
              <X size={18} />
            </button>
            <span className="eyebrow text-amber-600 flex items-center gap-1 font-semibold">
              <AlertCircle size={14} /> Đóng phiên tư vấn
            </span>
            <h2 id="end-chat-title" className="text-base font-bold text-slate-900 mt-1">
              Đóng phiên tư vấn này?
            </h2>
            <p className="text-xs text-slate-600 mt-2 leading-relaxed">
              Bạn có chắc muốn kết thúc phiên tư vấn cho khách hàng (
              <strong>{sessionToClose.customer_display || sessionToClose.customer_id}</strong>)? Khách hàng sẽ kết thúc phiên hiện tại và bạn vẫn có thể xem lại toàn bộ lịch sử sau khi đóng.
            </p>
            <div className="flex items-center justify-end gap-2 mt-4">
              <button
                className="secondary-button text-xs py-1.5 px-3 rounded-lg"
                onClick={() => setSessionToClose(null)}
                disabled={closing}
                type="button"
              >
                Huỷ
              </button>
              <button
                className="danger-button text-xs py-1.5 px-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-medium"
                onClick={() => void handleConfirmClose()}
                disabled={closing}
                type="button"
              >
                {closing ? "Đang đóng..." : "Xác nhận kết thúc"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
