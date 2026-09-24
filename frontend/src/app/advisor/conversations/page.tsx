import { redirect } from "next/navigation";

/** "Hội thoại" đã gộp vào "Khách hàng" (plan §18) — hội thoại xem theo từng khách. */
export default function AdvisorConversationsPage() {
  redirect("/advisor/customers");
}
