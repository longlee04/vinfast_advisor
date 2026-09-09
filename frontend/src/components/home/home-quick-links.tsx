import Link from "next/link";

import styles from "@/components/home/home-quick-links.module.css";

/**
 * Hàng "lối tắt" neo trong trang, đặt NGAY DƯỚI hero trang chủ.
 *
 * Trước đây các mục này nằm trên header riêng của trang chủ — nhưng header phải
 * là MỘT thanh chung cho mọi trang (Sếp: hai thanh khác nhau là lỗi nặng), mà
 * các neo `#green-future`… chỉ có nghĩa ở trang chủ. Vậy chúng rời header,
 * thành một hàng nhỏ thuộc riêng nội dung trang chủ.
 */
const SHORTCUTS = [
  { label: "Giới thiệu", href: "/#green-future" },
  { label: "Phụ kiện xe", href: "/#accessories" },
  { label: "Dịch vụ hậu mãi", href: "/#service" },
  { label: "Pin và trạm sạc", href: "/#charging" },
] as const;

export function HomeQuickLinks() {
  return (
    <nav aria-label="Lối tắt trong trang" className={styles.row}>
      {SHORTCUTS.map((item) => (
        <Link href={item.href} key={item.label}>{item.label}</Link>
      ))}
    </nav>
  );
}
