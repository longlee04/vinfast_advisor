// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ConsultationFlow } from "@/components/consultation/consultation-flow";
import { AgentApiError } from "@/lib/api/agent";
import { AgentSessionProvider } from "@/store/agent-session";

const { fetchDeliveries, sendTurn, fetchTestDriveOptions, getSearchParams } = vi.hoisted(() => ({
  fetchDeliveries: vi.fn(),
  sendTurn: vi.fn(),
  fetchTestDriveOptions: vi.fn(),
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
    fetchTestDriveOptions,
    fetchCustomerConversations: vi.fn().mockResolvedValue([]),
    turnEventsUrl: (sessionId: string) => `/events/${sessionId}`,
  };
});

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  onerror: (() => void) | null = null;
  onmessage: (() => void) | null = null;

  constructor() {
    FakeEventSource.instances.push(this);
  }

  close(): void {}
}

describe("ConsultationFlow after HITL delivery", () => {
  beforeEach(() => {
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("keeps history and accepts another HITL turn after the first approval", async () => {
    const user = userEvent.setup();
    sendTurn
      .mockResolvedValueOnce({
        answer: "Đã chuyển tư vấn viên duyệt.",
        pending_question: null,
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: true,
      })
      .mockResolvedValueOnce({
        answer: "Đã chuyển câu hỏi tiếp theo cho tư vấn viên duyệt.",
        pending_question: null,
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: true,
      });
    const firstDelivery = {
      review_id: "review-1",
      content: "Tư vấn viên đã duyệt đề xuất VF 8.",
      comparison_image_base64: "Zmlyc3Q=",
    };
    const secondDelivery = {
      review_id: "review-2",
      content: "Tư vấn viên đã duyệt phần giải đáp về VF 7.",
      comparison_image_base64: "c2Vjb25k",
    };
    let resolveStaleDelivery!: (value: { items: (typeof firstDelivery)[] }) => void;
    const staleDelivery = new Promise<{ items: (typeof firstDelivery)[] }>((resolve) => {
      resolveStaleDelivery = resolve;
    });
    fetchDeliveries
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [firstDelivery] })
      // Fetch cũ của vòng 2 cố ý resolve sau event approval để bắt race ghi đè.
      .mockReturnValueOnce(staleDelivery)
      .mockResolvedValueOnce({ items: [firstDelivery, secondDelivery] })
      // Sau reload ở phase delivered, panel cần dựng lại delivery gần nhất.
      .mockResolvedValueOnce({ items: [firstDelivery, secondDelivery] });

    const rendered = render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    const composer = screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" });
    await user.type(composer, "Tôi cần xe gia đình");
    await user.click(screen.getByRole("button", { name: "Gửi" }));
    await screen.findByText("Đề xuất đang được tư vấn viên kiểm tra");
    await waitFor(() => expect(fetchDeliveries).toHaveBeenCalledTimes(1));

    await act(async () => {
      FakeEventSource.instances.at(-1)?.onmessage?.();
    });
    await screen.findByText("Tư vấn viên đã duyệt đề xuất VF 8.");

    const reopenedComposer = screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" });
    await user.type(reopenedComposer, "Còn VF 7 thì sao?");
    await user.click(screen.getByRole("button", { name: "Gửi" }));

    await screen.findByText("Đã chuyển câu hỏi tiếp theo cho tư vấn viên duyệt.");
    await waitFor(() => expect(fetchDeliveries).toHaveBeenCalledTimes(3));
    expect(screen.queryByText("Đã được tư vấn viên duyệt")).not.toBeInTheDocument();

    await act(async () => {
      FakeEventSource.instances.at(-1)?.onmessage?.();
    });
    await screen.findByText("Tư vấn viên đã duyệt phần giải đáp về VF 7.");
    expect(screen.getByAltText("Bảng so sánh các mẫu xe được đề xuất")).toHaveAttribute(
      "src",
      "data:image/png;base64,c2Vjb25k",
    );

    await act(async () => {
      resolveStaleDelivery({ items: [firstDelivery] });
    });
    expect(screen.getByAltText("Bảng so sánh các mẫu xe được đề xuất")).toHaveAttribute(
      "src",
      "data:image/png;base64,c2Vjb25k",
    );
    expect(screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" })).toBeInTheDocument();
    expect(screen.getByText("Tôi cần xe gia đình")).toBeInTheDocument();
    expect(screen.getByText("Đã chuyển tư vấn viên duyệt.")).toBeInTheDocument();
    expect(screen.getByText("Tư vấn viên đã duyệt đề xuất VF 8.")).toBeInTheDocument();
    expect(screen.getByText("Còn VF 7 thì sao?")).toBeInTheDocument();
    await waitFor(() => expect(sendTurn).toHaveBeenCalledTimes(2));
    expect(sendTurn).toHaveBeenNthCalledWith(
      2,
      "11111111-1111-1111-1111-111111111111",
      "11111111-1111-1111-1111-111111111111",
      "Còn VF 7 thì sao?",
    );

    await waitFor(() => {
      const stored = JSON.parse(sessionStorage.getItem("p150.agent-session") || "null");
      expect(stored.phase).toBe("delivered");
    });
    rendered.unmount();
    // Dựng lại như một lần F5 GIỮA hội thoại: URL lúc đó đã mang
    // `?conversation=<id>` (ConsultationFlow ghi vào ngay sau lượt đầu), nên
    // provider được phép khôi phục phiên đã lưu. Không truyền id ở đây là mô
    // phỏng một lần mở hội thoại MỚI — khi đó không khôi phục gì mới là đúng.
    render(
      <AgentSessionProvider conversationId="11111111-1111-1111-1111-111111111111">
        <ConsultationFlow initialConversationId="11111111-1111-1111-1111-111111111111" />
      </AgentSessionProvider>,
    );

    await screen.findByText("Đã được tư vấn viên duyệt");
    expect(screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" })).toBeInTheDocument();
    expect(screen.getByText("Tư vấn viên đã duyệt phần giải đáp về VF 7.")).toBeInTheDocument();
  });
});

describe("ConsultationFlow retry identity", () => {
  beforeEach(() => {
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    const ids = [
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "33333333-3333-3333-3333-333333333333",
    ];
    vi.stubGlobal("crypto", { randomUUID: vi.fn(() => ids.shift() ?? "44444444-4444-4444-4444-444444444444") });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("retries restored pending payload even when draft differs", async () => {
    sessionStorage.setItem(
      "p150.agent-session",
      JSON.stringify({
        sessionId: "11111111-1111-1111-1111-111111111111",
        messages: [{ role: "user", text: "Tin nhắn gốc" }],
        phase: "chatting",
        errorMessage: null,
        pendingSubmission: {
          id: "22222222-2222-2222-2222-222222222222",
          message: "Tin nhắn gốc",
        },
        deliveredReviewIds: [],
      }),
    );
    sendTurn.mockResolvedValueOnce({
      answer: null,
      pending_question: "Xe chở mấy người?",
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });
    const user = userEvent.setup();

    render(
      <AgentSessionProvider conversationId="11111111-1111-1111-1111-111111111111">
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "Nội dung đã sửa");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Xe chở mấy người?");

    expect(sendTurn).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "Tin nhắn gốc",
    );
    expect(screen.queryByText("Nội dung đã sửa")).not.toBeInTheDocument();
  });

  it.each([
    ["terminal 4xx", new AgentApiError("invalid_turn", 422)],
    ["empty 2xx", null],
  ])("clears pending after %s", async (_label, failure) => {
    const user = userEvent.setup();
    if (failure) {
      sendTurn.mockRejectedValueOnce(failure);
    } else {
      sendTurn.mockResolvedValueOnce({
        answer: null,
        pending_question: null,
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: false,
      });
    }
    sendTurn.mockResolvedValueOnce({
      answer: "Đã nhận tin mới.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "Tin đầu");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText(failure ? "Không gửi được lượt chat (422)." : "Agent không trả lời được lượt này.");
    const composer = screen.getByLabelText("Tin nhắn gửi trợ lý");
    await user.clear(composer);
    await user.type(composer, "Tin mới");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Đã nhận tin mới.");

    expect(sendTurn).toHaveBeenNthCalledWith(
      2,
      "11111111-1111-1111-1111-111111111111",
      "33333333-3333-3333-3333-333333333333",
      "Tin mới",
    );
  });

  it("retains pending after 5xx and cannot overwrite original payload", async () => {
    const user = userEvent.setup();
    sendTurn
      .mockRejectedValueOnce(new AgentApiError("request_failed", 503))
      .mockResolvedValueOnce({
        answer: null,
        pending_question: "Xe chở mấy người?",
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: false,
      });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "Tin gốc");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Không gửi được lượt chat (503).");
    const composer = screen.getByLabelText("Tin nhắn gửi trợ lý");
    await user.clear(composer);
    await user.type(composer, "Tin sửa");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Xe chở mấy người?");

    expect(sendTurn).toHaveBeenNthCalledWith(
      2,
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "Tin gốc",
    );
    expect(screen.queryByText("Tin sửa")).not.toBeInTheDocument();
  });

  it("reuses client turn and one bubble after ambiguous failure, then creates a new turn", async () => {
    const user = userEvent.setup();
    sendTurn
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValueOnce({
        answer: null,
        pending_question: "Xe chở mấy người?",
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: false,
      })
      .mockResolvedValueOnce({
        answer: "Đã ghi nhận 5 người.",
        pending_question: null,
        lookup_facts: [],
        terminal_reason: null,
        awaiting_review: false,
      });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    const composer = screen.getByLabelText("Tin nhắn gửi trợ lý");
    await user.type(composer, "Tôi cần xe gia đình");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Không kết nối được tới máy chủ.");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Xe chở mấy người?");

    expect(screen.getAllByText("Tôi cần xe gia đình")).toHaveLength(1);
    expect(sendTurn).toHaveBeenNthCalledWith(
      1,
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "Tôi cần xe gia đình",
    );
    expect(sendTurn).toHaveBeenNthCalledWith(
      2,
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "Tôi cần xe gia đình",
    );

    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "5 người");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Đã ghi nhận 5 người.");
    expect(sendTurn).toHaveBeenNthCalledWith(
      3,
      "11111111-1111-1111-1111-111111111111",
      "33333333-3333-3333-3333-333333333333",
      "5 người",
    );
  });
});

describe("ConsultationFlow with an auto-approved answer", () => {
  beforeEach(() => {
    // `globals` tắt trong vitest.config.ts nên auto-cleanup của testing-library
    // không chạy; không dọn thì DOM của describe trước còn nguyên và mọi query
    // theo role đều thấy hai phần tử.
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("does not show the review panel for a listed-price answer", async () => {
    // A7-4: gia niem yet duoc tra thang, KHONG qua hang doi duyet. Luot do co
    // `answer` khac null va `terminal_reason` null - dung hinh dang ma UI cu
    // doc thanh "da gui tu van vien", nen no dung man cho duyet ngay duoi mot
    // cau tra loi da hoan tat va khoa luon o nhap cua khach.
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: "VinFast VF 3 All New: gia niem yet tu 270.750.000 dong.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    await user.type(
      screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" }),
      "vf3 gia bao nhieu",
    );
    await user.click(screen.getByRole("button", { name: "Gửi" }));

    await screen.findByText("VinFast VF 3 All New: gia niem yet tu 270.750.000 dong.");
    expect(
      screen.queryByText("Đề xuất đang được tư vấn viên kiểm tra"),
    ).not.toBeInTheDocument();
    // Khach phai hoi tiep duoc ngay, khong bi khoa o nhap de cho mot review
    // chang bao gio ton tai.
    expect(
      screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" }),
    ).toBeInTheDocument();
    expect(fetchDeliveries).not.toHaveBeenCalled();
  });

  it("still shows the review panel when the server says the turn is queued", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: "Em da chuan bi xong de xuat va dang gui tu van vien kiem tra.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: true,
    });
    fetchDeliveries.mockResolvedValue({ items: [] });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    await user.type(
      screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" }),
      "anh giam cho em 20 trieu duoc khong",
    );
    await user.click(screen.getByRole("button", { name: "Gửi" }));

    await screen.findByText(
      "Đề xuất đang được tư vấn viên kiểm tra",
    );
  });
});

