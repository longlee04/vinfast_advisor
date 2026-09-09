// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf9Experience } from "@/components/vf9/vf9-experience";

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

describe("Vf9Experience", () => {
  it("recreates the VF9 hero, specifications and two official price cards", () => {
    render(<Vf9Experience />);

    expect(
      screen.getByAltText("VinFast VF 9 - Sự lựa chọn của người thành đạt, tiên phong"),
    ).toHaveAttribute("data-image-src", "/media/vinfast/vf9/hero.webp");
    expect(screen.getByRole("heading", { name: "Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong" })).toBeInTheDocument();
    expect(screen.getByText("626 km*")).toBeInTheDocument();
    expect(screen.getByText("402 hp / 620 Nm")).toBeInTheDocument();
    expect(screen.getByText("1.280.600.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByText("1.452.550.000 VNĐ*")).toBeInTheDocument();
  });

  it("uses a separate official vehicle image for all seven exterior colors without clipping names", () => {
    render(<Vf9Experience />);

    const expectedColors = [
      ["Zenith Grey", "color-zenith-grey.webp"],
      ["Urban Mint", "color-urban-mint.webp"],
      ["Jet Black", "color-jet-black.webp"],
      ["Ivy Green", "color-ivy-green.webp"],
      ["Infinity Blanc", "color-infinity-blanc.webp"],
      ["Desat Silver", "color-desat-silver.webp"],
      ["Crimson Red", "color-crimson-red.webp"],
    ] as const;

    expectedColors.forEach(([name, file]) => {
      fireEvent.click(screen.getByRole("button", { name: `Xem màu ${name}` }));
      expect(screen.getByAltText(`VinFast VF 9 màu ${name}`)).toHaveAttribute(
        "data-image-src",
        `/media/vinfast/vf9/${file}`,
      );
      expect(screen.getByText(name)).toBeVisible();
    });
    expect(screen.getAllByRole("button", { name: /Xem màu/ })).toHaveLength(7);
  });

  it("switches the interior gallery and technology tabs", () => {
    render(<Vf9Experience />);

    expect(screen.getByAltText("Khoang lái VinFast VF 9")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf9/interior-01.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Nội thất tiếp theo" }));
    expect(screen.getByAltText("Hàng ghế cơ trưởng VinFast VF 9")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf9/interior-02.webp",
    );
    fireEvent.click(screen.getByRole("tab", { name: "Trợ lý ảo tiếng Việt" }));
    expect(screen.getByAltText("Trợ lý ảo tiếng Việt trên VinFast VF 9")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf9/technology-assistant.webp",
    );
  });

  it("uses the four official VinFast privilege icons", () => {
    render(<Vf9Experience />);

    const expectedIcons = [
      ["Biểu tượng trải nghiệm VIP VinFast", "privilege-vip.webp"],
      ["Biểu tượng dịch vụ sửa chữa VinFast", "privilege-support.webp"],
      ["Biểu tượng chăm sóc khách hàng VinFast", "privilege-urgent.webp"],
      ["Biểu tượng sạc điện VinFast", "privilege-charging.webp"],
    ] as const;

    expectedIcons.forEach(([alt, file]) => {
      expect(screen.getByAltText(alt)).toHaveAttribute(
        "data-image-src",
        `/media/vinfast/vf9/${file}`,
      );
    });
  });

  it("keeps the vehicle picker closed by default and closes it after selecting a vehicle", () => {
    render(<Vf9Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("link", { name: "VF 8" }));
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("uses only test-drive actions and shared support, without deposit or consultation forms", () => {
    render(<Vf9Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
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
