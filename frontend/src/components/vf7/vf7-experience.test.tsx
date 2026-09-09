// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf7Experience } from "@/components/vf7/vf7-experience";

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

describe("Vf7Experience", () => {
  it("renders the official VF 7 hero, three prices and campaign heading", () => {
    render(<Vf7Experience />);

    expect(screen.getByAltText("VinFast VF 7 - Đam mê tạo phi thường")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/hero.webp",
    );
    expect(screen.getByText("703.000.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("788.500.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("807.500.000 VNĐ*")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", {
        name: "VF 7 là một bước tiến đột phá trong thiết kế xe ô tô của VinFast.",
      }),
    ).toBeInTheDocument();
  });

  it("changes to a separate official vehicle image for every selected color", () => {
    render(<Vf7Experience />);

    expect(screen.getByAltText("VinFast VF 7 màu Solar Ruby")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/color-solar-ruby.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Zenith Grey" }));
    expect(screen.getByAltText("VinFast VF 7 màu Zenith Grey")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/color-zenith-grey.webp",
    );
  });

  it("moves through the official highlight and masterpiece galleries", () => {
    render(<Vf7Experience />);

    expect(screen.getByAltText("Triết lý thiết kế Vũ Trụ Phi Đối Xứng")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/feature-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Điểm nổi bật tiếp theo" }));
    expect(screen.getByAltText("Trải nghiệm lái phấn khích")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/feature-3.webp",
    );

    expect(screen.getByAltText("VinFast VF 7 - tác phẩm nghệ thuật số 1")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/masterpiece-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Tác phẩm tiếp theo" }));
    expect(screen.getByAltText("VinFast VF 7 - tác phẩm nghệ thuật số 2")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf7/masterpiece-2.webp",
    );
  });

  it("keeps the vehicle picker closed until requested and closes it after navigation", () => {
    render(<Vf7Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(screen.getByRole("link", { name: "VF 8" })).toHaveAttribute("href", "/vehicles/vf-8");
    fireEvent.click(screen.getByRole("link", { name: "VF 8" }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "VF 8" })).not.toBeInTheDocument();
  });

  it("uses test-drive actions and shared support without the old deposit or registration form", () => {
    render(<Vf7Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    const testDriveLinks = screen.getAllByRole("link", { name: /đặt lịch lái thử/i });
    expect(testDriveLinks.length).toBeGreaterThan(2);
    testDriveLinks.forEach((link) => expect(link).toHaveAttribute("href", "/test-drive"));
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation"),
    );
  });
});
