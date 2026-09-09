"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Liên kết nội bộ kèm CỬA SỔ XEM TRƯỚC: rê chuột vào là hiện một khung nhỏ của
 * chính trang đó, chưa cần bấm (Sếp 2026-08-25).
 *
 * Dùng `<iframe>` chứ không dựng một thẻ dữ liệu riêng: trang xe là trang của
 * CHÍNH web này (`/vehicles/<slug>`), nên khung xem trước luôn khớp với thứ
 * khách thấy sau khi bấm — không có bản sao thông tin thứ hai để lệch nhau.
 *
 * Ba ràng buộc, cả ba đều vì hiệu năng chứ không phải thẩm mỹ:
 *
 * - **Chỉ dựng iframe SAU khi rê đủ lâu** (`HOVER_DELAY_MS`). Lướt chuột ngang
 *   một đoạn văn có bảy liên kết mà nạp bảy trang là tự làm treo máy khách.
 * - **Rời chuột là gỡ hẳn iframe**, không giấu đi. Một iframe ẩn vẫn chạy script
 *   và giữ bộ nhớ.
 * - **`pointer-events: none`** trên khung: con trỏ không bao giờ "rơi vào" trang
 *   con, nên rời liên kết là đóng, không kẹt.
 *
 * `loading="lazy"` + `sandbox` hẹp: trang con chỉ cần hiển thị, không cần chạy
 * form hay mở cửa sổ.
 */

const HOVER_DELAY_MS = 350;

export function PreviewLink({
  href,
  children,
}: Readonly<{ href: string; children: React.ReactNode }>): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function cancel(): void {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }

  // Gỡ hẹn giờ khi component biến mất giữa chừng: khách rời màn chat trong lúc
  // đang đếm thì `setOpen` sau đó là cập nhật một component đã tháo.
  useEffect(() => cancel, []);

  function show(): void {
    cancel();
    timer.current = setTimeout(() => setOpen(true), HOVER_DELAY_MS);
  }

  function hide(): void {
    cancel();
    setOpen(false);
  }

  return (
    <span
      className="preview-link"
      onBlur={hide}
      onFocus={show}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <a className="inline-link" href={href}>
        {children}
      </a>
      {open ? (
        <span aria-hidden="true" className="preview-link-card">
          <iframe
            loading="lazy"
            sandbox="allow-same-origin allow-scripts"
            src={href}
            tabIndex={-1}
            title=""
          />
        </span>
      ) : null}
    </span>
  );
}
