// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf6Experience } from "@/components/vf6/vf6-experience";

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

describe("Vf6Experience", () => {
  it("renders the official 2026 VF 6 campaign imagery, prices and highlights", () => {
    render(<Vf6Experience />);

    expect(screen.getByAltText("VinFast VF 6 - Cùng bạn ghi dấu từng khoảnh khắc")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf6/hero.webp",
    );
    expect(screen.getByText("613.700.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("664.050.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("59,6 kW")).toBeInTheDocument();
    expect(screen.getByText("485 km/lần sạc")).toBeInTheDocument();
    expect(screen.getByText("150 kW/201 hp")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Triết lý thiết kế “Cặp đối lập tự nhiên”" }),
    ).toBeInTheDocument();
  });

  it("changes the official exterior and gallery images when their controls are used", () => {
    render(<Vf6Experience />);

    expect(screen.getByAltText("Ngoại thất VinFast VF 6 nhìn từ phía trước")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf6/exterior-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Ngoại thất tiếp theo" }));
    expect(screen.getByAltText("Ngoại thất VinFast VF 6 nhìn từ phía sau")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf6/exterior-2.webp",
    );

    expect(screen.getByAltText("VinFast VF 6 trên cung đường ven núi")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf6/gallery-1.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Ảnh tiếp theo" }));
    expect(screen.getByAltText("VinFast VF 6 giữa thiên nhiên")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf6/gallery-2.webp",
    );
  });

  it("keeps the vehicle picker closed until requested and closes it after navigation", () => {
    render(<Vf6Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(screen.getByRole("link", { name: "VF 7" })).toHaveAttribute("href", "/vehicles/vf-7");
    fireEvent.click(screen.getByRole("link", { name: "VF 7" }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "VF 7" })).not.toBeInTheDocument();
  });

  it("uses test-drive actions and the shared support choices without old deposit or form copy", () => {
    render(<Vf6Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    const testDriveLinks = screen.getAllByRole("link", { name: /đặt lịch lái thử/i });
    expect(testDriveLinks.length).toBeGreaterThan(1);
    testDriveLinks.forEach((link) => expect(link).toHaveAttribute("href", "/test-drive"));
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation"),
    );
  });

  it("calculates the monthly petrol comparison from the entered values", () => {
    render(<Vf6Experience />);

    fireEvent.change(screen.getByLabelText("Mức tiêu thụ nhiên liệu"), { target: { value: "8" } });
    fireEvent.change(screen.getByLabelText("Quãng đường mỗi tháng"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "TÍNH CHI PHÍ" }));

    expect(screen.getByText("1.764.800 VNĐ/tháng")).toBeInTheDocument();
  });
});
