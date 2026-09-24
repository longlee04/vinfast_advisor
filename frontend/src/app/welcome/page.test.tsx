// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as agentApi from "@/lib/api/agent";
import * as authApi from "@/lib/api/auth";
import { normalizeVnPhone } from "@/lib/api/customer-profile";

vi.mock("@/lib/api/agent", () => ({ refreshCustomerIdentity: vi.fn().mockResolvedValue({ refreshed: true }) }));

const replace = vi.fn();
// Router phải là MỘT object ổn định như router thật của Next. Bản cũ trả
// `({ replace })` mới mỗi lần render, nên effect `[router]` của trang chạy lại
// sau khi cờ "đã chào" vừa được ghi vào sessionStorage → `replace("/")` — test
// đỏ vì chính mock, không phải vì trang.
const router = { replace };

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => router,
}));

// Trang giờ mang thanh điều hướng chung (Sếp 2026-08-31: thống nhất thanh
// ngang). Header thật cần AuthProvider + đủ store — không phải thứ test màn
// chào muốn dựng, nên thế bằng vai đóng thế có testid để vẫn khẳng định được
// "trang có thanh ngang".
vi.mock("@/components/shared/app-header", () => ({
  AppHeader: () => <div data-testid="app-header" />,
}));

describe("WelcomePage", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.localStorage.clear();
    replace.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("chào tên khách (từ hồ sơ) và hiện đủ ba lối vào cùng nút bỏ qua", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u1",
      email: "khach@gmail.com",
      role: "customer",
      state: "active",
    });
    vi.spyOn(authApi, "getProfile").mockResolvedValue({
      id: "u1",
      email: "khach@gmail.com",
      role: "customer",
      full_name: "Nguyễn Văn A",
      phone_number: "0912345678",
      address: null,
      showroom_name: null,
      avatar_url: null,
      vehicle_preference: null,
      budget_preference: null,
      seats_preference: null,
      home_charging: null,
      title: null,
      bio: null,
    });

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    await waitFor(() => {
      expect(screen.getByText(/Chào Nguyễn Văn A, rất vui được gặp/)).toBeInTheDocument();
    });

    expect(screen.getByRole("link", { name: /Tư vấn chọn xe theo nhu cầu/ })).toHaveAttribute(
      "href",
      "/consultation",
    );
    expect(screen.getByRole("link", { name: /Xem các mẫu xe/ })).toHaveAttribute("href", "/vehicles");
    expect(screen.getByRole("link", { name: /Lịch lái thử của tôi/ })).toHaveAttribute(
      "href",
      "/account#test-drive-bookings",
    );
    expect(screen.getByRole("link", { name: "Bỏ qua" })).toHaveAttribute("href", "/");

    expect(replace).not.toHaveBeenCalled();
  });

  it("chưa có tên hồ sơ thì dùng phần trước @ của email làm tên chào", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u2",
      email: "minhkhang@gmail.com",
      role: "customer",
      state: "active",
    });
    vi.spyOn(authApi, "getProfile").mockResolvedValue(null);

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Để sau" }));
    await waitFor(() => {
      expect(screen.getByText(/Chào minhkhang, rất vui được gặp/)).toBeInTheDocument();
    });
  });

  it("lần đăng nhập đầu (chưa từng thấy email này) thì KHÔNG có chữ 'lại'", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({
      id: "u3",
      email: "lanmoi@gmail.com",
      role: "customer",
      state: "active",
    });
    vi.spyOn(authApi, "getProfile").mockResolvedValue(null);

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Để sau" }));
    await waitFor(() => {
      expect(screen.getByText("Chào lanmoi, rất vui được gặp")).toBeInTheDocument();
    });
  });

  it("chưa đăng nhập (me() thất bại) thì đẩy về /login", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue(null);
    vi.spyOn(authApi, "getProfile").mockResolvedValue(null);

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/login");
    });
  });

  it("đã xem màn chào trong phiên này rồi thì vào lại /welcome sẽ đẩy thẳng về /", async () => {
    window.sessionStorage.setItem("p150.welcomed", "1");
    const meSpy = vi.spyOn(authApi, "me");

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/");
    });
    // Đã có cờ "đã xem" thì không cần gọi lại `/auth/me` — kiểm tra cờ trước.
    expect(meSpy).not.toHaveBeenCalled();
  });

  it("trang chào có thanh điều hướng chung", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({ user: { email: "an@example.com" } } as never);
    vi.spyOn(authApi, "getProfile").mockResolvedValue({ full_name: "An" } as never);
    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);
    await waitFor(() => expect(screen.getByTestId("app-header")).toBeInTheDocument());
  });

  it("hồ sơ thiếu SĐT: xin tên/SĐT/địa chỉ, kiểm SĐT, lưu rồi báo tư vấn viên ngay (plan §19)", async () => {
    vi.spyOn(authApi, "me").mockResolvedValue({ id: "u9", email: "moi@gmail.com", role: "customer", state: "active" });
    vi.spyOn(authApi, "getProfile").mockResolvedValue({ full_name: "Trần B", phone_number: null } as never);
    const save = vi.spyOn(authApi, "updateProfile").mockResolvedValue({
      full_name: "Trần Bình",
      phone_number: "0912345678",
      address: "12 Láng Hạ",
      role: "customer",
    } as never);

    const { default: WelcomePage } = await import("./page");
    render(<WelcomePage />);

    expect(await screen.findByRole("heading", { name: "Cho em xin vài thông tin cơ bản" })).toBeInTheDocument();
    expect(screen.getByLabelText("Họ và tên")).toHaveValue("Trần B");
    fireEvent.change(screen.getByLabelText("Họ và tên"), { target: { value: "Trần Bình" } });
    fireEvent.change(screen.getByLabelText("Số điện thoại"), { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu và tiếp tục" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Số điện thoại chưa đúng");
    expect(save).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Số điện thoại"), { target: { value: "+84 912 345 678" } });
    fireEvent.change(screen.getByLabelText(/Địa chỉ/), { target: { value: " 12 Láng Hạ " } });
    fireEvent.click(screen.getByRole("button", { name: "Lưu và tiếp tục" }));

    await waitFor(() => expect(screen.getByText(/Chào Trần Bình, rất vui được gặp/)).toBeInTheDocument());
    expect(save).toHaveBeenCalledWith({ full_name: "Trần Bình", phone_number: "0912345678", address: "12 Láng Hạ" });
    expect(agentApi.refreshCustomerIdentity).toHaveBeenCalled();
  });

  it("chuẩn hoá SĐT Việt Nam", () => {
    expect(normalizeVnPhone("0912 345 678")).toBe("0912345678");
    expect(normalizeVnPhone("+84 912.345.678")).toBe("0912345678");
    expect(normalizeVnPhone("84912345678")).toBe("0912345678");
    expect(normalizeVnPhone("0212345678")).toBeNull();
    expect(normalizeVnPhone("091234")).toBeNull();
  });
});
