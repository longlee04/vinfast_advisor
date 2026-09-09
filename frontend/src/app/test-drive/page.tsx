import { BookingForm } from "@/components/booking/booking-form";
import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function TestDrivePage() {
  return <CustomerShell><div className="customer-wide-container"><PageHeading eyebrow="Trải nghiệm thực tế" title="Đặt lịch lái thử" description="Chọn mẫu xe, showroom và khung giờ thuận tiện trong ba bước ngắn." /><BookingForm /></div></CustomerShell>;
}
