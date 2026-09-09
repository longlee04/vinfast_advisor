import { PolicyNotifications } from "@/components/customer/policy-notifications";
import { CustomerShell } from "@/components/shared/customer-shell";

export default function NotificationsPage() {
  return (
    <CustomerShell>
      <section className="customer-notification-page">
        <span className="eyebrow">Cập nhật dành cho khách hàng</span>
        <h1>Thông báo chính sách</h1>
        <p>Các nội dung dưới đây đã được đội ngũ VinFast kiểm tra và công bố.</p>
        <PolicyNotifications />
      </section>
    </CustomerShell>
  );
}
