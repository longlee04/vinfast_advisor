import { CustomerHistory } from "@/components/customer/customer-history";
import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function AccountPage() {
  return <CustomerShell><div className="customer-wide-container"><PageHeading eyebrow="Tài khoản khách hàng" title="Tài khoản của bạn" description="Quản lý hồ sơ nhu cầu, đề xuất đã duyệt, bảng so sánh và lịch lái thử trong cùng một nơi." /><CustomerHistory /></div></CustomerShell>;
}
