import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";
import { TcoCalculator } from "@/components/tco/tco-calculator";

export default function TcoPage() {
  return <CustomerShell><div className="customer-container"><PageHeading eyebrow="Chi phí sở hữu" title="Ước tính tổng chi phí sở hữu" description="Kết quả cập nhật khi bạn thay đổi mẫu xe hoặc các giả định sử dụng." /><TcoCalculator /></div></CustomerShell>;
}
