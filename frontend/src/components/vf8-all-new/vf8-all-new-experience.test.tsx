// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf8AllNewExperience } from "@/components/vf8-all-new/vf8-all-new-experience";

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

describe("Vf8AllNewExperience", () => {
  it("renders the dedicated campaign hero and headline specifications", () => {
    render(<Vf8AllNewExperience />);

    expect(screen.getByAltText("VinFast VF 8 Thế Hệ Mới")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/hero.webp",
    );
    expect(screen.getByRole("heading", { name: "Khi phong cách trở thành dấu ấn" })).toBeInTheDocument();
    expect(screen.getByText("170 kW")).toBeInTheDocument();
    expect(screen.getByText("330 Nm")).toBeInTheDocument();
    expect(screen.getByText("480–500 km")).toBeInTheDocument();
    expect(screen.getByText("60 kWh")).toBeInTheDocument();
  });

  it("switches between separate official images and keeps long color names visible", () => {
    render(<Vf8AllNewExperience />);

    expect(screen.getByAltText("VF 8 Thế Hệ Mới màu Solar Ruby")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/color-vf8ph-13.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Starburst Blue" }));
    expect(screen.getByAltText("VF 8 Thế Hệ Mới màu Starburst Blue")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/color-vf8ph-23.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Starburst Blue Body - Infinity Blanc Roof" }));
    expect(screen.getByText("Starburst Blue Body - Infinity Blanc Roof")).toBeVisible();
    expect(screen.getByAltText("VF 8 Thế Hệ Mới màu Starburst Blue Body - Infinity Blanc Roof")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/color-vf8ph-24.webp",
    );
  });

  it("moves through the daily technology carousel", () => {
    render(<Vf8AllNewExperience />);

    expect(screen.getByRole("heading", { name: "Kiến trúc điện - điện tử" })).toBeInTheDocument();
    expect(screen.getByAltText("Kiến trúc điện - điện tử VF 8 Thế Hệ Mới")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/technology-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Công nghệ tiếp theo" }));
    expect(screen.getByRole("heading", { name: "Hệ thống hỗ trợ lái nâng cao (ADAS)" })).toBeInTheDocument();
    expect(screen.getByAltText("Hệ thống hỗ trợ lái nâng cao ADAS")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf8-all-new/technology-2.webp",
    );
  });

  it("keeps the vehicle picker closed until requested and closes it after navigation", () => {
    render(<Vf8AllNewExperience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("link", { name: "VF 9" }));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("uses test-drive actions and shared support without deposit or registration forms", () => {
    render(<Vf8AllNewExperience />);

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
