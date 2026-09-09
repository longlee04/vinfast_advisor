// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AgentDock } from "@/components/customer/agent-dock";

const { push, getPathname } = vi.hoisted(() => ({
  push: vi.fn(),
  getPathname: vi.fn(() => "/"),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push }),
  usePathname: () => getPathname(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

describe("AgentDock", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    getPathname.mockReturnValue("/");
  });

  it("renders a restrained agent composer without the decorative AI badge", () => {
    render(<AgentDock />);

    expect(screen.getByRole("complementary", { name: "Trợ lý tư vấn" })).toBeInTheDocument();
    // Hint câu hỏi mẫu đang chạy nên placeholder rỗng; trỏ chuột vào là hint tắt
    // NGAY và placeholder thường quay lại (Sếp 2026-08-31).
    expect(document.querySelector(".agent-dock-hint")).toBeInTheDocument();
    fireEvent.pointerEnter(screen.getByRole("textbox", { name: "Câu hỏi cho trợ lý" }));
    expect(document.querySelector(".agent-dock-hint")).toBeNull();
    expect(screen.getByPlaceholderText("Bạn muốn hỏi gì về VinFast?")).toBeInTheDocument();
    // Thống nhất động từ với header: "Đặt lịch lái thử" (đợt vá 2026-08-31).
    expect(screen.getByRole("link", { name: /đặt lịch lái thử/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.queryByText("AI Advisor")).not.toBeInTheDocument();
    expect(document.querySelector(".lucide-sparkles")).not.toBeInTheDocument();
  });

  it("opens the consultation with the trimmed prompt", async () => {
    const user = userEvent.setup();
    render(<AgentDock />);

    await user.type(screen.getByRole("textbox", { name: "Câu hỏi cho trợ lý" }), "  VF 8 đi được bao xa?  ");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));

    expect(push).toHaveBeenCalledWith("/consultation?prompt=VF+8+%C4%91i+%C4%91%C6%B0%E1%BB%A3c+bao+xa%3F");
  });

  it("includes the from path when opened from a vehicle page", async () => {
    getPathname.mockReturnValue("/vehicles/vf-8");
    const user = userEvent.setup();
    render(<AgentDock />);

    await user.type(screen.getByRole("textbox", { name: "Câu hỏi cho trợ lý" }), "VF 8 sạc bao lâu?");
    await user.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));

    expect(push).toHaveBeenCalledWith("/consultation?prompt=VF+8+s%E1%BA%A1c+bao+l%C3%A2u%3F&from=%2Fvehicles%2Fvf-8");
  });

  it("hides completely when on the consultation page", () => {
    getPathname.mockReturnValue("/consultation");
    const { container } = render(<AgentDock />);

    expect(container).toBeEmptyDOMElement();
  });

  it("keeps the existing dock and focuses its input when a consultation CTA asks for it", () => {
    render(<AgentDock />);
    const input = screen.getByRole("textbox", { name: "Câu hỏi cho trợ lý" });

    fireEvent(window, new CustomEvent("vinfast:open-agent-dock", {
      detail: { prompt: "Tư vấn giúp tôi về VF 9" },
    }));

    expect(input).toHaveFocus();
    expect(input).toHaveValue("Tư vấn giúp tôi về VF 9");
  });
});
