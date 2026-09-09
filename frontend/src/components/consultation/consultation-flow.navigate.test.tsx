// @vitest-environment jsdom

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { AgentSessionProvider } from "@/store/agent-session";

/**
 * Đường đi TRỌN của `navigate`: TurnResponse → dispatch → store → panel cạnh
 * chat. Canh ba luật của hợp đồng đợt 9: có `navigate` thì mở panel (KHÔNG đổi
 * trang), lượt sau không có thì giữ nguyên, ghim bản đồ đồng bộ với thẻ lái thử.
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
vi.mock("next/dynamic", () => ({
  default: () => (props: { selectedId: string | null; onSelect: (id: string) => void }) => (
    <div data-testid="tour-map">
      <span data-testid="tour-map-selected">{props.selectedId}</span>
      <button onClick={() => props.onSelect("sr-2")} type="button">ghim sr-2</button>
    </div>
  ),
}));
vi.mock("@/components/consultation/tour-vehicle-summary", () => ({
  TourVehicleSummary: ({ navigate }: { navigate: { slug: string } }) => (
    <div data-testid="vehicle-summary">{navigate.slug}</div>
  ),
  hasVehicleDetail: () => true,
}));
vi.mock("@/lib/api/agent", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/agent")>();
  return {
    ...actual,
    fetchDeliveries,
    sendTurn,
    fetchConversationMessages: vi.fn().mockResolvedValue({ items: [] }),
    fetchCustomerConversations: vi.fn().mockResolvedValue([]),
  };
});

const BASE = { pending_question: null, lookup_facts: [], terminal_reason: null, awaiting_review: false, recommendations: [] };

const TURN_VEHICLE = {
  ...BASE,
  answer: "Dạ, VF 5 là lựa chọn rất hợp ạ.",
  navigate: { kind: "vehicle", vehicle_id: "v-5", slug: "vf-5", name: "VinFast VF 5 All New" },
};

const TURN_PLAIN = { ...BASE, answer: "Dạ showroom mở cửa 8h ạ." };

const TURN_MAP = {
  ...BASE,
  answer: "Dạ, em có 2 showroom gần anh/chị ạ.",
  test_drive_card: {
    vehicle_id: "v-5",
    vehicle_name: "VinFast VF 5",
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "HN", distance_label: "2 km" },
      { showroom_id: "sr-2", name: "VinFast Long Biên", address: "HN", distance_label: "6 km" },
    ],
    days: [{ date: "2026-09-01", label: "Thứ Ba 1/9", times: [{ scheduled_at: "2026-09-01T09:00", label: "09:00" }] }],
    options: [{ showroom_id: "sr-1", scheduled_at: "2026-09-01T09:00", value: "book-1" }],
    default_showroom_id: "sr-1",
    default_date: "2026-09-01",
  },
  navigate: {
    kind: "map",
    vehicle_id: "v-5",
    center: { lat: 21, lng: 105.8 },
    needs_location: false,
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "HN", lat: 21.03, lng: 105.79, distance_km: 2 },
      { showroom_id: "sr-2", name: "VinFast Long Biên", address: "HN", lat: 21.04, lng: 105.88, distance_km: 6 },
    ],
  },
};

async function gui(user: ReturnType<typeof userEvent.setup>, text: string): Promise<void> {
  await user.type(screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" }), text);
  await user.click(screen.getByRole("button", { name: "Gửi" }));
}

/** jsdom không đo layout: giả workspace 1320px, danh sách 292px → cột chat 1028px. */
class FakeResizeObserver {
  constructor(private readonly callback: () => void) {}
  observe(): void {
    this.callback();
  }
  disconnect(): void {}
}