describe("ConsultationFlow with vehicle recommendations", () => {
  beforeEach(() => {
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  // 2026-09-23 (Sếp bắt trên giao diện): lượt đề xuất đi qua đường dự phòng /
  // đường "một bậc giá" có `answer` là LỜI DẪN, còn pitch trên card là chữ
  // catalog chung chung. Luật cards-only cũ ("có card là giấu bong bóng") nuốt
  // mất lời dẫn và khách nhận một rừng thẻ không ai dẫn.
  it("keeps the lead bubble when card pitches are not the answer text", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: ["Em đưa anh/chị lên tầm giá cao hơn một bậc ạ:", "1. VF 6 — hợp vì đủ chỗ"].join("\n\n"),
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
      recommendations: [
        {
          vehicle_id: "20000000-0000-0000-0000-000000000101",
          rank: 1,
          display_name: "VF 6",
          image_url: null,
          starting_price_vnd: "690000000",
          pitch: "Mẫu xe đang có trong danh mục VinFast.",
          citations: [],
        },
      ],
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "xe khác đắt hơn");
    await user.click(screen.getByLabelText("Gửi"));

    await waitFor(() => expect(screen.getByText("VF 6")).toBeInTheDocument());
    expect(screen.getByText(/Em đưa anh\/chị lên tầm giá cao hơn một bậc/)).toBeInTheDocument();
  });

  it("renders one card per recommended vehicle and hides the joined answer bubble", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: "VF 6 đi được 399 km.\n\nVF 8 chở được 7 chỗ.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
      recommendations: [
        {
          vehicle_id: "20000000-0000-0000-0000-000000000101",
          rank: 1,
          display_name: "VF 6",
          image_url: "https://cdn/vf6.png",
          starting_price_vnd: "690000000",
          pitch: "VF 6 đi được 399 km.",
          citations: [
            { index: 1 },
          ],
        },
        {
          vehicle_id: "20000000-0000-0000-0000-000000000102",
          rank: 2,
          display_name: "VF 8",
          image_url: null,
          starting_price_vnd: "1090000000",
          pitch: "VF 8 chở được 7 chỗ.",
          citations: [],
        },
      ],
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "tôi cần xe 5 chỗ");
    await user.click(screen.getByLabelText("Gửi"));

    await waitFor(() => expect(screen.getByText("VF 6")).toBeInTheDocument());
    expect(screen.getByText("VF 8")).toBeInTheDocument();
    expect(screen.getByText("Giá từ 690.000.000 đ")).toBeInTheDocument();
    // [I3] Lượt auto-approved có card thì KHÔNG được hiện lại y hệt nội dung
    // dưới dạng một bong bóng joined-text riêng — trùng lặp và gây hiểu nhầm
    // (nội dung card cũng chính là các câu pitch). Ghép nguyên văn `answer`
    // (khớp khoảng trắng đã chuẩn hoá) không được xuất hiện: nếu còn bong
    // bóng, đây là node DUY NHẤT chứa cả hai câu pitch nối liền.
    expect(
      screen.queryByText("VF 6 đi được 399 km. VF 8 chở được 7 chỗ."),
    ).not.toBeInTheDocument();
  });

  // [C1] `agent_finished` (lượt đang chờ tư vấn viên duyệt) nay đặt
  // `pitchHidden: true` — card catalog vẫn hiện (tên, ảnh, giá) nhưng pitch/
  // citation CHƯA qua duyệt thì không được lộ ra, kể cả khi backend lỡ chưa
  // gate (payload test vẫn cố tình để `pitch`/`citations` đầy trong mock để
  // xác nhận frontend tự ẩn — defense in depth). Đồng thời [I3]: tin nhắn có
  // `pitchHidden` thì bong bóng trả lời KHÔNG bị màn cards-only nuốt mất, vì
  // đó là chỗ duy nhất khách đọc được nội dung của lượt `agent_finished` này.
  // Payload `delivered` (nội dung tư vấn viên duyệt/sửa) KHÔNG có
  // `recommendations` nên vẫn luôn render thành một bong bóng chung, không card.
  it("hides the pending-review card's pitch but keeps its bubble, and still shows the later advisor delivery", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: "Em xin đề xuất mẫu xe phù hợp nhất.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: true,
      recommendations: [
        {
          vehicle_id: "20000000-0000-0000-0000-000000000101",
          rank: 1,
          display_name: "VF 6",
          image_url: "https://cdn/vf6.png",
          starting_price_vnd: "690000000",
          pitch: "VF 6 đi được 399 km [1].",
          citations: [
            { index: 1 },
          ],
        },
      ],
    });
    fetchDeliveries.mockResolvedValueOnce({ items: [] }).mockResolvedValueOnce({
      items: [
        {
          review_id: "review-1",
          content: "Nội dung tư vấn viên đã sửa.",
          comparison_image_base64: null,
        },
      ],
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "tôi cần xe 5 chỗ");
    await user.click(screen.getByLabelText("Gửi"));

    await screen.findByText("VF 6");
    await waitFor(() => expect(fetchDeliveries).toHaveBeenCalledTimes(1));

    await act(async () => {
      FakeEventSource.instances.at(-1)?.onmessage?.();
    });

    await waitFor(() => expect(screen.getByText("Nội dung tư vấn viên đã sửa.")).toBeInTheDocument());
    // [I3] Bong bóng của lượt `agent_finished` vẫn còn: `pitchHidden` che card,
    // không che tin nhắn — nếu không, khách nhìn thấy card trống trơn.
    expect(screen.getByText("Em xin đề xuất mẫu xe phù hợp nhất.")).toBeInTheDocument();
    expect(screen.getByText("VF 6")).toBeInTheDocument();
    // [C1] `pitch`/`citations` của card CHƯA qua duyệt không được lộ ra.
    expect(screen.queryByText("VF 6 đi được 399 km [1].")).not.toBeInTheDocument();
    expect(screen.queryByText("[1] cars:row-1")).not.toBeInTheDocument();
  });
});

