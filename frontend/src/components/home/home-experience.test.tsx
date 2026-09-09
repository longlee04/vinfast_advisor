// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HomeExperience } from "@/components/home/home-experience";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props}>{children}</a>,
}));

describe("HomeExperience", () => {
  beforeEach(() => {
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });

  it("renders the official homepage sections and complete product pagination", () => {
    render(<HomeExperience />);

    const cars = screen.getByRole("region", { name: "Ô tô điện VinFast" });
    const motorbikes = screen.getByRole("region", { name: "Xe máy điện VinFast" });

    expect(within(cars).getAllByRole("button", { name: /Xem mẫu ô tô/ })).toHaveLength(14);
    expect(within(motorbikes).getAllByRole("button", { name: /Xem mẫu xe máy điện/ })).toHaveLength(18);
    expect(screen.getByRole("heading", { name: "Phụ kiện xe" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thiết bị sạc di động" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bảo hành & Dịch vụ" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mãnh liệt Tinh thần Việt Nam - Vì Tương lai Xanh" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Đăng ký nhận thông tin" })).toBeInTheDocument();
  });

  it("có hàng lối tắt neo trong trang ngay dưới hero (các mục này không còn trên header)", () => {
    render(<HomeExperience />);

    const shortcuts = screen.getByRole("navigation", { name: "Lối tắt trong trang" });
    const links = within(shortcuts).getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/#green-future",
      "/#accessories",
      "/#service",
      "/#charging",
    ]);
  });
});
