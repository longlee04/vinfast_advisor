// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace }),
}));

const authState = { status: "anonymous" as string, user: null as { role: string } | null };

vi.mock("@/store/auth-store", () => ({
  useAuth: () => authState,
}));

// `globals` tắt trong vitest.config.ts nên phải tự cleanup.
afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  replace.mockClear();
  authState.status = "anonymous";
  authState.user = null;
});

async function renderGuard(props: { allow: string[]; loginPath?: string }) {
  // `DEMO_MODE` là hằng đọc lúc IMPORT module, và nó mặc định BẬT (mọi giá trị
  // khác chuỗi "false"). Bật thì guard trả thẳng children và không chặn gì —
  // nên phải đặt env rồi reset cache module TRƯỚC khi import, đúng như bản build
  // prod đang chạy (`NEXT_PUBLIC_DEMO_MODE=false` truyền qua build arg).
  vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "false");
  vi.resetModules();
  const { RoleGuard } = await import("@/components/shared/role-guard");
  render(
    <RoleGuard allow={props.allow} loginPath={props.loginPath}>
      <p>nội dung nội bộ</p>
    </RoleGuard>,
  );
}

describe("RoleGuard đẩy về ĐÚNG trang đăng nhập", () => {
  it("khu vực nội bộ đẩy về form nhân viên, không phải form khách", async () => {
    // Sếp 2026-08-26: `/admin` khi chưa đăng nhập bị đẩy sang `/login` — form của
    // KHÁCH HÀNG. Nhân viên tới đó rồi loay hoay vì tài khoản nội bộ không nằm
    // trong luồng đăng nhập khách. Đó là lý do "không vào được admin xem log".
    await renderGuard({ allow: ["admin"], loginPath: "/staff-login" });

    expect(replace).toHaveBeenCalledWith("/staff-login");
  });

  it("không truyền gì thì vẫn về form khách như cũ", async () => {
    // Mặc định phải giữ nguyên: khu vực của khách dùng chính `RoleGuard` này.
    await renderGuard({ allow: ["customer"] });

    expect(replace).toHaveBeenCalledWith("/login");
  });

  it("đăng nhập rồi nhưng sai vai thì báo hết quyền, KHÔNG đẩy đi đăng nhập lại", async () => {
    // Đẩy một người đã đăng nhập về form đăng nhập là vòng lặp: họ đăng nhập
    // đúng tài khoản của mình rồi lại bị đẩy về.
    authState.status = "authenticated";
    authState.user = { role: "advisor" };

    await renderGuard({ allow: ["admin"], loginPath: "/staff-login" });

    expect(replace).not.toHaveBeenCalled();
    expect(screen.getByText("Không có quyền truy cập")).toBeInTheDocument();
  });
});