describe("ConsultationFlow with search params and back navigation", () => {
  beforeEach(() => {
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
    getSearchParams.mockReturnValue(new URLSearchParams());
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders back button to vehicle product page when from parameter is present", () => {
    getSearchParams.mockReturnValue(new URLSearchParams("from=/vehicles/vf-8"));

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    const backLink = screen.getByRole("link", { name: "Quay lại trang sản phẩm" });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute("href", "/vehicles/vf-8");
  });

  it("renders default back button to home when from parameter is absent", () => {
    getSearchParams.mockReturnValue(new URLSearchParams());

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    const backLink = screen.getByRole("link", { name: "Quay lại trang chủ" });
    expect(backLink).toBeInTheDocument();
    expect(backLink).toHaveAttribute("href", "/");
  });

  it("automatically sends the initial prompt from URL query params", async () => {
    getSearchParams.mockReturnValue(
      new URLSearchParams("prompt=Xe VF 8 sạc bao lâu?&from=/vehicles/vf-8"),
    );

    sendTurn.mockResolvedValueOnce({
      answer: "VF 8 sạc nhanh từ 10% đến 70% trong khoảng 31 phút.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    await screen.findByText("Xe VF 8 sạc bao lâu?");
    await screen.findByText("VF 8 sạc nhanh từ 10% đến 70% trong khoảng 31 phút.");
    // `client_turn_id` do client sinh mỗi lượt (khử trùng lặp khi gửi lại).
    expect(sendTurn).toHaveBeenCalledWith(
      "11111111-1111-1111-1111-111111111111",
      expect.any(String),
      "Xe VF 8 sạc bao lâu?",
    );
  });

  it("keeps the initial prompt visible when restoring a stored session", async () => {
    const prompt = "Tôi cần ô tô điện cho 4 người, ngân sách 500 triệu.";
    getSearchParams.mockReturnValue(
      new URLSearchParams(`prompt=${encodeURIComponent(prompt)}`),
    );
    sessionStorage.setItem(
      "p150.agent-session",
      JSON.stringify({
        sessionId: "22222222-2222-2222-2222-222222222222",
        messages: [
          { role: "assistant", text: "Nội dung của lượt tư vấn trước." },
        ],
        phase: "chatting",
        errorMessage: null,
        deliveredReviewIds: [],
      }),
    );
    sendTurn.mockResolvedValueOnce({
      answer: "Mình tìm thấy các mẫu xe phù hợp ngân sách của bạn.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider conversationId="22222222-2222-2222-2222-222222222222">
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    await screen.findByText("Nội dung của lượt tư vấn trước.");
    await screen.findByText(prompt);
    await screen.findByText("Mình tìm thấy các mẫu xe phù hợp ngân sách của bạn.");
    expect(sendTurn).toHaveBeenCalledTimes(1);
    expect(sendTurn).toHaveBeenCalledWith(
      "22222222-2222-2222-2222-222222222222",
      expect.any(String),
      prompt,
    );
  });
});

describe("ConsultationFlow khi chưa đăng nhập", () => {
  beforeEach(() => {
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    // `mockReset` chứ không `clearAllMocks`: describe trước xếp sẵn vài
    // `mockResolvedValueOnce` chưa dùng hết, để nguyên thì lượt gửi ở đây ăn
    // phải bản thành công cũ thay vì lỗi mình vừa xếp.
    sendTurn.mockReset();
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "11111111-1111-1111-1111-111111111111" });
    fetchDeliveries.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  async function guiMotLuot(status: number): Promise<void> {
    const user = userEvent.setup();
    // `mockRejectedValue` chứ không `Once`: component có thể gửi lại, lần hai mà
    // trả `undefined` thì thành lỗi kiểu khác, không còn là lỗi đăng nhập nữa.
    sendTurn.mockRejectedValue(new AgentApiError("khong duoc phep", status));
    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByRole("textbox", { name: "Tin nhắn gửi trợ lý" }), "Toi can xe dien");
    await user.click(screen.getByRole("button", { name: "Gửi" }));
  }

  it("401 thì đưa nút sang trang đăng nhập, không phải Bắt đầu lại", async () => {
    await guiMotLuot(401);

    const nut = await screen.findByRole("link", { name: /Đăng nhập/ });
    expect(nut).toHaveAttribute("href", "/login");
    expect(screen.getByText("Bạn cần đăng nhập để tiếp tục hội thoại.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bắt đầu lại/ })).not.toBeInTheDocument();
  });

  it("lỗi không phải đăng nhập thì vẫn là Bắt đầu lại", async () => {
    await guiMotLuot(500);

    await screen.findByRole("button", { name: /Bắt đầu lại/ });
    expect(screen.queryByRole("link", { name: /Đăng nhập/ })).not.toBeInTheDocument();
  });
});

// ── Vào từ trang chính: hội thoại MỚI, và khách là người mở lời ──────────────
//
// Hai lỗi Sếp báo 2026-08-25:
//   1. Bấm "Trò chuyện với AI" ở trang chính lại rơi vào hội thoại cũ.
//   2. Bong bóng đầu tiên trong luồng luôn là của bot, dù chính khách mới là
//      người mở lời khi bấm vào từ trang chính.

describe("ConsultationFlow mo tu trang chinh", () => {
  beforeEach(() => {
    // `vi.clearAllMocks()` ở `afterEach` của các describe trước KHÔNG xoá hàng
    // đợi `mockResolvedValueOnce` còn thừa — phải `mockReset()`. Thiếu dòng này
    // thì lượt chat trong describe dưới đây nhận về câu trả lời của một test khác.
    sendTurn.mockReset();
    fetchDeliveries.mockReset();
    // DOM của describe trước còn nằm lại (không phải describe nào cũng gọi
    // `cleanup`), nên `findByText` sẽ thấy hai lời chào và ném "Found multiple".
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "99999999-9999-9999-9999-999999999999" });
    getSearchParams.mockReturnValue(new URLSearchParams());
    fetchDeliveries.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    getSearchParams.mockReturnValue(new URLSearchParams());
  });

  it("khong khoi phuc hoi thoai cu khi vao /consultation tron", async () => {
    sessionStorage.setItem(
      "p150.agent-session",
      JSON.stringify({
        sessionId: "88888888-8888-8888-8888-888888888888",
        messages: [{ role: "user", text: "Câu hỏi của lần trước" }],
        phase: "chatting",
        errorMessage: null,
        pendingSubmission: null,
        deliveredReviewIds: [],
      }),
    );

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    // Cách B (Sếp 2026-08-31): bot không mở lời — khung trống, chỉ có ô gõ.
    await screen.findByLabelText("Tin nhắn gửi trợ lý");
    expect(document.querySelector(".conversation-message")).toBeNull();
    expect(screen.queryByText("Câu hỏi của lần trước")).not.toBeInTheDocument();
    // Phiên cũ bị xoá luôn, không sống lại ở lần điều hướng sau.
    expect(sessionStorage.getItem("p150.agent-session")).not.toContain(
      "88888888-8888-8888-8888-888888888888",
    );
  });

  it("bong bong dau tien la cua khach, khong phai bot chao", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: null,
      pending_question: "Ngân sách của bạn khoảng bao nhiêu?",
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );

    // Lúc chưa có lượt nào: KHÔNG có bong bóng nào, chỉ ô gõ với dòng mời hỏi.
    await screen.findByLabelText("Tin nhắn gửi trợ lý");
    expect(document.querySelector(".conversation-message")).toBeNull();

    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "Tôi muốn mua ô tô điện");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByText("Ngân sách của bạn khoảng bao nhiêu?");

    // Khách đã mở lời ⇒ lời chào biến mất, dòng hội thoại bắt đầu bằng câu của khách.
    expect(
      screen.queryByText("Chào anh/chị ạ. Em có thể hỗ trợ chọn xe, tra cứu giá hoặc thông tin VinFast."),
    ).not.toBeInTheDocument();
    const bubbles = document.querySelectorAll(".conversation-message");
    expect(bubbles[0]?.className).toContain("message-user");
    expect(bubbles[0]?.textContent).toContain("Tôi muốn mua ô tô điện");
  });

  it("trong khung chat KHONG co nut bam, KHONG chu mo goi y, placeholder tinh (Sep 2026-08-31)", async () => {
    sendTurn.mockResolvedValueOnce({
      answer: "Anh/chị quan tâm ô tô điện hay xe máy điện ạ?",
      pending_question: "Anh/chị quan tâm ô tô điện hay xe máy điện ạ?",
      quick_replies: [{ label: "Ô tô điện", value: "Ô tô điện" }],
    });
    const user = userEvent.setup();
    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.type(screen.getByLabelText("Tin nhắn gửi trợ lý"), "tư vấn xe");
    await user.click(screen.getByRole("button", { name: "Gửi" }));
    await screen.findByText("Anh/chị quan tâm ô tô điện hay xe máy điện ạ?");
    expect(screen.queryByRole("button", { name: "Ô tô điện" })).toBeNull();
    expect(document.querySelector(".composer-hint")).toBeNull();
    // Placeholder rút gọn (đợt vá 2026-08-31): câu dài cũ tràn/đứt trên ô hẹp.
    expect(screen.getByLabelText("Tin nhắn gửi trợ lý")).toHaveAttribute("placeholder", "Hỏi em về giá, sạc, chọn xe…");
  });

  it("nut gap tu van vien gui cum tu tat dinh, khong de LLM doan", async () => {
    const user = userEvent.setup();
    sendTurn.mockResolvedValueOnce({
      answer: "Phần này anh tư vấn viên hỗ trợ tốt hơn ạ.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: true,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    await user.click(screen.getByRole("button", { name: /Gặp tư vấn viên/ }));

    // Cụm "tư vấn viên" là thứ `domain/escalation._HUMAN_ADVISOR` bắt bằng regex
    // tất định. Đổi câu chữ ở đây mà quên regex kia thì nút mất tác dụng trong im lặng.
    await waitFor(() => expect(sendTurn).toHaveBeenCalled());
    expect(sendTurn.mock.calls[0][2]).toContain("tư vấn viên");
  });
});


describe("ConsultationFlow — thẻ lái thử xin vị trí rồi đổi tại chỗ", () => {
  beforeEach(() => {
    sendTurn.mockReset();
    fetchTestDriveOptions.mockReset();
    cleanup();
    sessionStorage.clear();
    FakeEventSource.instances = [];
    vi.stubGlobal("EventSource", FakeEventSource);
    vi.stubGlobal("crypto", { randomUUID: () => "33333333-3333-3333-3333-333333333333" });
    fetchDeliveries.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("gõ quận/huyện trên thẻ: thẻ đổi thành showroom/giờ trong CÙNG message, không mọc message mới", async () => {
    const user = userEvent.setup();
    const NAY_9H = "2026-08-30T09:00:00+07:00";
    sendTurn.mockResolvedValueOnce({
      answer: "Anh/chị bấm Dùng vị trí của tôi hoặc gõ quận/huyện ngay trong thẻ nhé.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
      test_drive_card: {
        vehicle_id: "veh-vf8",
        vehicle_name: "VinFast VF 8",
        needs_location: true,
        showrooms: [],
        days: [],
        options: [],
        default_showroom_id: "",
        default_date: "",
      },
      quick_replies: [{ label: "Giá lăn bánh", value: "Giá lăn bánh" }],
    });
    fetchTestDriveOptions.mockResolvedValueOnce({
      test_drive_card: {
        vehicle_id: "veh-vf8",
        vehicle_name: "VinFast VF 8",
        needs_location: false,
        showrooms: [{ showroom_id: "sr-lb", name: "Long Biên", address: "Số 1 Nguyễn Văn Cừ", distance_label: "2,1 km" }],
        days: [{ date: "2026-08-30", label: "Hôm nay 30/08", times: [{ scheduled_at: NAY_9H, label: "9h00" }] }],
        options: [{ showroom_id: "sr-lb", scheduled_at: NAY_9H, value: "__lichlaithu__|" + NAY_9H + "|Long Biên" }],
        default_showroom_id: "sr-lb",
        default_date: "2026-08-30",
      },
      quick_replies: [{ label: "Có ưu đãi gì không?", value: "Có ưu đãi gì không?" }],
    });
    sendTurn.mockResolvedValueOnce({
      answer: "Dạ em đã đặt lịch 9h00 tại Long Biên ạ.",
      pending_question: null,
      lookup_facts: [],
      terminal_reason: null,
      awaiting_review: false,
    });

    render(
      <AgentSessionProvider>
        <ConsultationFlow />
      </AgentSessionProvider>,
    );
    const input = screen.getByLabelText("Tin nhắn gửi trợ lý");
    await user.type(input, "Tôi muốn lái thử VF 8");
    await user.click(screen.getByLabelText("Gửi"));
    await screen.findByLabelText("Quận/huyện, tỉnh");
    const turnsBefore = document.querySelectorAll(".conversation-turn").length;

    await user.type(screen.getByLabelText("Quận/huyện, tỉnh"), "Long Biên, Hà Nội");
    await user.click(screen.getByRole("button", { name: "Tìm showroom" }));

    // Thẻ đổi tại chỗ: cột giờ hiện ra, khối xin vị trí biến mất, số lượt y nguyên.
    await screen.findByRole("button", { name: "9h00" });
    expect(screen.queryByLabelText("Quận/huyện, tỉnh")).toBeNull();
    expect(document.querySelectorAll(".conversation-turn")).toHaveLength(turnsBefore);
    expect(fetchTestDriveOptions).toHaveBeenCalledWith({
      sessionId: "33333333-3333-3333-3333-333333333333",
      vehicleId: "veh-vf8",
      locationText: "Long Biên, Hà Nội",
    });
    // Gợi ý ô gõ đi theo thẻ mới.

    // Bấm giờ rồi Đặt lịch: vẫn gửi mã `__lichlaithu__…` như trước, không thêm đường mới.
    await user.click(screen.getByRole("button", { name: "9h00" }));
    await user.click(screen.getByRole("button", { name: "Đặt lịch" }));
    await screen.findByText("Dạ em đã đặt lịch 9h00 tại Long Biên ạ.");
    expect(sendTurn.mock.calls.at(-1)?.[2]).toBe("__lichlaithu__|" + NAY_9H + "|Long Biên");
  });
});
