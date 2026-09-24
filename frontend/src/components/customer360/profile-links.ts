/** Đường tới hồ sơ khách — một chỗ, để hàng đợi/panel/bảng phiên không tự ghép URL. */
export function customerProfileHref(customerId: string, role: "advisor" | "admin" = "advisor"): string {
  return `/${role}/customers/${encodeURIComponent(customerId)}`;
}

/** Khi chỉ biết phiên (hàng đợi duyệt, nút thắt): trang trung gian tra ra khách. */
export function customerProfileFromSessionHref(sessionId: string): string {
  return `/advisor/customers/from-session/${encodeURIComponent(sessionId)}`;
}
