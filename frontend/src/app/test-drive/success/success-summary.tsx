import { CalendarCheck2, MapPin } from "lucide-react";
import Link from "next/link";

/** "2026-09-01" → "01/09/2026" — sai định dạng thì trả nguyên văn, không nổ. */
function formatDateVn(date: string): string {
  const [year, month, day] = date.split("-");
  return year && month && day ? `${day}/${month}/${year}` : date;
}

/**
 * Thân màn "Đặt lịch thành công".
 *
 * Dữ liệu là THẬT, do form đẩy sang qua query params khi đặt xong — bản cũ in
 * cứng "VF 6 Plus · VinFast Times City" cho mọi khách, ai đặt xe khác cũng thấy
 * thẻ bịa. Vào thẳng trang không có params (bookmark, gõ tay URL) thì hiện bản
 * chung chỉ đường vào Tài khoản, tuyệt đối không bịa lại.
 */
export function BookingSuccessSummary({
  date,
  showroom,
  time,
  vehicle,
}: Readonly<{ vehicle?: string; date?: string; time?: string; showroom?: string }>) {
  const hasBooking = Boolean(vehicle && date && time && showroom);
  return (
    <div className="booking-success">
      <span className="success-icon"><CalendarCheck2 size={38} /></span>
      <span className="eyebrow">Yêu cầu đã được ghi nhận</span>
      <h1>Đặt lịch thành công</h1>
      {hasBooking ? (
        <>
          <p>Tư vấn viên sẽ liên hệ xác nhận với anh/chị ạ.</p>
          <div className="success-booking-card">
            <div>
              <strong>{vehicle}</strong>
              <span>{formatDateVn(date as string)} · {time}</span>
            </div>
            <div>
              <MapPin size={18} />
              <span><strong>{showroom}</strong></span>
            </div>
          </div>
        </>
      ) : (
        <p>Đặt lịch thành công. Anh/chị kiểm tra trong Tài khoản → Lịch lái thử để xem chi tiết ạ.</p>
      )}
      <div>
        <Link className="secondary-button" href="/account">Xem lịch trong Tài khoản</Link>
        <Link className="primary-button" href="/">Về trang chủ</Link>
      </div>
    </div>
  );
}
