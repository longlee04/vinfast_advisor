"use client";

import {
  ArrowRight,
  BellRing,
  CalendarDays,
  CheckCircle2,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  getDocumentDownloadUrl,
  listPublishedPolicyNotifications,
  type PublishedPolicyNotification,
} from "@/lib/api/policy-notifications";

function formatDate(value: string): string {
  try {
    return new Intl.DateTimeFormat("vi-VN", { dateStyle: "long" }).format(new Date(value));
  } catch {
    return value;
  }
}

export function PolicyNotifications() {
  const [items, setItems] = useState<PublishedPolicyNotification[]>([]);
  const [selectedItem, setSelectedItem] = useState<PublishedPolicyNotification | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState(false);

  async function handleDownloadOriginal(documentId: string) {
    try {
      setDownloading(true);
      const url = await getDocumentDownloadUrl(documentId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      alert("Không thể tải tài liệu gốc lúc này. Vui lòng thử lại sau.");
    } finally {
      setDownloading(false);
    }
  }

  useEffect(() => {
    let active = true;
    listPublishedPolicyNotifications()
      .then((notifications) => {
        if (active) setItems(notifications);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSelectedItem(null);
      }
    }
    if (selectedItem) {
      window.addEventListener("keydown", handleKeyDown);
      return () => window.removeEventListener("keydown", handleKeyDown);
    }
  }, [selectedItem]);

  if (loading) {
    return (
      <div className="customer-notification-state">
        <Loader2 className="spin" /> Đang tải thông báo...
      </div>
    );
  }
  if (error) {
    return <div className="customer-notification-state">Không thể tải thông báo lúc này.</div>;
  }
  if (items.length === 0) {
    return <div className="customer-notification-state">Chưa có thông báo chính sách mới.</div>;
  }

  return (
    <>
      <div className="customer-notification-list">
        {items.map((item) => (
          <article
            aria-label={`Xem chi tiết chính sách: ${item.title}`}
            className="customer-notification-card"
            key={item.id}
            onClick={() => setSelectedItem(item)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setSelectedItem(item);
              }
            }}
            role="button"
            tabIndex={0}
            title="Nhấn để xem chi tiết chính sách"
          >
            <span className="customer-notification-icon">
              <BellRing size={21} />
            </span>
            <div className="customer-notification-body">
              <div className="customer-notification-header">
                <h2>{item.title}</h2>
                <span className="customer-notification-action-hint">
                  Xem chi tiết <ArrowRight size={14} />
                </span>
              </div>
              <p>{item.content}</p>
              <footer>
                <span>
                  <CalendarDays size={14} /> {formatDate(item.published_at)}
                </span>
                {item.affected_models.length ? (
                  <span>Áp dụng: {item.affected_models.join(", ")}</span>
                ) : null}
              </footer>
            </div>
          </article>
        ))}
      </div>

      {selectedItem ? (
        <div
          className="customer-policy-modal-backdrop"
          onClick={() => setSelectedItem(null)}
          role="dialog"
          aria-modal="true"
        >
          <div
            className="customer-policy-modal"
            onClick={(event) => event.stopPropagation()}
          >
            <header className="customer-policy-modal-header">
              <div className="customer-policy-modal-title-wrap">
                <span className="customer-policy-modal-badge">
                  <CheckCircle2 size={14} /> Chính sách chính thức
                </span>
                <h2>{selectedItem.title}</h2>
              </div>
              <button
                aria-label="Đóng"
                className="customer-policy-modal-close"
                onClick={() => setSelectedItem(null)}
                type="button"
              >
                <X size={20} />
              </button>
            </header>

            <div className="customer-policy-modal-meta">
              <div>
                <dt>Ngày công bố</dt>
                <dd>{formatDate(selectedItem.published_at)}</dd>
              </div>
              <div>
                <dt>Dòng xe áp dụng</dt>
                <dd>
                  {selectedItem.affected_models.length > 0
                    ? selectedItem.affected_models.join(", ")
                    : "Toàn bộ danh mục xe VinFast"}
                </dd>
              </div>
              {selectedItem.effective_from ? (
                <div>
                  <dt>Hiệu lực từ</dt>
                  <dd>{selectedItem.effective_from}</dd>
                </div>
              ) : null}
              {selectedItem.effective_to ? (
                <div>
                  <dt>Hiệu lực đến</dt>
                  <dd>{selectedItem.effective_to}</dd>
                </div>
              ) : null}
            </div>

            <div className="customer-policy-modal-content">
              <h3>
                <FileText size={16} /> Nội dung chi tiết
              </h3>
              <div className="customer-policy-text">
                {selectedItem.content.split("\n\n").map((para, index) => (
                  <p key={index}>{para}</p>
                ))}
              </div>

              {selectedItem.source_document_id ? (
                <div style={{ marginTop: "20px" }}>
                  <button
                    className="secondary-button"
                    disabled={downloading}
                    onClick={() => void handleDownloadOriginal(selectedItem.source_document_id!)}
                    style={{ width: "100%", justifyContent: "center", gap: "8px" }}
                    type="button"
                  >
                    {downloading ? <Loader2 className="spin" size={16} /> : <Download size={16} />}
                    Xem / Tải tài liệu gốc do Admin tải lên (.pdf / .docx)
                  </button>
                </div>
              ) : null}
            </div>

            <footer className="customer-policy-modal-footer">
              <Link
                className="primary-button"
                href={`/consultation?prompt=${encodeURIComponent(
                  selectedItem.affected_models.length > 0
                    ? `Tôi muốn tìm hiểu chi tiết về chính sách "${selectedItem.title}" cho xe ${selectedItem.affected_models.join(", ")}`
                    : `Tôi muốn tìm hiểu chi tiết về chính sách "${selectedItem.title}" của VinFast`,
                )}`}
              >
                <MessageSquare size={16} /> Hỏi Trợ lý AI về chính sách này
              </Link>
              <button
                className="secondary-button"
                onClick={() => setSelectedItem(null)}
                type="button"
              >
                Đóng
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </>
  );
}
