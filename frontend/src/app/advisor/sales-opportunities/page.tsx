import { redirect } from "next/navigation";

/** Đã gộp vào "Khách hàng" (plan §17) — giữ đường cũ cho link/bookmark. */
export default function AdvisorSalesOpportunitiesPage() {
  redirect("/advisor/customers");
}
