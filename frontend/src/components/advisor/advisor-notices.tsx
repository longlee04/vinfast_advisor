"use client";

import { Check, Megaphone } from "lucide-react";
import { useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { internalNotices } from "@/mocks/admin";

export function AdvisorNotices() {
  const [readIds, setReadIds] = useState<string[]>(["notice-2"]);
  return <section className="ops-panel"><div className="ops-panel-heading"><div><h2>Thông báo dành cho Advisor</h2><p>Cập nhật giá, ưu đãi và quy trình nội bộ từ Admin</p></div><StatusBadge tone="info">{internalNotices.length - readIds.length} chưa đọc</StatusBadge></div><div className="advisor-notice-list">{internalNotices.map((notice) => { const read = readIds.includes(notice.id); return <article className={read ? "is-read" : ""} key={notice.id}><span className={notice.priority === "high" ? "notice-icon is-high" : "notice-icon"}><Megaphone size={19} /></span><div><div><h3>{notice.title}</h3><StatusBadge tone={notice.priority === "high" ? "danger" : "info"}>{notice.priority === "high" ? "Ưu tiên cao" : "Chính sách"}</StatusBadge></div><p>Đăng ngày {notice.createdAt}. Advisor cần đối chiếu thông tin này trước khi duyệt đề xuất liên quan.</p></div><button className={read ? "secondary-button" : "primary-button"} onClick={() => setReadIds((current) => read ? current.filter((id) => id !== notice.id) : [...current, notice.id])} type="button">{read ? "Đánh dấu chưa đọc" : <><Check size={16} /> Đã đọc</>}</button></article>; })}</div></section>;
}
