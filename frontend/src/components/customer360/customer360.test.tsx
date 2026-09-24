// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CustomerSummary } from "@/components/customer360/customer-summary";
import { needSummary } from "@/components/customer360/customer360-labels";
import { OpportunityCard } from "@/components/customer360/opportunity-card";
import { SessionList } from "@/components/customer360/session-list";
import type { SessionRow } from "@/types/customer360";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const CUSTOMER = {
  customer_id: "cust-1",
  display_name: "Nguyễn An",
  phone_masked: "0912***678",
  phone: "0912345678",
  assigned_advisor_id: "adv-1",
  sessions_count: 2,
  last_seen_at: "2026-09-24T09:00:00Z",
  heat_band: "HOT" as const,
  heat_score: 70,
};

const SESSION: SessionRow = {
  session_id: "11111111-2222-3333-4444-555555555555",
  started_at: null,
  last_activity_at: "2026-09-24T09:00:00Z",
  status: "ACTIVE",
  kind: "UNASSIGNED",
  opportunity_id: null,
  needs_review: false,
  decided_by: null,
  turn_count: null,
  summary_excerpt: "Hỏi giá VF 6",
};

afterEach(cleanup);

describe("CustomerSummary", () => {
  it("TVV phụ trách thấy SĐT đầy đủ và nút thao tác", () => {
    render(<CustomerSummary actions={<button type="button">Vào chat</button>} customer={CUSTOMER} readOnly={false} role="advisor" />);

    expect(screen.getByText("0912345678")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Vào chat" })).toBeInTheDocument();
    expect(screen.getByText("Nóng · 70")).toBeInTheDocument();
  });

  it("chế độ chỉ xem (Admin) chỉ thấy SĐT đã che và không có nút thao tác", () => {
    render(<CustomerSummary actions={<button type="button">Vào chat</button>} customer={CUSTOMER} readOnly role="admin" />);

    expect(screen.getByText("0912***678")).toBeInTheDocument();
    expect(screen.queryByText("0912345678")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Vào chat" })).not.toBeInTheDocument();
  });
});

describe("SessionList", () => {
  it("TVV mở phòng chat, Admin (readOnly) sang trang trace", () => {
    const { rerender } = render(<SessionList readOnly={false} role="advisor" sessions={[SESSION]} />);
    expect(screen.getByRole("link", { name: /Mở chat/ })).toHaveAttribute("href", `/advisor/conversations/${SESSION.session_id}`);

    rerender(<SessionList readOnly role="admin" sessions={[SESSION]} />);
    expect(screen.getByRole("link", { name: /Xem/ })).toHaveAttribute("href", `/admin/chat-sessions/${SESSION.session_id}`);
  });

  it("không có phiên thì nói rõ, không để trống", () => {
    render(<SessionList readOnly={false} role="advisor" sessions={[]} />);
    expect(screen.getByText("Chưa có phiên chat nào từ khách hàng này.")).toBeInTheDocument();
  });
});

describe("OpportunityCard và tóm tắt nhu cầu", () => {
  const slots = { vehicle_type: "CAR", budget_max_vnd: 900_000_000, budget_stated_vnd: 800_000_000, purpose_bucket: "FAMILY", purpose: "đưa con đi học" };

  it("chỉ hiện slot khách đã nói, định dạng đọc được, ẩn slot nội bộ", () => {
    render(
      <OpportunityCard
        opportunity={{ title: "Ô tô điện", slots, barriers: [{ code: "PRICE", evidence_quote: "hơi đắt, số em [SĐT]", session_id: "s1", turn_index: 3 }] }}
        readOnly={false}
      />,
    );

    expect(screen.getByText("Ô tô điện", { selector: "dd" })).toBeInTheDocument();
    expect(screen.getByText("800 triệu")).toBeInTheDocument();
    expect(screen.getByText("đưa con đi học")).toBeInTheDocument();
    expect(screen.queryByText("FAMILY")).not.toBeInTheDocument();
    expect(screen.getByText("Giá")).toBeInTheDocument();
    expect(screen.getByText("hơi đắt, số em [SĐT]")).toBeInTheDocument();
  });

  it("tóm tắt ưu tiên ngân sách khách nói hơn trần đã nới biên, không có slot thì trả null", () => {
    expect(needSummary(slots)).toBe("Loại xe: Ô tô điện · Ngân sách khách nói: 800 triệu · Mục đích: đưa con đi học");
    expect(needSummary({})).toBeNull();
    expect(needSummary(undefined)).toBeNull();
  });
});
