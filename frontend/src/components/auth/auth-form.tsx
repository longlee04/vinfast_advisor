"use client";

import { ArrowRight, CheckCircle2, Eye, EyeOff, LockKeyhole, Mail } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

import { AuthApiError, me } from "@/lib/api/auth";
import { useAuth } from "@/store/auth-store";

type AuthMode = "login" | "register";

/**
 * Câu cho khách đọc, theo từng mã backend trả về.
 *
 * Mã mật khẩu là một HỌ (`password_too_short`, `password_missing_character_class`…)
 * nên khớp theo tiền tố: thêm một luật mật khẩu ở backend không được biến câu
 * báo lỗi thành "không thể kết nối máy chủ".
 */
const AUTH_ERROR_MESSAGES: Record<string, string> = {
  invalid_credentials: "Email hoặc mật khẩu không đúng.",
  origin_forbidden: "Yêu cầu bị chặn do cấu hình máy chủ, báo kỹ thuật hỗ trợ.",
  email_domain_not_allowed: "Nhà cung cấp email này chưa được hỗ trợ. Vui lòng dùng Gmail, Outlook, Yahoo hoặc iCloud.",
  invalid_email: "Địa chỉ email chưa đúng định dạng.",
  password_too_short: "Mật khẩu quá ngắn, cần ít nhất 12 ký tự.",
  password_too_long: "Mật khẩu quá dài, vui lòng rút ngắn lại.",
  password_missing_character_class: "Mật khẩu cần có cả chữ hoa, chữ thường, số và ký tự đặc biệt.",
  password_contains_control_character: "Mật khẩu chứa ký tự không hợp lệ.",
  user_exists: "Email này đã được đăng ký tài khoản.",
  registration_unavailable: "Chưa đăng ký được lúc này, vui lòng thử lại sau ít phút.",
};

/**
 * Nhà cung cấp email backend chấp nhận — PHẢN CHIẾU luật của Auth API để chặn
 * sớm với ĐÚNG câu backend sẽ nói (`email_domain_not_allowed`). Client cũ ép
 * cứng "@gmail.com" trong khi backend nhận cả Outlook/Yahoo/iCloud: khách hợp
 * lệ bị chặn oan ngay trước cửa. Nếu hai bên lệch nhau, backend vẫn là chuẩn —
 * câu lỗi nó trả về đã có trong AUTH_ERROR_MESSAGES.
 */
const ALLOWED_EMAIL_DOMAINS = [
  "gmail.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "yahoo.com",
  "icloud.com",
  "me.com",
] as const;

function isAllowedEmailDomain(email: string): boolean {
  const domain = email.toLowerCase().split("@")[1] ?? "";
  return (ALLOWED_EMAIL_DOMAINS as readonly string[]).includes(domain);
}

/** Logo Google 4 màu, inline — không tải ảnh ngoài. */
function GoogleIcon() {
  return (
    <svg aria-hidden="true" height="18" viewBox="0 0 48 48" width="18">
      <path d="M43.6 20.1H42V20H24v8h11.3C33.7 32.7 29.2 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.1 6.1 29.3 4 24 4 13 4 4 13 4 24s9 20 20 20 20-9 20-20c0-1.3-.1-2.6-.4-3.9z" fill="#FFC107" />
      <path d="m6.3 14.7 6.6 4.8C14.7 15.1 19 12 24 12c3.1 0 5.9 1.2 8 3l5.7-5.7C34.1 6.1 29.3 4 24 4 16.3 4 9.7 8.3 6.3 14.7z" fill="#FF3D00" />
      <path d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35.1 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" fill="#4CAF50" />
      <path d="M43.6 20.1H42V20H24v8h11.3c-.8 2.2-2.2 4.2-4.1 5.6l6.2 5.2C41.4 34.9 44 30 44 24c0-1.3-.1-2.6-.4-3.9z" fill="#1976D2" />
    </svg>
  );
}

function errorMessage(error: unknown): string {
  if (error instanceof AuthApiError) {
    if (error.status === 429) return "Bạn đã thử quá nhiều lần, vui lòng thử lại sau ít phút.";
    const known = AUTH_ERROR_MESSAGES[error.code];
    if (known) return known;
    if (error.code.startsWith("password_")) return "Mật khẩu chưa đạt yêu cầu, vui lòng chọn mật khẩu khác.";
  }
  return "Không thể kết nối máy chủ, vui lòng thử lại sau.";
}

