// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf2Experience } from "@/components/vf2/vf2-experience";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props}>{children}</a>,
}));

afterEach(cleanup);

describe("Vf2Experience", () => {
  it("renders the reference campaign, pricing and technical specification content", () => {
    render(<Vf2Experience />);

    expect(screen.getByAltText("VinFast VF 2 - Ô tô đầu đời, ước mơ trong tầm với")).toBeInTheDocument();
    expect(screen.getByText("178.600.000")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thông số kỹ thuật" })).toBeInTheDocument();
    expect(screen.getByText("34 phút (10% - 70%)")).toBeInTheDocument();
  });

  it("switches the rendered vehicle image instead of using baked-in controls", () => {
    render(<Vf2Experience />);

    expect(screen.getByAltText("VinFast VF 2 màu Solar Ruby")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf2/color-solar-ruby.webp",
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Rose Pink" }));
    fireEvent.click(screen.getByRole("button", { name: "Xem màu Urban Mint" }));
    expect(screen.getByAltText("VinFast VF 2 màu Urban Mint")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf2/color-urban-mint.webp",
    );
  });

  it("uses the car navigation as a closed selector and closes it after a choice", () => {
    render(<Vf2Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const vehicleTrigger = screen.getByRole("button", { name: "Ô tô" });
    expect(vehicleTrigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(vehicleTrigger);
    expect(screen.getByRole("link", { name: "VF 3" })).toHaveAttribute("href", "/vehicles/vf-3");
    fireEvent.click(screen.getByRole("link", { name: "VF 3" }));

    expect(vehicleTrigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "VF 3" })).not.toBeInTheDocument();
  });

  it("calculates the monthly fuel advantage", () => {
    render(<Vf2Experience />);

    fireEvent.click(screen.getByRole("button", { name: "SO SÁNH" }));
    expect(screen.getByText("5.279.400 VNĐ")).toBeInTheDocument();
  });

  it("replaces deposits and the consultation form with the shared support choices", () => {
    render(<Vf2Experience />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /đặt lịch lái thử/i }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation?"),
    );
  });
});
