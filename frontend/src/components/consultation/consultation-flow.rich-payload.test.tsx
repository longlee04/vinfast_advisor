// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { AgentSessionProvider } from "@/store/agent-session";

/**
 * Đường đi TRỌN của thẻ chi tiết:
 *
 *     TurnResponse -> dispatch -> reduceAgentSession -> ChatMessage -> render
 *
 * Bộ này tồn tại vì test component cô lập đã nói dối. `vehicle-details-card.test.tsx`
 * xanh trong khi trên prod chưa lần nào khách thấy thẻ: nó truyền props thẳng
 * tay nên đi vòng qua đúng chỗ hỏng — nhánh `agent_answered` của reducer bỏ
 * rơi trường này.
 *
 * Không thay bộ kia. Nó canh cách VẼ; bộ này canh cách DỮ LIỆU TỚI. Kèm thêm
 * một bài canh CHIỀU NGƯỢC: `next_step_panel` backend vẫn gửi nhưng client
 * đợt 10 phải BỎ QUA — không còn nút điều hướng trong đoạn chat.
 */

const { fetchDeliveries, sendTurn, getSearchParams } = vi.hoisted(() => ({
  fetchDeliveries: vi.fn(),
  sendTurn: vi.fn(),
  getSearchParams: vi.fn(() => new URLSearchParams()),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/consultation",
  useSearchParams: () => getSearchParams(),
}));

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return {
    ...actual,
    fetchDeliveries,
    sendTurn,
    fetchCustomerConversations: vi.fn().mockResolvedValue([]),
    turnEventsUrl: (sessionId: string) => `/events/${sessionId}`,
  };
});

class FakeEventSource {
  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;
  close(): void {}
}

const TURN_WITH_CARDS = {
  answer: "Dạ VF 8 phù hợp với nhu cầu của anh/chị ạ.",
  pending_question: null,
  lookup_facts: [],
  terminal_reason: null,
  awaiting_review: false,
  recommendations: [],
  vehicle_details: {
    vehicle_name: "VinFast VF 8",
    spec_groups: [{ title: "Giá bán", rows: [["Eco", "1.190.000.000 đồng"]] }],
  },
  next_step_panel: {
    title: "Anh/chị muốn xem tiếp phần nào?",
    action: { label: "Đặt lịch lái thử", message: "Tôi muốn đặt lịch lái thử VF 8" },
  },
};

async function guiMotLuot(): Promise<void> {
  const user = userEvent.setup();
  render(
    <AgentSessionProvider>
      <ConsultationFlow />
    </AgentSessionProvider>,
  );
  const composer = screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" });
  await user.type(composer, "Cho tôi xem chi tiết VF 8");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
}

describe("ConsultationFlow giu payload giau cua mot luot", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
    fetchDeliveries.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("the chi tiet xe hien ra sau mot luot tra loi that", async () => {
    sendTurn.mockResolvedValueOnce(TURN_WITH_CARDS);

    await guiMotLuot();

    expect(await screen.findByRole("region", { name: "Chi tiết VinFast VF 8" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Giá bán" })).toHaveTextContent("1.190.000.000 đồng");
  });

  it("backend gui next_step_panel thi client BO QUA — khong con nut dieu huong trong doan chat", async () => {
    sendTurn.mockResolvedValueOnce(TURN_WITH_CARDS);

    await guiMotLuot();

    // Thẻ chi tiết của cùng lượt vẫn tới — chứng minh lượt đã render xong chứ
    // không phải chưa kịp vẽ.
    expect(await screen.findByRole("region", { name: "Chi tiết VinFast VF 8" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bước tiếp theo" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Đặt lịch lái thử" })).not.toBeInTheDocument();
  });

  it("luot khong co the thi khong ve gi them", async () => {
    sendTurn.mockResolvedValueOnce({
      answer: "Dạ showroom mở cửa 8h ạ.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
      recommendations: [],
    });

    await guiMotLuot();

    await screen.findByText("Dạ showroom mở cửa 8h ạ.");
    expect(screen.queryByRole("region", { name: /^Chi tiết / })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Bước tiếp theo" })).not.toBeInTheDocument();
  });
});
