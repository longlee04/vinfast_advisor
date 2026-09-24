// @vitest-environment jsdom

import { act, cleanup, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CustomerProfilePanel } from "@/components/customer360/customer-profile-panel";
import * as agentApi from "@/lib/api/agent";
import type { BottleneckSignal } from "@/types/agent";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/api/agent", () => ({ fetchBottleneckSignals: vi.fn() }));

function signal(overrides: Partial<BottleneckSignal>): BottleneckSignal {
  return {
    signal_id: "sig-1",
    session_id: "sess-1",
    client_turn_id: "t1",
    anchor_client_turn_id: "t1",
    label: "PRICE",
    evidence_quote: "giá hơi cao so với nhà em",
    status: "CORRECT",
    claimed_by: null,
    claimed_at: null,
    lease_expires_at: null,
    advisor_id: null,
    decided_at: null,
    created_at: "2026-09-24T09:00:00Z",
    updated_at: "2026-09-24T09:00:00Z",
    ...overrides,
  };
}

async function renderPanel(readOnly: boolean) {
  await act(async () => {
    render(
      <CustomerProfilePanel
        conversationId="sess-1"
        customerId="cust-1"
        customerLabel="Nguyễn An"
        hitlReasons={["Bot đã bàn giao — khách đang chờ tư vấn viên"]}
        readOnly={readOnly}
        role={readOnly ? "admin" : "advisor"}
        slots={{ vehicle_type: "CAR", budget_stated_vnd: 800_000_000, purpose_bucket: "FAMILY" }}
      />,
    );
  });
}

describe("CustomerProfilePanel", () => {
  beforeEach(() => {
    cleanup();
    vi.mocked(agentApi.fetchBottleneckSignals).mockImplementation(async (options) =>
      options?.status === "correct"
        ? [signal({}), signal({ signal_id: "sig-other", session_id: "sess-2", label: "RANGE", evidence_quote: "phiên khác" })]
        : [signal({ signal_id: "sig-2", label: "CHARGING", status: "PENDING", evidence_quote: "chung cư không có chỗ sạc" })],
    );
  });

  it("TVV: nhu cầu từ slot, rào cản CHỈ của phiên này, và lối sang cấp ưu đãi + hồ sơ", async () => {
    await renderPanel(false);

    expect(screen.getByText("Ô tô điện")).toBeInTheDocument();
    expect(screen.getByText("800 triệu")).toBeInTheDocument();
    expect(screen.queryByText("FAMILY")).not.toBeInTheDocument();
    expect(screen.getByText("giá hơi cao so với nhà em")).toBeInTheDocument();
    expect(screen.getByText("chung cư không có chỗ sạc")).toBeInTheDocument();
    expect(screen.queryByText("phiên khác")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Cấp ưu đãi/ })).toHaveAttribute("href", "/advisor/bottleneck-signals/sig-1");
    expect(screen.getByRole("link", { name: /Xem hồ sơ khách/ })).toHaveAttribute("href", "/advisor/customers/cust-1");
    // Panel cũ viết cứng hai dòng này — không còn.
    expect(screen.queryByText("Dữ liệu đã xác thực")).not.toBeInTheDocument();
  });

  it("Admin (chỉ xem): không có nút cấp ưu đãi, hồ sơ trỏ sang route admin", async () => {
    await renderPanel(true);

    expect(screen.queryByRole("link", { name: /Cấp ưu đãi/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Xem hồ sơ khách/ })).toHaveAttribute("href", "/admin/customers/cust-1");
  });
});
