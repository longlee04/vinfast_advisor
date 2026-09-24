/**
 * Thông tin cơ bản khách tự khai sau khi đăng nhập (plan Customer 360 §19): tên, SĐT, địa chỉ.
 *
 * Nguồn là hồ sơ auth (`PUT /auth/profile`); lưu xong báo agents chép NGAY sang phía tư vấn
 * viên (`POST /agent/customer-360/identity/refresh`) — không thì tư vấn viên vẫn thấy mã khách
 * cho tới lượt chat kế tiếp.
 */

import { refreshCustomerIdentity } from "@/lib/api/agent";
import { type UpdateProfilePayload, updateProfile, type UserProfile } from "@/lib/api/auth";

/** Đủ để tư vấn viên liên hệ: có tên và SĐT (địa chỉ không bắt buộc). */
export function isProfileComplete(profile: Pick<UserProfile, "full_name" | "phone_number"> | null | undefined): boolean {
  return Boolean(profile?.full_name?.trim() && profile?.phone_number?.trim());
}

/**
 * SĐT Việt Nam về dạng `0xxxxxxxxx` (10 số), hoặc `null` nếu không hợp lệ. Nhận cả dấu cách,
 * dấu chấm, gạch nối và đầu `+84`/`84`.
 */
export function normalizeVnPhone(raw: string): string | null {
  const digits = raw.replace(/[\s.\-()]/g, "");
  const local = digits.startsWith("+84") ? `0${digits.slice(3)}` : digits.startsWith("84") && digits.length === 11 ? `0${digits.slice(2)}` : digits;
  return /^0[35789]\d{8}$/.test(local) ? local : null;
}

/** Lưu hồ sơ rồi chép sang phía tư vấn viên. Bước chép hỏng không làm hỏng việc lưu. */
export async function saveCustomerProfile(payload: UpdateProfilePayload): Promise<UserProfile> {
  const updated = await updateProfile(payload);
  if (updated.role === "customer") await refreshCustomerIdentity().catch(() => undefined);
  return updated;
}
