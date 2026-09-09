"use client";

import {
  AlertCircle,
  CalendarDays,
  CarFront,
  CircleDollarSign,
  Edit3,
  FileText,
  Headset,
  History,
  MapPin,
  MessageSquare,
  MoreVertical,
  Pin,
  PinOff,
  Plus,
  Scale,
  Search,
  Trash2,
  X,
  Zap,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  clearConversationCustomData,
  enrichConversation,
  filterConversations,
  getCustomConversationTitles,
  getPinnedConversationIds,
  groupConversations,
  setCustomConversationTitle,
  setPinnedConversation,
  type ConversationIntent,
  type EnrichedConversation,
} from "@/lib/conversation-helpers";
import { deleteConversation, fetchConversations } from "@/lib/api/agent";
import type { ConversationSummary } from "@/types/agent";

function renderIntentIcon(intent: ConversationIntent): React.JSX.Element {
  switch (intent) {
    case "comparison":
      return <Scale aria-hidden="true" className="conv-intent-icon conv-intent-comparison" size={15} />;
    case "price":
      return <CircleDollarSign aria-hidden="true" className="conv-intent-icon conv-intent-price" size={15} />;
    case "charging_station":
      return <Zap aria-hidden="true" className="conv-intent-icon conv-intent-charging" size={15} />;
    case "showroom":
      return <MapPin aria-hidden="true" className="conv-intent-icon conv-intent-showroom" size={15} />;
    case "test_drive":
      return <CalendarDays aria-hidden="true" className="conv-intent-icon conv-intent-testdrive" size={15} />;
    case "policy":
      return <FileText aria-hidden="true" className="conv-intent-icon conv-intent-policy" size={15} />;
    case "advisor":
      return <Headset aria-hidden="true" className="conv-intent-icon conv-intent-advisor" size={15} />;
    case "vehicle_consultation":
      return <CarFront aria-hidden="true" className="conv-intent-icon conv-intent-vehicle" size={15} />;
    default:
      return <MessageSquare aria-hidden="true" className="conv-intent-icon conv-intent-general" size={15} />;
  }
}

