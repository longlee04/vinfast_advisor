import { redirect } from "next/navigation";

/** Thông báo nội bộ nằm trên "Tổng quan" (plan §17) — trang riêng cũ chỉ có dữ liệu giả. */
export default function AdvisorNoticesPage() {
  redirect("/advisor");
}
