// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomeHeroSlider } from "@/components/home/home-hero-slider";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => <a href={href} {...props}>{children}</a>,
}));

describe("HomeHeroSlider", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    Object.defineProperty(window, "matchMedia", {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    });
  });

  afterEach(() => vi.useRealTimers());

  it("uses all six official campaign banners in the order shown by the reference", () => {
    render(<HomeHeroSlider />);

    expect(screen.getByRole("heading", { name: "Thu nhập hiệu quả dù ngày hay đêm" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Thu nhập hiệu quả dù ngày hay đêm" })).toHaveAttribute("href", "/test-drive");
    expect(screen.getAllByRole("button", { name: /Xem slide/ })).toHaveLength(6);

    act(() => vi.advanceTimersByTime(6_000));
    expect(screen.getByRole("heading", { name: "Vingroup tri ân khách hàng nhân dịp sinh nhật 33 năm" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Xem slide 6/ }));
    expect(screen.getByRole("heading", { name: "VinFast MPV 7 - ưu đãi tài chính" })).toBeInTheDocument();
  });
});
