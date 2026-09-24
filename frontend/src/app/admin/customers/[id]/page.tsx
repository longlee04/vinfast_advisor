import { CustomerProfilePage } from "@/components/customer360/customer-profile-page";
import { OperationalShell } from "@/components/shared/operational-shell";
import { customerIdFromParam } from "@/lib/customer-id";

/** Hồ sơ khách ở chế độ chỉ xem — không có trong menu Admin (plan §2.6). */
export default async function AdminCustomerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <OperationalShell role="admin">
      <CustomerProfilePage customerId={customerIdFromParam(id)} readOnly role="admin" />
    </OperationalShell>
  );
}
