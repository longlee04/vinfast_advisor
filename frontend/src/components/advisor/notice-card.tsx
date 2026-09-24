"use client";

import { Megaphone } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { fetchNoticeList, markNoticeRead, type NoticeItem } from "@/lib/api/assignments";

/** Số thông báo hiện trên Tổng quan — chưa đọc trước, mới trước. */
const NOTICE_LIMIT = 5;

/**
 * Thông báo nội bộ (giá, ưu đãi, quy trình) ngay trên Tổng quan — thay trang "Chính sách nội
 * bộ" cũ vốn chỉ hiện dữ liệu giả. Dữ liệu thật từ `/agent/notices`, "Đã đọc" lưu ở backend.
 */
export function NoticeCard() {
  const [items, setItems] = useState<readonly NoticeItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    fetchNoticeList()
      .then((rows) => {
        setItems(rows);
        setFailed(false);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function markRead(noticeId: string) {
    await markNoticeRead(noticeId).catch(() => undefined);
    load();
  }

  const visible = [...(items ?? [])]
    .sort((a, b) => Number(a.read) - Number(b.read) || b.created_at.localeCompare(a.created_at))
    .slice(0, NOTICE_LIMIT);
  const unread = (items ?? []).filter((item) => !item.read).length;

  return (
    <section aria-labelledby="c360-notices-title" className="c360-card c360-section">
      <div className="c360-section-head">
        <h2 id="c360-notices-title">Thông báo nội bộ</h2>
        {unread ? <StatusBadge tone="info">{`${unread} chưa đọc`}</StatusBadge> : null}
      </div>
      {failed ? <p className="customer360-empty">Không tải được thông báo.</p> : null}
      {items !== null && items.length === 0 ? <p className="customer360-empty">Chưa có thông báo nào.</p> : null}
      {visible.length ? (
        <ul className="c360-notices">
          {visible.map((notice) => (
            <li data-read={notice.read || undefined} key={notice.notice_id}>
              <Megaphone aria-hidden="true" size={16} />
              <div>
                <strong>{notice.title}</strong>
                {notice.content ? <p>{notice.content}</p> : null}
                <small className="c360-muted">{new Date(notice.created_at).toLocaleDateString("vi-VN")}</small>
              </div>
              {!notice.read ? (
                <button className="text-button" onClick={() => void markRead(notice.notice_id)} type="button">
                  Đã đọc
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
