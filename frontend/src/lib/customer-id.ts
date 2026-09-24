/**
 * `customer_id` trong URL có thể là email (`%40`). Giải mã an toàn: chuỗi đã được Next
 * giải mã sẵn mà còn ký tự `%` lạc thì trả nguyên văn thay vì làm hỏng trang.
 * File riêng, không phụ thuộc gì, để route (server component) import được.
 */
export function customerIdFromParam(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}
