"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/store/auth-store";

/**
 * `NEXT_PUBLIC_DEMO_MODE` mặc định BẬT (mọi giá trị khác chuỗi "false") để giữ
 * nguyên hành vi demo hiện tại — /advisor, /admin chưa nối API thật (Khối 4
 * chưa tới lượt) nên chặn cứng bây giờ chỉ khoá UI trống không bảo vệ được gì.
 * Khi Khối 4 nối API thật, đặt `NEXT_PUBLIC_DEMO_MODE=false` để bật chặn theo
 * role thật từ `/me` — không cần sửa code, chỉ đổi biến môi trường.
 */
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";

export function RoleGuard({
  allow,
  children,
  loginPath = "/login",
}: Readonly<{
  allow: readonly string[];
  children: React.ReactNode;
  /**
   * Trang đăng nhập dành cho nhóm người dùng của khu vực này.
   *
   * Sếp 2026-08-26: `/admin` và `/advisor` khi chưa đăng nhập bị đẩy sang
   * `/login` — form của KHÁCH HÀNG. Nhân viên tới đó rồi loay hoay vì tài khoản
   * nội bộ không nằm trong luồng đăng nhập khách, và đó là lý do "không vào được
   * admin xem log". Khu vực nội bộ phải trỏ về `/staff-login`.
   */
  loginPath?: string;
}>) {
  const { status, user } = useAuth();
  const router = useRouter();
  const isAnonymous = status === "anonymous";

  useEffect(() => {
    if (!DEMO_MODE && isAnonymous) {
      router.replace(loginPath);
    }
  }, [isAnonymous, loginPath, router]);

  if (DEMO_MODE) return <>{children}</>;
  if (status === "loading" || isAnonymous) return null;

  if (user && !allow.includes(user.role)) {
    return (
      <div className="state-panel">
        <ShieldAlert size={34} />
        <h1>Không có quyền truy cập</h1>
        <p>Tài khoản của bạn không có quyền xem trang này.</p>
        <Link className="primary-button" href="/">
          Về trang chủ
        </Link>
      </div>
    );
  }

  return <>{children}</>;
}
