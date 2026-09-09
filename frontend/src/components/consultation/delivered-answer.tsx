"use client";

import { ShieldCheck } from "lucide-react";

/**
 * Phần kèm theo của nội dung đã duyệt: nhãn xác nhận và bảng so sánh.
 *
 * Không lặp lại phần văn bản — nó đã nằm trong dòng hội thoại như một tin nhắn
 * của trợ lý, in thêm lần nữa ở đây sẽ thành hai bản cùng nội dung trên màn hình.
 */
export function DeliveredAnswer({ imageBase64 }: Readonly<{ imageBase64: string | null }>) {
  return (
    <div className="delivered-answer">
      <span className="eyebrow">
        <ShieldCheck size={16} /> Đã được tư vấn viên duyệt
      </span>
      {imageBase64 ? (
        // eslint-disable-next-line @next/next/no-img-element -- ảnh là base64 tại chỗ, không có URL cho next/image
        <img
          alt="Bảng so sánh các mẫu xe được đề xuất"
          className="comparison-image"
          src={`data:image/png;base64,${imageBase64}`}
        />
      ) : null}
    </div>
  );
}
