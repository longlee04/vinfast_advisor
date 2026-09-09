import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";

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

describe("VehicleMegaMenu", () => {
  it("mở bằng nhấn, mặc định hiện xe điện và đóng bằng Escape", async () => {
    const user = userEvent.setup();
    render(<VehicleMegaMenu />);

    const trigger = screen.getByRole("button", { name: "Ô tô" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "VF 2" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fadil" })).not.toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("đổi danh sách xe theo tab và đóng sau khi chọn xe", async () => {
    const user = userEvent.setup();
    render(<VehicleMegaMenu />);

    await user.click(screen.getByRole("button", { name: "Ô tô" }));
    await user.click(screen.getByRole("tab", { name: "Động cơ xăng" }));

    expect(screen.getByRole("tab", { name: "Động cơ xăng" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: "Fadil" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "VF 2" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Dòng xe dịch vụ" }));
    expect(screen.getByRole("link", { name: "Minio Green" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Fadil" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Động cơ xăng" }));
    await user.click(screen.getByRole("link", { name: "Fadil" }));
    expect(screen.getByRole("button", { name: "Ô tô" })).toHaveAttribute("aria-expanded", "false");
  });

  it("cho phép chuyển tab bằng phím mũi tên", async () => {
    const user = userEvent.setup();
    render(<VehicleMegaMenu />);

    await user.click(screen.getByRole("button", { name: "Ô tô" }));
    screen.getByRole("tab", { name: "Động cơ điện" }).focus();
    await user.keyboard("{ArrowRight}");

    expect(screen.getByRole("tab", { name: "Động cơ xăng" })).toHaveFocus();
    expect(screen.getByRole("tab", { name: "Động cơ xăng" })).toHaveAttribute("aria-selected", "true");
  });

  it("đóng khi khách nhấn ra ngoài menu", async () => {
    const user = userEvent.setup();
    render(<><VehicleMegaMenu /><button type="button">Nội dung trang</button></>);

    await user.click(screen.getByRole("button", { name: "Ô tô" }));
    fireEvent.mouseDown(screen.getByRole("button", { name: "Nội dung trang" }));

    expect(screen.getByRole("button", { name: "Ô tô" })).toHaveAttribute("aria-expanded", "false");
  });
});
