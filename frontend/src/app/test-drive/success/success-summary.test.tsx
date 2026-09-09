// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { BookingSuccessSummary } from "@/app/test-drive/success/success-summary";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

describe("BookingSuccessSummary — màn đặt lịch thành công", () => {
  beforeEach(() => cleanup());

  it("có dữ liệu thật từ form (query params): hiện đúng xe/giờ/showroom vừa đặt", () => {
    render(
      <BookingSuccessSummary
        date="2026-09-01"
        showroom="VinFast Long Biên"
        time="15:30"
        vehicle="VinFast VF 6 Plus"
      />,
    );

    expect(screen.getByText("VinFast VF 6 Plus")).toBeInTheDocument();
    expect(screen.getByText(/15:30/)).toBeInTheDocument();
    expect(screen.getByText("VinFast Long Biên")).toBeInTheDocument();
    // Dữ liệu bịa cứng ngày xưa không còn.
    expect(screen.queryByText("VF 6 Plus", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText(/Thứ Tư, 12\/08\/2026/)).not.toBeInTheDocument();
    expect(screen.queryByText("VinFast Times City")).not.toBeInTheDocument();
  });

  it("thiếu params (vào thẳng trang): bản chung chỉ đường vào Tài khoản, KHÔNG bịa dữ liệu", () => {
    render(<BookingSuccessSummary />);

    expect(screen.getByText(/kiểm tra trong Tài khoản/i)).toBeInTheDocument();
    expect(screen.queryByText("VF 6 Plus")).not.toBeInTheDocument();
    expect(screen.queryByText("VinFast Times City")).not.toBeInTheDocument();
  });
});
