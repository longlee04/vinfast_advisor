import { Suspense } from "react";

import { AuthForm } from "@/components/auth/auth-form";
import { AppHeader } from "@/components/shared/app-header";

// Có thanh điều hướng như mọi trang khách (Sếp 2026-08-31: các trang không
// thống nhất thanh ngang) — khách vào thẳng /login vẫn có đường đi tiếp,
// không bị nhốt trong màn đăng nhập.
export default function LoginPage() {
  return (
    <>
      <AppHeader />
      <Suspense fallback={null}>
        <AuthForm mode="login" />
      </Suspense>
    </>
  );
}
