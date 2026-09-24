import { CustomerProfileRedirect } from "@/components/customer360/customer-profile-redirect";
import { OperationalShell } from "@/components/shared/operational-shell";

/** Hàng đợi duyệt / nút thắt chỉ biết `session_id` — trang này tra ra khách rồi chuyển sang hồ sơ. */
export default async function CustomerFromSessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return (
    <OperationalShell role="advisor">
      <CustomerProfileRedirect sessionId={sessionId} />
    </OperationalShell>
  );
}
