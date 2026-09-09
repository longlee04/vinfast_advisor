import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { MotorbikeMegaMenu } from "@/components/shared/motorbike-mega-menu";

vi.mock("next/image", () => ({
  default: ({ src }: { alt: string; src: string }) => <span data-image-src={src} />,
}));

vi.mock("next/link", () => ({
  default: ({ children, href, onClick }: React.ComponentProps<"a">) => (
    <a
      href={href}
      onClick={(event) => {
        event.preventDefault();
        onClick?.(event);
      }}
    >
      {children}
    </a>
  ),
}));

describe("MotorbikeMegaMenu", () => {
  it("mở bằng nhấn và mặc định hiển thị phân khúc phổ thông", async () => {
    const user = userEvent.setup();
    render(<MotorbikeMegaMenu />);

    const trigger = screen.getByRole("button", { name: "Xe máy điện" });
    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("tab", { name: "Phổ thông" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Evo" })).toHaveAttribute("href", "/motorbikes/evo");
    expect(screen.queryByRole("link", { name: "Vero X" })).not.toBeInTheDocument();
  });

  it("đổi phân khúc và đóng sau khi chọn xe", async () => {
    const user = userEvent.setup();
    render(<MotorbikeMegaMenu />);

    await user.click(screen.getByRole("button", { name: "Xe máy điện" }));
    await user.click(screen.getByRole("tab", { name: "Cao cấp" }));

    expect(screen.getByRole("link", { name: "Vero X" })).toHaveAttribute("href", "/motorbikes/vero-x");
    expect(screen.queryByRole("link", { name: "Evo" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Vero X" }));
    expect(screen.getByRole("button", { name: "Xe máy điện" })).toHaveAttribute("aria-expanded", "false");
  });
});
