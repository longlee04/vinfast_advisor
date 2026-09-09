/**
 * Kiểu dữ liệu lịch lái thử của khách hàng — khớp `BookingListItemResponse`
 * (`src/agents/api/schemas.py`) và ràng buộc `ck_test_drive_bookings_status`
 * (`src/agents/models.py`): chỉ có đúng 3 trạng thái REQUESTED/CONFIRMED/CANCELLED.
 */

export type BookingStatus = "REQUESTED" | "CONFIRMED" | "CANCELLED";

export type BookingListItem = {
  readonly booking_id: string;
  readonly customer_id: string;
  readonly customer_name?: string | null;
  readonly phone?: string | null;
  readonly vehicle_id: string;
  readonly vehicle_name: string;
  readonly advisor_id?: string | null;
  readonly showroom: string;
  readonly scheduled_at: string;
  readonly status: BookingStatus;
  readonly created_at: string;
};
