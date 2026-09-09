import { Suspense } from "react";

import { AuthForm } from "@/components/auth/auth-form";
import { AppHeader } from "@/components/shared/app-header";

// Cùng lý do với /login: thanh điều hướng thống nhất trên mọi trang khách.
export default function RegisterPage() {
  return (
    <>
      <AppHeader />
      <Suspense fallback={null}>
        <AuthForm mode="register" />
      </Suspense>
    </>
  );
}