export function ConversationHistorySidebar({
  activeConversationId,
  onNewConversation,
  isOpen = false,
  onClose,
  rail = null,
}: Readonly<{
  activeConversationId: string;
  onNewConversation: () => void;
  isOpen?: boolean;
  onClose?: () => void;
  /**
   * Chế độ THANH MẢNH 56px (Sếp 2026-08-31): khi cửa sổ "trang đi theo hội
   * thoại" mở, danh sách thu lại nhường chỗ — khung chat GIỮ NGUYÊN chiều rộng,
   * chỉ dịch sang trái đúng phần vừa thu. Thanh có nút bung lại danh sách và
   * avatar (ảnh xe đã chốt / ghim bản đồ) bấm để mở lại cửa sổ. `null` = bình
   * thường. Danh sách vẫn MOUNT (chỉ ẩn bằng CSS) nên bung lại không nạp lại.
   */
  rail?: {
    readonly avatar: { readonly src: string; readonly alt: string } | null;
    readonly label: string;
    readonly onExpand: () => void;
    readonly onAvatarClick: () => void;
  } | null;
}>): React.JSX.Element {
  const pathname = usePathname();
  const router = useRouter();

  const [rawSummaries, setRawSummaries] = useState<readonly ConversationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(() => getPinnedConversationIds());
  const [customTitles, setCustomTitles] = useState<Record<string, string>>(() => getCustomConversationTitles());

  // Menu & Modal states
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<EnrichedConversation | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [renameTarget, setRenameTarget] = useState<EnrichedConversation | null>(null);
  const [renameInput, setRenameInput] = useState("");

  const renameInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchConversations();
      setRawSummaries(res.items);
      setPinnedIds(getPinnedConversationIds());
      setCustomTitles(getCustomConversationTitles());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, activeConversationId]);

  // Click outside listener for context menu
  useEffect(() => {
    function handleClickOutside(event: MouseEvent): void {
      const target = event.target as HTMLElement | null;
      if (!target?.closest(".conversation-item-actions")) {
        setActiveMenuId(null);
      }
    }
    if (activeMenuId) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [activeMenuId]);

  // Escape key listener for modals and menus
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        setActiveMenuId(null);
        setDeleteTarget(null);
        setRenameTarget(null);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Focus rename input when rename modal opens
  useEffect(() => {
    if (renameTarget) {
      setTimeout(() => renameInputRef.current?.focus(), 50);
    }
  }, [renameTarget]);

  // Enrich items with custom titles, pins, and metadata
  const enrichedItems = useMemo<readonly EnrichedConversation[]>(() => {
    return rawSummaries.map((summary) =>
      enrichConversation(summary, {
        isPinned: pinnedIds.has(summary.conversation_id),
        customTitle: customTitles[summary.conversation_id],
      }),
    );
  }, [rawSummaries, pinnedIds, customTitles]);

  // Filter with realtime search query
  const filteredItems = useMemo<readonly EnrichedConversation[]>(() => {
    return filterConversations(enrichedItems, searchQuery);
  }, [enrichedItems, searchQuery]);

  // Group by time & pinned
  const groupedList = useMemo(() => {
    return groupConversations(filteredItems);
  }, [filteredItems]);

  // Pin / Unpin toggle handler
  function handleTogglePin(item: EnrichedConversation): void {
    const nextPinned = !item.isPinned;
    setPinnedConversation(item.id, nextPinned);
    setPinnedIds((prev) => {
      const next = new Set(prev);
      if (nextPinned) next.add(item.id);
      else next.delete(item.id);
      return next;
    });
    setActiveMenuId(null);
  }

  // Rename modal submit handler
  function handleSaveRename(e?: React.FormEvent): void {
    e?.preventDefault();
    if (!renameTarget) return;
    const newTitle = renameInput.trim();
    setCustomConversationTitle(renameTarget.id, newTitle);
    setCustomTitles((prev) => ({ ...prev, [renameTarget.id]: newTitle }));
    setRenameTarget(null);
    setRenameInput("");
    setActiveMenuId(null);
  }

  // Delete conversation confirmed
  async function handleConfirmDelete(): Promise<void> {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteConversation(deleteTarget.id);
      clearConversationCustomData(deleteTarget.id);
      const isCurrentActive = deleteTarget.id === activeConversationId;
      setDeleteTarget(null);
      await load();

      if (isCurrentActive) {
        router.push("/consultation");
        onNewConversation();
        onClose?.();
      }
    } catch {
      setError(true);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      {/* Mobile Backdrop Scrim */}
      {isOpen ? (
        <button
          aria-label="Đóng lịch sử trò chuyện"
          className="conversation-history-scrim"
          onClick={onClose}
          type="button"
        />
      ) : null}

      <aside
        aria-label="Cuộc trò chuyện"
        className={["conversation-history-sidebar", isOpen ? "is-open" : "", rail ? "is-rail" : ""].filter(Boolean).join(" ")}
      >
        {rail ? (
          <div className="conversation-history-rail">
            <button
              aria-label="Mở danh sách hội thoại"
              className="history-icon-button"
              onClick={rail.onExpand}
              title="Mở danh sách hội thoại"
              type="button"
            >
              <History aria-hidden="true" size={18} />
            </button>
            <button
              aria-label="Tạo cuộc trò chuyện mới"
              className="history-icon-button"
              onClick={onNewConversation}
              title="Cuộc trò chuyện mới"
              type="button"
            >
              <Plus aria-hidden="true" size={18} />
            </button>
            <button
              aria-label={rail.label}
              className="conversation-history-rail__avatar"
              onClick={rail.onAvatarClick}
              title={rail.label}
              type="button"
            >
              {rail.avatar ? (
                <Image alt={rail.avatar.alt} height={40} src={rail.avatar.src} unoptimized width={40} />
              ) : (
                <MapPin aria-hidden="true" size={18} />
              )}
            </button>
          </div>
        ) : null}
        {/* Header */}
        <div className="conversation-history-header">
          <div className="conversation-header-brand">
            <span className="eyebrow">VinFast AI</span>
            <h2>Cuộc trò chuyện</h2>
          </div>
          <div className="history-header-actions">
            <button
              aria-label="Tạo cuộc trò chuyện mới"
              className="history-icon-button"
              onClick={() => {
                onNewConversation();
                onClose?.();
              }}
              title="Cuộc trò chuyện mới"
              type="button"
            >
              <Plus size={18} />
            </button>
            <button
              aria-label="Đóng lịch sử chat"
              className="history-close-button"
              onClick={onClose}
              title="Đóng"
              type="button"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="conversation-search-wrapper">
          <div className="conversation-search-box">
            <Search aria-hidden="true" className="search-icon" size={15} />
            <input
              aria-label="Tìm cuộc trò chuyện"
              className="conversation-search-input"
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Tìm cuộc trò chuyện..."
              type="text"
              value={searchQuery}
            />
            {searchQuery ? (
              <button
                aria-label="Xóa tìm kiếm"
                className="search-clear-btn"
                onClick={() => setSearchQuery("")}
                type="button"
              >
                <X size={14} />
              </button>
            ) : null}
          </div>
        </div>

        {/* Primary CTA: New Conversation Button */}
        <button
          aria-label="Bắt đầu cuộc trò chuyện mới"
          className="new-conversation-button"
          onClick={() => {
            onNewConversation();
            onClose?.();
          }}
          type="button"
        >
          <Plus aria-hidden="true" size={16} />
          <span>Cuộc trò chuyện mới</span>
        </button>

        {/* Conversation List / Groups */}
        <div className="conversation-history-list">
          {/* Skeleton Loading State */}
          {loading ? (
            <div aria-label="Đang tải lịch sử" className="conversation-skeleton-list">
              {[1, 2, 3, 4].map((n) => (
                <div className="conversation-skeleton-item" key={n}>
                  <div className="skeleton-line-1">
                    <div className="skeleton-icon" />
                    <div className="skeleton-title" />
                  </div>
                  <div className="skeleton-line-2" />
                  <div className="skeleton-line-3" />
                </div>
              ))}
            </div>
          ) : null}

          {/* Error State */}
          {!loading && error ? (
            <div className="conversation-history-state conversation-state-error">
              <AlertCircle size={24} />
              <span>Không tải được danh sách trò chuyện.</span>
              <button className="state-action-btn" onClick={() => void load()} type="button">
                Thử lại
              </button>
            </div>
          ) : null}

          {/* Empty State: No Conversations at all */}
          {!loading && !error && rawSummaries.length === 0 ? (
            <div className="conversation-empty-card">
              <div className="empty-icon-circle">
                <MessageSquare className="empty-icon" size={24} />
              </div>
              <h3>Chưa có cuộc trò chuyện</h3>
              <p>Bắt đầu trò chuyện với VinFast AI để được tư vấn chọn xe, báo giá và chính sách.</p>
              <button
                className="empty-cta-btn"
                onClick={() => {
                  onNewConversation();
                  onClose?.();
                }}
                type="button"
              >
                <Plus size={15} /> Cuộc trò chuyện mới
              </button>
            </div>
          ) : null}

          {/* Empty Search Result */}
          {!loading && !error && rawSummaries.length > 0 && filteredItems.length === 0 ? (
            <div className="conversation-history-state">
              <Search className="text-muted" size={22} />
              <span>Không tìm thấy cuộc trò chuyện nào phù hợp.</span>
              <button
                className="state-action-btn"
                onClick={() => setSearchQuery("")}
                type="button"
              >
                Xóa tìm kiếm
              </button>
            </div>
          ) : null}

          {/* Render Groups */}
          {!loading &&
            !error &&
            groupedList.map((group) => (
              <div className="conversation-time-group" key={group.key}>
                <div className="conversation-group-header">
                  <span>{group.label}</span>
                  <small>{group.items.length}</small>
                </div>

                <div className="conversation-group-items">
                  {group.items.map((item) => {
                    const isActive = item.id === activeConversationId;
                    const isMenuOpen = activeMenuId === item.id;

                    return (
                      <div
                        className={`conversation-history-item ${isActive ? "is-active" : ""} ${isMenuOpen ? "menu-open" : ""}`}
                        key={item.id}
                      >
                        <Link
                          aria-current={isActive ? "page" : undefined}
                          className="conversation-item-main-link"
                          href={`${pathname}?conversation=${item.id}`}
                          onClick={() => onClose?.()}
                        >
                          {/* Row 1: Icon + Title */}
                          <div className="conversation-item-top">
                            <span className="conversation-item-icon">
                              {renderIntentIcon(item.intent)}
                            </span>
                            <strong className="conversation-item-title" title={item.title}>
                              {item.title}
                            </strong>
                          </div>

                          {/* Row 2: Preview */}
                          <div className="conversation-item-preview" title={item.preview}>
                            {item.preview}
                          </div>

                          {/* Row 3: Time • Short ID • Advisor badge */}
                          <div className="conversation-item-meta">
                            <span className="item-meta-time">{item.formattedTime}</span>
                            <span className="item-meta-divider">•</span>
                            <span className="item-meta-id">{item.shortId}</span>
                            {item.isAdvisorActive ? (
                              <>
                                <span className="item-meta-divider">•</span>
                                <span className="item-meta-advisor-badge">Tư vấn viên</span>
                              </>
                            ) : null}
                            {item.isPinned ? (
                              <Pin aria-hidden="true" className="item-meta-pin-icon" size={11} />
                            ) : null}
                          </div>
                        </Link>

                        {/* Action Dropdown Trigger */}
                        <div className="conversation-item-actions">
                          <button
                            aria-expanded={isMenuOpen}
                            aria-haspopup="menu"
                            aria-label={`Tùy chọn cho ${item.title}`}
                            className="conversation-more-btn"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setActiveMenuId(isMenuOpen ? null : item.id);
                            }}
                            title="Tùy chọn"
                            type="button"
                          >
                            <MoreVertical size={15} />
                          </button>

                          {/* Context Menu Dropdown */}
                          {isMenuOpen ? (
                            <div
                              className="conversation-context-menu"
                              role="menu"
                            >
                              <button
                                className="menu-action-btn"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  setRenameTarget(item);
                                  setRenameInput(item.title);
                                  setActiveMenuId(null);
                                }}
                                role="menuitem"
                                type="button"
                              >
                                <Edit3 size={14} />
                                <span>Đổi tên</span>
                              </button>

                              <button
                                className="menu-action-btn"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  handleTogglePin(item);
                                }}
                                role="menuitem"
                                type="button"
                              >
                                {item.isPinned ? (
                                  <>
                                    <PinOff size={14} />
                                    <span>Bỏ ghim</span>
                                  </>
                                ) : (
                                  <>
                                    <Pin size={14} />
                                    <span>Ghim</span>
                                  </>
                                )}
                              </button>

                              <button
                                className="menu-action-btn menu-action-danger"
                                onClick={(e) => {
                                  e.preventDefault();
                                  e.stopPropagation();
                                  setDeleteTarget(item);
                                  setActiveMenuId(null);
                                }}
                                role="menuitem"
                                type="button"
                              >
                                <Trash2 size={14} />
                                <span>Xóa</span>
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
        </div>
      </aside>

      {/* Delete Confirmation Modal */}
      {deleteTarget ? (
        <div
          aria-labelledby="delete-dialog-title"
          aria-modal="true"
          className="conversation-modal-overlay"
          role="dialog"
        >
          <div className="conversation-modal-card">
            <div className="modal-header-icon modal-danger-icon">
              <Trash2 size={22} />
            </div>
            <h3 id="delete-dialog-title">Xóa cuộc trò chuyện này?</h3>
            <p>
              Cuộc trò chuyện &ldquo;<strong>{deleteTarget.title}</strong>&rdquo; và toàn bộ lịch sử tin nhắn sẽ bị xóa vĩnh viễn và không thể khôi phục.
            </p>
            <div className="modal-actions">
              <button
                className="modal-btn modal-cancel-btn"
                disabled={deleting}
                onClick={() => setDeleteTarget(null)}
                type="button"
              >
                Hủy
              </button>
              <button
                aria-label="Xác nhận xóa"
                className="modal-btn modal-danger-btn"
                disabled={deleting}
                onClick={() => void handleConfirmDelete()}
                type="button"
              >
                {deleting ? "Đang xóa..." : "Xóa"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Rename Modal */}
      {renameTarget ? (
        <div
          aria-labelledby="rename-dialog-title"
          aria-modal="true"
          className="conversation-modal-overlay"
          role="dialog"
        >
          <form className="conversation-modal-card" onSubmit={handleSaveRename}>
            <div className="modal-header-icon modal-primary-icon">
              <Edit3 size={22} />
            </div>
            <h3 id="rename-dialog-title">Đổi tên cuộc trò chuyện</h3>
            <div className="modal-input-wrapper">
              <input
                aria-label="Tên cuộc trò chuyện mới"
                className="modal-text-input"
                maxLength={60}
                onChange={(e) => setRenameInput(e.target.value)}
                placeholder="Nhập tên cuộc trò chuyện..."
                ref={renameInputRef}
                type="text"
                value={renameInput}
              />
            </div>
            <div className="modal-actions">
              <button
                className="modal-btn modal-cancel-btn"
                onClick={() => setRenameTarget(null)}
                type="button"
              >
                Hủy
              </button>
              <button
                aria-label="Lưu tên mới"
                className="modal-btn modal-confirm-btn"
                type="submit"
              >
                Lưu
              </button>
            </div>
          </form>
        </div>
      ) : null}
    </>
  );
}
