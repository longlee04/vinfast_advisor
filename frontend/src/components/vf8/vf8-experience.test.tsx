// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf8Experience } from "@/components/vf8/vf8-experience";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

afterEach(cleanup);

describe("Vf8Experience", () => {
  it("renders the official hero, prices and overview heading", () => {
    render(<Vf8Experience />);

    expect(screen.getByAltText("VinFast VF 8 trên đường phố")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/hero.webp",
    );
    expect(screen.getByText("853.100.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("1.025.050.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thiết kế cá nhân hoá" })).toBeInTheDocument();
  });

  it("changes to a separate official vehicle image for every selected color", () => {
    render(<Vf8Experience />);

    expect(screen.getByAltText("VinFast VF 8 màu Jet Black")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/color-jet-black.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Infinity Blanc" }));
    expect(screen.getByAltText("VinFast VF 8 màu Infinity Blanc")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/color-infinity-blanc.webp",
    );
    expect(screen.getByText("Infinity Blanc")).toBeVisible();
  });

  it("moves through the interior gallery and switches technology tabs", () => {
    render(<Vf8Experience />);

    expect(screen.getByAltText("Khoang nội thất VinFast VF 8")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/interior-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Nội thất tiếp theo" }));
    expect(screen.getByAltText("Bảng điều khiển VinFast VF 8")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/interior-2.webp",
    );

    fireEvent.click(screen.getByRole("tab", { name: "Ứng dụng VinFast" }));
    expect(screen.getByAltText("Ứng dụng VinFast trên VF 8")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8/technology-app.webp",
    );
  });

  it("keeps the vehicle picker closed until requested and closes it after navigation", () => {
    render(<Vf8Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("link", { name: "VF 9" }));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("uses test-drive actions and shared support without deposit or registration forms", () => {
    render(<Vf8Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    const testDriveLinks = screen.getAllByRole("link", { name: /đặt lịch lái thử|đăng ký lái thử/i });
    expect(testDriveLinks.length).toBeGreaterThan(2);
    testDriveLinks.forEach((link) => expect(link).toHaveAttribute("href", "/test-drive"));
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation"),
    );
  });
});
