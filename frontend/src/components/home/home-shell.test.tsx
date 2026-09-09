// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HomeShell } from "@/components/home/home-shell";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/",
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  // eslint-disable-next-line @next/next/no-img-element -- mock next/image trong test
  default: (props: React.ComponentProps<"img">) => <img alt="" {...props} />,
}));

// AppHeader đọc phiên đăng nhập — trang chủ trong test coi như khách vãng lai.
vi.mock("@/store/auth-store", () => ({
  useAuth: () => ({ status: "anonymous", user: null, profile: null, logout: vi.fn() }),
}));

describe("HomeShell", () => {
  beforeEach(() => cleanup());

  it("dùng cùng thanh trợ lý ngang như mọi trang khách, không còn nút tròn riêng", () => {
    render(<HomeShell><p>nội dung</p></HomeShell>);

    // Sếp 2026-08-29: khung chat phải thống nhất — trang chủ cũng là thanh gõ ngang.
    expect(screen.getByRole("complementary", { name: "Trợ lý tư vấn" })).toBeInTheDocument();
    expect(screen.getByLabelText("Câu hỏi cho trợ lý")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mở hỗ trợ/i })).not.toBeInTheDocument();
  });

  it("dùng MỘT header chung (AppHeader) như mọi trang khách, không còn header riêng", () => {
    render(<HomeShell><p>nội dung</p></HomeShell>);

    // Sếp: hai thanh điều hướng khác nhau giữa trang chủ và trang trong là lỗi
    // nặng — trang chủ phải dùng đúng AppHeader (mega-menu + tài khoản).
    expect(screen.getAllByRole("banner")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Ô tô" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /tài khoản/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /đặt lịch lái thử/i })[0]).toHaveAttribute("href", "/test-drive");
    // Chữ IN HOA của header cũ không còn.
    expect(screen.queryByText("ĐĂNG KÝ LÁI THỬ")).not.toBeInTheDocument();
  });

  it("header trang chủ chạy biến thể overlay để phủ lên hero", () => {
    render(<HomeShell><p>nội dung</p></HomeShell>);

    const header = screen.getByRole("banner");
    expect(header).toHaveAttribute("data-variant", "overlay");
    // Chưa cuộn (scrollY = 0) thì đang ở trạng thái trong suốt.
    expect(header).toHaveClass("is-overlay");
  });
});
