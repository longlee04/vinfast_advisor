import Link from "next/link";

import { VehicleComparison } from "@/components/comparison/vehicle-comparison";
import { CustomerShell } from "@/components/shared/customer-shell";
import { PageHeading } from "@/components/shared/page-heading";

export default function ComparePage() {
  return <CustomerShell><div className="customer-wide-container"><PageHeading eyebrow="So sánh cùng loại" title="Chọn lựa chọn phù hợp nhất" description="Các khác biệt quan trọng được nhóm để dễ đọc trên cả desktop và mobile." actions={<Link className="secondary-button" href="/recommendations">Chỉnh danh sách xe</Link>} /><VehicleComparison /></div></CustomerShell>;
}
