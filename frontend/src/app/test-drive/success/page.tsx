import { BookingSuccessSummary } from "@/app/test-drive/success/success-summary";
import { CustomerShell } from "@/components/shared/customer-shell";

/**
 * Trang server: nhận dữ liệu THẬT của lượt đặt qua query params do form đẩy
 * sang (vehicle, date, time, showroom) — không còn thẻ bịa cứng.
 */
export default async function TestDriveSuccessPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const read = (key: string): string | undefined => {
    const value = params[key];
    return typeof value === "string" && value.trim() ? value : undefined;
  };
  return (
    <CustomerShell>
      <BookingSuccessSummary
        date={read("date")}
        showroom={read("showroom")}
        time={read("time")}
        vehicle={read("vehicle")}
      />
    </CustomerShell>
  );
}
