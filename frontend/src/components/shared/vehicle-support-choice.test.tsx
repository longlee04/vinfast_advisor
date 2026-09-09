// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { VehicleSupportChoice } from "@/components/shared/vehicle-support-choice";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

afterEach(cleanup);

describe("VehicleSupportChoice", () => {
  it("keeps both compact support choices in one shared row", () => {
    render(<VehicleSupportChoice from="/vehicles/vf-3" model="VF 3" />);

    const choices = screen.getByRole("group", { name: "Lựa chọn hỗ trợ cho VF 3" });
    expect(choices).toHaveAttribute("data-layout", "compact-row");
    expect(choices.children).toHaveLength(2);
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
  });

  it("uses a conversational ViVi icon instead of the old sparkle symbol", () => {
    render(<VehicleSupportChoice from="/vehicles/vf-7" model="VF 7" />);

    expect(screen.getByTestId("vivi-conversation-icon")).toBeInTheDocument();
    expect(screen.queryByTestId("vivi-sparkles-icon")).not.toBeInTheDocument();
  });
});