describe("ConsultationFlow: trang web đi theo hội thoại", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get() {
        return (this as HTMLElement).classList.contains("consultation-workspace") ? 1320 : 0;
      },
    });
    Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
      configurable: true,
      get() {
        return (this as HTMLElement).classList.contains("conversation-history-sidebar") ? 292 : 0;
      },
    });
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
    fetchDeliveries.mockResolvedValue({ items: [] });
  });
  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("navigate kind=vehicle mở panel cạnh chat, KHÔNG rời /consultation; lượt sau không có thì giữ nguyên", async () => {
    const user = userEvent.setup();
    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    expect(screen.queryByRole("complementary", { name: "Trang đi theo hội thoại" })).not.toBeInTheDocument();

    sendTurn.mockResolvedValueOnce(TURN_VEHICLE);
    await gui(user, "Tôi chọn VF 5");

    const panel = await screen.findByRole("complementary", { name: "Trang đi theo hội thoại" });
    expect(panel).toHaveClass("is-open");
    expect(panel.querySelector("iframe.tour-panel__frame")?.getAttribute("src")).toBe("/vehicles/vf-5?embed=1");
    expect(within(panel).getByText("VinFast VF 5 All New")).toBeInTheDocument();
    expect(window.location.pathname).not.toContain("/vehicles/");

    // Bố cục khi mở do MỘT MÌNH CSS quyết (Sếp chốt đợt 10, panel là vai
    // chính): [56px | chat minmax(440px, 38%) | panel minmax(560px, 1fr)] —
    // khoá ở consultation-css.test.ts. Ở đây chỉ canh JS: đúng class, và KHÔNG
    // còn biến --chat-col ghim cứng cột chat (chat phải được co lại).
    const workspace = panel.parentElement!;
    expect(workspace).toHaveClass("is-rail");
    expect(workspace).toHaveClass("tour-panel-open");
    expect(workspace.style.getPropertyValue("--chat-col")).toBe("");
    const sidebar = screen.getByRole("complementary", { name: "Cuộc trò chuyện" });
    expect(sidebar).toHaveClass("is-rail");
    expect(within(sidebar).getByRole("button", { name: "Mở lại chi tiết VinFast VF 5 All New" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "" })).toHaveTextContent("Em dẫn anh/chị qua xem tận nơi VinFast VF 5 All New nhé — chi tiết em mở sẵn ngay bên cạnh đây ạ.");

    sendTurn.mockResolvedValueOnce(TURN_PLAIN);
    await gui(user, "Showroom mở mấy giờ?");
    await screen.findByText("Dạ showroom mở cửa 8h ạ.");

    expect(screen.getByRole("complementary", { name: "Trang đi theo hội thoại" })).toHaveClass("is-open");
    expect(document.querySelector("iframe.tour-panel__frame")?.getAttribute("src")).toBe("/vehicles/vf-5?embed=1");
  });

  it("thu gọn rồi mở lại bằng nút nhỏ, không phải hỏi lại bot", async () => {
    const user = userEvent.setup();
    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    sendTurn.mockResolvedValueOnce(TURN_VEHICLE);
    await gui(user, "Tôi chọn VF 5");
    await screen.findByRole("complementary", { name: "Trang đi theo hội thoại" });

    await user.click(screen.getByRole("button", { name: "Đóng cửa sổ" }));
    expect(screen.getByLabelText("Trang đi theo hội thoại", { selector: "aside" })).not.toHaveClass("is-open");
    // đóng → danh sách bung lại, bố cục về y hệt cũ
    const sidebar = screen.getByRole("complementary", { name: "Cuộc trò chuyện" });
    expect(sidebar).not.toHaveClass("is-rail");
    expect(sidebar.parentElement).not.toHaveClass("is-rail");
    expect(sidebar.parentElement!.style.getPropertyValue("--chat-col")).toBe("");

    await user.click(screen.getByRole("button", { name: "VinFast VF 5 All New" }));
    expect(screen.getByRole("complementary", { name: "Trang đi theo hội thoại" })).toHaveClass("is-open");
    expect(sidebar).toHaveClass("is-rail");
    // mở lại bằng tay: KHÔNG thêm dòng hệ thống nữa, không hỏi bot
    expect(screen.getAllByText(/Em dẫn anh\/chị qua xem/)).toHaveLength(1);
    expect(sendTurn).toHaveBeenCalledTimes(1);
  });

  it("navigate kind=map: bấm ghim đổi showroom trong thẻ lái thử và ngược lại", async () => {
    const user = userEvent.setup();
    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    sendTurn.mockResolvedValueOnce(TURN_MAP);
    await gui(user, "Tôi muốn lái thử");

    const panel = await screen.findByRole("complementary", { name: "Trang đi theo hội thoại" });
    expect(screen.getByText("Em dẫn anh/chị qua bản đồ showroom bên cạnh, mình chọn chỗ nào tiện đường nhất nhé ạ.")).toBeInTheDocument();
    const card = screen.getByRole("region", { name: "Chọn lịch lái thử" });
    expect(within(panel).getByTestId("tour-map-selected")).toHaveTextContent("sr-1");
    expect(within(card).getByRole("button", { name: /VinFast Cầu Giấy/ })).toHaveAttribute("aria-pressed", "true");

    // ghim → thẻ
    await user.click(within(panel).getByRole("button", { name: "ghim sr-2" }));
    expect(within(card).getByRole("button", { name: /VinFast Long Biên/ })).toHaveAttribute("aria-pressed", "true");
    expect(within(panel).getByRole("button", { name: /VinFast Long Biên/ })).toHaveAttribute("aria-pressed", "true");

    // thẻ → ghim
    await user.click(within(card).getByRole("button", { name: /VinFast Cầu Giấy/ }));
    expect(within(panel).getByTestId("tour-map-selected")).toHaveTextContent("sr-1");
  });
});
