// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Mpv7Experience } from "@/components/mpv7/mpv7-experience";

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

describe("Mpv7Experience", () => {
  it("renders the official MPV 7 gallery and changes real images", () => {
    render(<Mpv7Experience />);

    expect(screen.getByAltText("VinFast VF MPV 7 Solar Ruby nhìn từ phía trước")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/mpv7/gallery-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Ảnh tiếp theo" }));
    expect(screen.getByAltText("VinFast VF MPV 7 Solar Ruby nhìn từ phía sau")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/mpv7/gallery-2.webp",
    );
  });

  it("renders the official price and key specifications from the recording", () => {
    render(<Mpv7Experience />);

    expect(screen.getByText("712.500.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("4740 x 1872 x 1734")).toBeInTheDocument();
    expect(screen.getByText("450 km/lần sạc đầy")).toBeInTheDocument();
    expect(screen.getByText("60,13 kWh")).toBeInTheDocument();
    expect(screen.getByText("10,1 inch")).toBeInTheDocument();
  });

  it("calculates the monthly fuel advantage with editable values", () => {
    render(<Mpv7Experience />);

    fireEvent.change(screen.getByLabelText("Quãng đường di chuyển mỗi tháng"), { target: { value: "2000" } });
    fireEvent.change(screen.getByLabelText("Mức tiêu thụ nhiên liệu trên 100 km"), { target: { value: "7" } });
    fireEvent.change(screen.getByLabelText("Giá nhiên liệu mỗi lít"), { target: { value: "25000" } });
    fireEvent.click(screen.getByRole("button", { name: "So sánh" }));

    expect(screen.getByText("3.500.000 VNĐ")).toBeInTheDocument();
  });

  it("keeps the vehicle menu closed by default and closes it after choosing a car", () => {
    render(<Mpv7Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("link", { name: "VF 8" }));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("uses test-drive actions and shared support without deposit or registration forms", () => {
    render(<Mpv7Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    screen.getAllByRole("link", { name: /đặt lịch lái thử/i }).forEach((link) => {
      expect(link).toHaveAttribute("href", "/test-drive");
    });
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation"),
    );
  });
});