export function AuthForm({ mode }: Readonly<{ mode: AuthMode }>) {
  const isRegister = mode === "register";
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, register } = useAuth();
  const [showPassword, setShowPassword] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Quay về từ Google với `?error=google` (backend redirect khi OAuth hỏng):
  // báo một câu đọc được thay vì trang đăng nhập im lặng như chưa có gì xảy ra.
  // Lỗi do khách vừa thao tác (submit form) luôn được ưu tiên hiển thị.
  const googleError =
    !isRegister && searchParams.get("error") === "google"
      ? "Đăng nhập Google không thành công, anh/chị thử lại hoặc dùng email ạ."
      : null;
  const shownError = error ?? googleError;

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");

    setError(null);

    if (isRegister) {
      if (!isAllowedEmailDomain(email)) {
        // Cùng nguyên văn với backend (`email_domain_not_allowed`) — khách thấy
        // MỘT câu dù bị chặn ở client hay server.
        setError(AUTH_ERROR_MESSAGES.email_domain_not_allowed);
        return;
      }
      if (password.length < 12) {
        setError("Mật khẩu phải có ít nhất 12 ký tự.");
        return;
      }
      if (!/[A-Z]/.test(password)) {
        setError("Mật khẩu phải có ít nhất 1 chữ in hoa (A-Z).");
        return;
      }
      if (!/[a-z]/.test(password)) {
        setError("Mật khẩu phải có ít nhất 1 chữ thường (a-z).");
        return;
      }
      if (!/[0-9]/.test(password)) {
        setError("Mật khẩu phải có ít nhất 1 chữ số (0-9).");
        return;
      }
      if (!/[^A-Za-z0-9]/.test(password)) {
        setError("Mật khẩu phải có ít nhất 1 ký tự đặc biệt (@, #, $, %, v.v.).");
        return;
      }
    }

    setLoading(true);
    try {
      if (isRegister) {
        await register(email, password);
        setSubmitted(true);
      } else {
        await login(email, password);
        const currentUser = await me();
        if (currentUser?.role === "admin") {
          router.push("/admin");
        } else if (currentUser?.role === "advisor") {
          router.push("/advisor");
        } else {
          // Khách hàng: có `?next=` (deep-link nội bộ) thì đi thẳng theo đó, giữ
          // nguyên hành vi cũ khi bị chặn quay lại một trang cụ thể. Không có thì
          // qua màn chào trước, không về thẳng trang chính như trước nữa.
          const next = searchParams.get("next");
          router.push(next && next.startsWith("/") ? next : "/welcome");
        }
      }
    } catch (submitError) {
      setError(errorMessage(submitError));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-visual">
        <div>
          <span className="eyebrow">VinFast AI Sales Advisor</span>
          <h1>{isRegister ? "Bắt đầu hành trình phù hợp với bạn." : "Chào mừng bạn quay trở lại."}</h1>
          <p>Lưu hồ sơ nhu cầu, theo dõi đề xuất đã duyệt và quản lý lịch lái thử trong một tài khoản.</p>
        </div>
      </section>
      <section className="auth-form-panel">
        <Link className="auth-wordmark" href="/">
          VINFAST <span>AI Sales Advisor</span>
        </Link>
        {submitted ? (
          <div className="auth-ready-state">
            <CheckCircle2 size={44} />
            <h2>Yêu cầu đăng ký đã được gửi</h2>
            <p>Tài khoản đã được tạo ở trạng thái <strong>Chờ xác nhận</strong>. Admin sẽ xác nhận và kích hoạt tài khoản của bạn.</p>
            <button className="secondary-button" onClick={() => setSubmitted(false)} type="button">
              Đăng ký tài khoản khác
            </button>
            <Link className="primary-button" href="/login">
              Đến trang đăng nhập
            </Link>
          </div>
        ) : (
          <>
            <div className="auth-heading">
              <span className="eyebrow">{isRegister ? "Tạo tài khoản" : "Đăng nhập"}</span>
              <h2>{isRegister ? "Đăng ký để lưu hành trình" : "Truy cập tài khoản của bạn"}</h2>
              <p>
                {isRegister
                  ? "Tài khoản khách hàng (Gmail, Outlook, Yahoo hoặc iCloud) sẽ ở trạng thái Chờ xác nhận."
                  : "Dùng email và mật khẩu đã đăng ký."}
              </p>
            </div>
            <form className="auth-form" onSubmit={submit}>
              <label>
                Email
                <div>
                  <Mail size={18} />
                  <input autoComplete="email" name="email" placeholder="you@gmail.com" required type="email" />
                </div>
              </label>
              <label>
                Mật khẩu
                <div>
                  <LockKeyhole size={18} />
                  <input
                    autoComplete={isRegister ? "new-password" : "current-password"}
                    minLength={12}
                    name="password"
                    placeholder="Ít nhất 12 ký tự (gồm hoa, thường, số, ký tự đặc biệt)"
                    required
                    type={showPassword ? "text" : "password"}
                  />
                  <button
                    aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                    onClick={() => setShowPassword((current) => !current)}
                    type="button"
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </label>
              {/* "Ghi nhớ phiên" và "Quên mật khẩu?" đã BỎ: chưa nối vào luồng
                  nào — nút chết chỉ làm khách mất niềm tin (đợt vá 2026-08-31). */}
              {isRegister ? (
                <p className="password-hint">Tối thiểu 12 ký tự: chữ hoa (A-Z), chữ thường (a-z), số (0-9) và ký tự đặc biệt (@, #, $...).</p>
              ) : null}
              {shownError ? (
                <p className="auth-error" role="alert">
                  {shownError}
                </p>
              ) : null}
              <button className="primary-button auth-submit" disabled={loading} type="submit">
                {loading ? "Đang xử lý..." : isRegister ? "Tạo tài khoản" : "Đăng nhập"}
                <ArrowRight size={18} />
              </button>
            </form>
            {/* Google OAuth: <a> trỏ thẳng endpoint backend (trình duyệt phải
                RỜI trang sang Google — fetch/router không làm được việc này).
                Backend đang được làm song song, đường dẫn đã chốt. */}
            <div aria-hidden="true" className="auth-divider">hoặc</div>
            <a className="auth-google-button" href="/api/v1/auth/google/start">
              <GoogleIcon />
              Tiếp tục với Google
            </a>
            <p className="auth-switch-copy">
              {isRegister ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
              <Link href={isRegister ? "/login" : "/register"}>{isRegister ? "Đăng nhập" : "Đăng ký ngay"}</Link>
            </p>
            {!isRegister ? (
              <p className="text-center text-xs text-slate-500 mt-2">
                Bạn là nhân viên VinFast?{" "}
                <Link className="text-blue-600 font-semibold hover:underline" href="/staff-login">
                  Đăng nhập Advisor / Admin →
                </Link>
              </p>
            ) : null}
            <div className="auth-api-note">
              <LockKeyhole size={15} />
              Cookie HttpOnly và CSRF do backend Auth quản lý.
            </div>
          </>
        )}
      </section>
    </main>
  );
}
