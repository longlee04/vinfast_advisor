"use client";

import { Megaphone, Plus, X } from "lucide-react";
import { useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { internalNotices } from "@/mocks/admin";

export function NoticePreview() {
  const [dialogOpen, setDialogOpen] = useState(false);
  return (
    <>
      <section className="ops-panel"><div className="ops-panel-heading"><div><h2>Thông báo đã đăng</h2><p>Trạng thái đọc riêng theo tư vấn viên</p></div><button className="primary-button" onClick={() => setDialogOpen(true)} type="button"><Plus size={17} /> Tạo thông báo</button></div><div className="notice-list">{internalNotices.map((notice) => <article key={notice.id}><span className={notice.priority === "high" ? "notice-icon is-high" : "notice-icon"}><Megaphone size={18} /></span><div><div><h3>{notice.title}</h3><StatusBadge tone={notice.priority === "high" ? "danger" : "info"}>{notice.priority === "high" ? "Ưu tiên cao" : "Bình thường"}</StatusBadge></div><p>Tạo ngày {notice.createdAt} · {notice.readCount}/{notice.audienceCount} tư vấn viên đã đọc</p><div className="read-progress"><span style={{ width: `${(notice.readCount / notice.audienceCount) * 100}%` }} /></div></div></article>)}</div></section>
      {dialogOpen ? <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="notice-dialog-title"><button className="dialog-backdrop" aria-label="Đóng hộp thoại" onClick={() => setDialogOpen(false)} type="button" /><section className="mock-dialog"><div className="dialog-heading"><div><span className="eyebrow">Thông báo mới</span><h2 id="notice-dialog-title">Tạo thông báo nội bộ</h2></div><button className="icon-button" onClick={() => setDialogOpen(false)} aria-label="Đóng" type="button"><X size={19} /></button></div><label className="field-label">Tiêu đề<input placeholder="Nhập tiêu đề thông báo" /></label><label className="field-label">Mức ưu tiên<select><option>Bình thường</option><option>Cao</option></select></label><label className="field-label">Nội dung<textarea placeholder="Nhập nội dung..." /></label><div className="dialog-actions"><button className="secondary-button" onClick={() => setDialogOpen(false)} type="button">Huỷ</button><button className="primary-button" onClick={() => setDialogOpen(false)} type="button">Đăng thông báo</button></div></section></div> : null}
    </>
  );
}
