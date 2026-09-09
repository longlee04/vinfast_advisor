// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as authApi from "@/lib/api/auth";

const push = vi.fn();
let nextParam: string | null = null;
let errorParam: string | null = null;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => ({
    get: (key: string) => {
      if (key === "next") return nextParam;
      if (key === "error") return errorParam;
      return null;
    },
  }),
}));

const login = vi.fn().mockResolvedValue(undefined);
const register = vi.fn().mockResolvedValue(undefined);

vi.mock("@/store/auth-store", () => ({
  useAuth: () => ({ login, register }),
}));

async function submitLogin() {
  const { AuthForm } = await import("./auth-form");
  render(<AuthForm mode="login" />);

  await userEvent.type(screen.getByPlaceholderText("you@gmail.com"), "khach@gmail.com");
  await userEvent.type(
    screen.getByPlaceholderText("Ít nhất 12 ký tự (gồm hoa, thường, số, ký tự đặc biệt)"),
    "MatKhauManh123!",
  );
  await userEvent.click(screen.getByRole("button", { name: /Đăng nhập/ }));
}

describe("AuthForm (login) — điểm đến sau đăng nhập", () => {
  afterEach(() => {
    cleanup();
    push.mockClear();
    login.mockClear();
    register.mockClear();
    nextParam = null;
    errorParam = null;
    vi.restoreAllMocks();
  });

  it("khách hàng không có ?next thì qua màn chào /welcome, không về thẳng /", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u1",
      email: "khach@gmail.com",
      role: "customer",
      state: "active",
    });

    await submitLogin();

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/welcome");
    });
  });

  it("khách hàng có ?next= hợp lệ thì đi thẳng theo deep-link, không qua /welcome", async () => {
    nextParam = "/tco";
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u1",
      email: "khach@gmail.com",
      role: "customer",
      state: "active",
    });

    await submitLogin();

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/tco");
    });
  });

  it("nhân viên (advisor) vẫn về /advisor như cũ, không đổi sang /welcome", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u2",
      email: "advisor@vinfast.vn",
      role: "advisor",
      state: "active",
    });

    await submitLogin();

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith("/advisor");
    });
  });
});

describe("AuthForm (login) — Google OAuth + dọn nút chết (đợt vá UI 2026-08-31)", () => {
  afterEach(() => {
    cleanup();
    errorParam = null;
    vi.restoreAllMocks();
  });

  it("có nút 'Tiếp tục với Google' trỏ thẳng endpoint backend, kèm dòng phân cách 'hoặc'", async () => {
    const { AuthForm } = await import("./auth-form");
    render(<AuthForm mode="login" />);

    expect(screen.getByRole("link", { name: /tiếp tục với google/i })).toHaveAttribute(
      "href",
      "/api/v1/auth/google/start",
    );
    expect(screen.getByText("hoặc")).toBeInTheDocument();
  });

  it("?error=google: báo lỗi Google đọc được, mời thử lại hoặc dùng email", async () => {
    errorParam = "google";
    const { AuthForm } = await import("./auth-form");
    render(<AuthForm mode="login" />);

    expect(
      screen.getByText("Đăng nhập Google không thành công, anh/chị thử lại hoặc dùng email ạ."),
    ).toBeInTheDocument();
  });

  it("KHÔNG còn nút chết: 'Quên mật khẩu?' (chưa có luồng) và 'Ghi nhớ phiên' (không nối gì)", async () => {
    const { AuthForm } = await import("./auth-form");
    render(<AuthForm mode="login" />);

    expect(screen.queryByText(/quên mật khẩu/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/ghi nhớ phiên/i)).not.toBeInTheDocument();
  });
});

describe("AuthForm (register) — validation email khớp thông điệp backend", () => {
  afterEach(() => {
    cleanup();
    register.mockClear();
    vi.restoreAllMocks();
  });

  async function submitRegister(email: string) {
    const { AuthForm } = await import("./auth-form");
    render(<AuthForm mode="register" />);
    await userEvent.type(screen.getByPlaceholderText("you@gmail.com"), email);
    await userEvent.type(
      screen.getByPlaceholderText("Ít nhất 12 ký tự (gồm hoa, thường, số, ký tự đặc biệt)"),
      "MatKhauManh123!",
    );
    await userEvent.click(screen.getByRole("button", { name: /Tạo tài khoản/ }));
  }

  it("Outlook được backend chấp nhận thì client KHÔNG được chặn (trước đây ép @gmail.com)", async () => {
    await submitRegister("khach@outlook.com");

    await waitFor(() => expect(register).toHaveBeenCalledWith("khach@outlook.com", "MatKhauManh123!"));
    expect(screen.queryByText(/@gmail\.com/)).not.toBeInTheDocument();
  });

  it("domain lạ: chặn tại client bằng ĐÚNG câu backend sẽ nói, không gọi API", async () => {
    await submitRegister("khach@congty.xyz");

    expect(
      screen.getByText("Nhà cung cấp email này chưa được hỗ trợ. Vui lòng dùng Gmail, Outlook, Yahoo hoặc iCloud."),
    ).toBeInTheDocument();
    expect(register).not.toHaveBeenCalled();
  });
});
