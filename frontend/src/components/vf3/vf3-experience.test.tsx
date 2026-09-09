// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf3Experience } from "@/components/vf3/vf3-experience";

vi.mock("next/image", () => ({
  default: ({ alt, src, ...props }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} {...props} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props}>{children}</a>,
}));

afterEach(cleanup);

describe("Vf3Experience", () => {
  it("renders the VF 3 campaign pricing and technical specifications from the reference", () => {
    render(<Vf3Experience />);

    expect(screen.getByAltText("VinFast VF 3 - Chiếc xe đô thị dành cho thế hệ người Việt mới")).toBeInTheDocument();
    expect(screen.getByText("270.750.000")).toBeInTheDocument();
    expect(screen.getByText("281.200.000")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thông số kỹ thuật" })).toBeInTheDocument();
    expect(screen.getByText("36 phút (10% - 70%)")).toBeInTheDocument();
  });

  it("changes to the real vehicle image selected by the color controls", () => {
    render(<Vf3Experience />);

    expect(screen.getByAltText("VinFast VF 3 màu Summer Yellow")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf3/color-summer-yellow.webp",
    );

    fireEvent.click(screen.getByRole("button", { name: "Xem màu Sky Blue" }));

    expect(screen.getByAltText("VinFast VF 3 màu Sky Blue")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf3/color-sky-blue.webp",
    );
  });

  it("shows every complete color name in the shared unclipped label", () => {
    render(<Vf3Experience />);

    const colorName = screen.getByRole("status");
    const names = [
      "Summer Yellow",
      "Rose Pink",
      "Zenith Grey",
      "Solar Ruby",
      "Sky Blue",
      "Urban Mint",
      "Infinity Blanc",
    ];

    for (const name of names) {
      fireEvent.click(screen.getByRole("button", { name: `Xem màu ${name}` }));
      expect(colorName).toHaveTextContent(name);
    }
  });

  it("rotates through transparent 360-degree frames when the vehicle is dragged", () => {
    render(<Vf3Experience />);

    const spinControl = screen.getByRole("slider", { name: "Xoay 360° VinFast VF 3" });
    fireEvent.pointerDown(spinControl, { clientX: 100, pointerId: 1 });
    fireEvent.pointerMove(spinControl, { clientX: 68, pointerId: 1 });
    fireEvent.pointerUp(spinControl, { pointerId: 1 });

    expect(screen.getByAltText("VinFast VF 3 màu Summer Yellow")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf3/color-summer-yellow-f02.webp",
    );
  });

  it("keeps the vehicle menu closed until requested and closes it after choosing a car", () => {
    render(<Vf3Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(screen.getByRole("link", { name: "VF 5" })).toHaveAttribute("href", "/vehicles/vf-5");
    fireEvent.click(screen.getByRole("link", { name: "VF 5" }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "VF 5" })).not.toBeInTheDocument();
  });

  it("uses test-drive and shared advisor choices instead of a deposit action", () => {
    render(<Vf3Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /đặt lịch lái thử/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toBeInTheDocument();
  });
});
