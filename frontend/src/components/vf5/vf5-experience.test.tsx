// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Vf5Experience } from "@/components/vf5/vf5-experience";

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

describe("Vf5Experience", () => {
  it("renders the VF 5 campaign price and technical specifications from the reference", () => {
    render(<Vf5Experience />);

    expect(screen.getByAltText("VinFast VF 5 - Cá nhân vượt trội")).toBeInTheDocument();
    expect(screen.getByText("471.200.000 VNĐ*")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Thông số kỹ thuật" })).toBeInTheDocument();
    expect(screen.getByText("33 phút")).toBeInTheDocument();
    expect(screen.getByText("6 túi khí")).toBeInTheDocument();
  });

  it("changes to a separate official vehicle image for each selected color", () => {
    render(<Vf5Experience />);

    expect(screen.getByAltText("VinFast VF 5 màu Zenith Grey")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf5/color-zenith-grey.webp",
    );

    fireEvent.click(screen.getByRole("button", { name: "Xem màu Summer Yellow Body - Jet Black Roof" }));

    expect(screen.getByAltText("VinFast VF 5 màu Summer Yellow Body - Jet Black Roof")).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/vf5/color-summer-yellow.webp",
    );
  });

  it("keeps the vehicle picker closed until requested and closes it after navigation", () => {
    render(<Vf5Experience />);

    expect(screen.queryByRole("navigation", { name: "Các dòng ô tô VinFast" })).not.toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);
    expect(screen.getByRole("link", { name: "VF 6" })).toHaveAttribute("href", "/vehicles/vf-6");
    fireEvent.click(screen.getByRole("link", { name: "VF 6" }));

    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("link", { name: "VF 6" })).not.toBeInTheDocument();
  });

  it("opens and closes the consultation dialog from the model navigation action", () => {
    render(<Vf5Experience />);

    fireEvent.click(screen.getByRole("button", { name: "Nhận báo giá và ưu đãi" }));
    expect(
      screen.getByRole("dialog", { name: /nhận báo giá & ưu đãi mới nhất/i }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Đóng biểu mẫu tư vấn" }));
    expect(
      screen.queryByRole("dialog", { name: /nhận báo giá & ưu đãi mới nhất/i }),
    ).not.toBeInTheDocument();
  });

  it("removes the video card and bottom form in favor of the shared support choices", () => {
    render(<Vf5Experience />);

    expect(screen.queryByAltText("Video giới thiệu VinFast VF 5")).not.toBeInTheDocument();
    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /đăng ký tư vấn/i })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /đặt lịch lái thử/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toBeInTheDocument();
  });
});
