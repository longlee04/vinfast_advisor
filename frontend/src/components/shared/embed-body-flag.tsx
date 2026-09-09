"use client";

import { useEffect } from "react";

import { useEmbedMode } from "@/lib/use-embed-mode";

/**
 * Cắm trong root layout: khi trang chạy TRONG cửa sổ hội thoại (`?embed=1`,
 * iframe cùng domain) thì gắn `data-embed="1"` lên `<body>`.
 *
 * VÌ SAO cần cờ trên body thay vì từng component tự ẩn: header/dock/footer đã
 * tự ẩn qua `useEmbedMode()`, nhưng các trang chi tiết xe còn thanh nav NỘI BỘ
 * riêng (vd `.vf7-product-nav` có nút "Đăng ký lái thử") nằm ngay đầu trang —
 * nhúng vào cửa sổ thì nó trùng/đè ngay dưới thanh tiêu đề của cửa sổ (Sếp báo
 * trên VF 7). Sửa từng component là chín-mười chỗ phải nhớ; một cờ trên body +
 * một danh sách selector trong `globals.css` (`body[data-embed="1"] …`) là MỘT
 * chỗ duy nhất, trang mới thêm nav chỉ cần thêm selector.
 *
 * Trả `null`: component này chỉ có tác dụng phụ, không vẽ gì.
 */
export function EmbedBodyFlag() {
  const embedded = useEmbedMode();
  useEffect(() => {
    if (!embedded) return undefined;
    document.body.dataset.embed = "1";
    // Dọn khi rời embed (điều hướng client-side ra trang thường): không dọn thì
    // cờ dính lại và trang thường mất nav.
    return () => {
      delete document.body.dataset.embed;
    };
  }, [embedded]);
  return null;
}
