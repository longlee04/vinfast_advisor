"use client";

import { ArrowRight, KeyRound, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useState } from "react";

import { AuthApiError, me, staffApi } from "@/lib/api/auth";
import { AppHeader } from "@/components/shared/app-header";
import { useAuth } from "@/store/auth-store";

function staffRedirect(role: string): "/admin" | "/advisor" {
  return role.toLowerCase() === "admin" ? "/admin" : "/advisor";
}

/**
 * Lỗi đăng nhập nhân viên → câu nói được cho người đọc.
 *
 * Sếp 2026-08-26: "error message quá chung". Đã tách được những ca hệ thống phân
 * biệt thật; ba ca còn lại thì KHÔNG tách được, và đó là chủ ý:
 * `auth/presentation/staff_routes` gom "sai mật khẩu", "tài khoản bị khoá" và
 * "chưa xác thực" về cùng một `invalid_credentials`. Nói rõ tài khoản bị khoá là
 * xác nhận tài khoản đó CÓ TỒN TẠI — biến form đăng nhập thành công cụ dò danh
 * sách nhân viên. Muốn tách thì phải đổi hợp đồng ở backend trước, và cân nhắc
 * đánh đổi đó riêng.
 */
function staffErrorMessage(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.code === "weak_password") return "Mật khẩu mới chưa đủ mạnh.";
    if (error.status === 429) return "Bạn đã thử quá nhiều lần, vui lòng thử lại sau ít phút.";
    // 5xx là lỗi PHÍA HỆ THỐNG. Báo "sai mật khẩu" ở đây là đổ lỗi cho người
    // dùng vì một sự cố họ không gây ra, và họ sẽ gõ lại mật khẩu đúng nhiều lần
    // cho tới khi dính rate limit.
    if (error.status >= 500) return "Hệ thống đang bận, anh/chị thử lại sau ít phút giúp em ạ.";
    if (error.status === 0) return "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại giúp em ạ.";
  }
  // Không phải `AuthApiError` nghĩa là `fetch` ném trước khi có phản hồi — mất
  // mạng, DNS hỏng, server không lên. Cũng không phải lỗi mật khẩu.
  if (!(error instanceof AuthApiError)) {
    return "Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại giúp em ạ.";
  }
  return "Email hoặc mật khẩu không đúng.";
}

export default function StaffLoginPage() {
  const router = useRouter();
  const { adoptSession } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [mustSetPassword, setMustSetPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);

    try {
      if (mustSetPassword) {
        await staffApi.completePassword(email, password, newPassword);
      } else {
        await staffApi.login(email, password);
      }

      const currentUser = await me();
      if (!currentUser) {
        throw new AuthApiError("session_not_created", 401);
      }
      // Báo cho auth-store TRƯỚC khi chuyển trang: RoleGuard ở /admin//advisor
      // đọc store, không đọc cookie — thiếu bước này là bị đá ngược về đây ngay.
      await adoptSession(currentUser);
      router.replace(staffRedirect(currentUser.role));
    } catch (caught) {
      if (caught instanceof AuthApiError && caught.code === "temporary_password_required") {
        setMustSetPassword(true);
        setError("Tài khoản đang dùng mật khẩu tạm. Đặt mật khẩu mới để tiếp tục.");
      } else {
        setError(staffErrorMessage(caught));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AppHeader />
    <main className="auth-page">
      <section className="auth-visual">
        <div>
          <span className="eyebrow">Khu vực nội bộ</span>
          <h1>Hỗ trợ mỗi hành trình mua xe chính xác hơn.</h1>
          <p>Đăng nhập bằng tài khoản Advisor hoặc Admin để tiếp tục công việc của bạn.</p>
        </div>
        <small>VinFast AI Sales Advisor · Hệ thống dành cho nhân viên</small>
      </section>
      <section className="auth-form-panel">
        <span className="auth-wordmark">
          VINFAST <span>AI Sales Advisor</span>
        </span>
        <div className="auth-heading">
          <span className="eyebrow">{mustSetPassword ? "Bảo mật tài khoản" : "Đăng nhập nhân viên"}</span>
          <h2>{mustSetPassword ? "Đặt mật khẩu mới" : "Truy cập không gian làm việc"}</h2>
          <p>
            {mustSetPassword
              ? "Mật khẩu tạm chỉ dùng một lần. Chọn mật khẩu mới để kích hoạt tài khoản."
              : "Dùng email nhân viên và mật khẩu được cấp để đăng nhập."}
          </p>
        </div>
        <form className="auth-form" onSubmit={submit}>
          <label>
            Email
            <div>
              <Mail aria-hidden="true" size={18} />
              <input
                autoComplete="email"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="advisor@vinfast.vn"
                required
                type="email"
                value={email}
              />
            </div>
          </label>
          <label>
            {mustSetPassword ? "Mật khẩu tạm" : "Mật khẩu"}
            <div>
              <KeyRound aria-hidden="true" size={18} />
              <input
                autoComplete={mustSetPassword ? "one-time-code" : "current-password"}
                minLength={12}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Ít nhất 12 ký tự"
                required
                type="password"
                value={password}
              />
            </div>
          </label>
          {mustSetPassword ? (
            <label>
              Mật khẩu mới
              <div>
                <LockKeyhole aria-hidden="true" size={18} />
                <input
                  autoComplete="new-password"
                  minLength={12}
                  name="new-password"
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="Ít nhất 12 ký tự"
                  required
                  type="password"
                  value={newPassword}
                />
              </div>
            </label>
          ) : null}
          {mustSetPassword ? (
            <p className="password-hint">Tối thiểu 12 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt.</p>
          ) : null}
          {error ? (
            <p className="auth-error" role="alert">
              {error}
            </p>
          ) : null}
          <button className="primary-button auth-submit" disabled={busy} type="submit">
            {busy ? "Đang xử lý..." : mustSetPassword ? "Đặt mật khẩu mới" : "Đăng nhập"}
            <ArrowRight aria-hidden="true" size={18} />
          </button>
        </form>
        <p className="text-center text-xs text-slate-500 mt-4">
          Bạn là khách hàng?{" "}
          <Link className="text-blue-600 font-semibold hover:underline" href="/login">
            Đăng nhập khách hàng →
          </Link>
        </p>
        <div className="auth-api-note">
          <ShieldCheck aria-hidden="true" size={15} />
          Phiên đăng nhập được bảo vệ bằng cookie HttpOnly và CSRF.
        </div>
      </section>
    </main>
    </>
  );
}
