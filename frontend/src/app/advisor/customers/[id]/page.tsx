import { CustomerProfilePage } from "@/components/customer360/customer-profile-page";
import { OperationalShell } from "@/components/shared/operational-shell";
import { customerIdFromParam } from "@/lib/customer-id";

export default async function AdvisorCustomerProfilePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <OperationalShell role="advisor">
      <CustomerProfilePage customerId={customerIdFromParam(id)} readOnly={false} role="advisor" />
    </OperationalShell>
  );
}
