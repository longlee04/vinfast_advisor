// @vitest-environment node
//
// Ghim `node` chứ không dùng `jsdom` mặc định: `API_BASE_URL` đổi theo
// `typeof window` — không có `window` thì tuyệt đối
// (`http://localhost:8000/api/v1`), có `window` thì tương đối (`/api/v1`, để
// nginx proxy). Bộ này kiểm nhánh KHÔNG có `window`; chạy trong `jsdom` là kiểm
// nhánh khác và `startsWith("http")` đỏ.

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AgentApiError,
  fetchTestDriveAvailability,
  approveReview,
  claimReview,
  claimBottleneckSignal,
  fetchBottleneckSignalDetail,
  fetchAllConversationMessages,
  fetchBottleneckSignals,
  fetchDeliveries,
  fetchReviewDetail,
  fetchReviewQueue,
  fetchReviews,
  fetchSalesOpportunities,
  rejectReview,
  resolveReview,
  sendBottleneckSignalOffer,
  sendBottleneckSignalVerdict,
  sendTurn,
  turnEventsUrl,
} from "@/lib/api/agent";

function mockFetch(body: unknown, status = 200): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("sendTurn", () => {
  it("gửi session_id và message tới /agent/turn kèm cookie", async () => {
    const fetchMock = mockFetch({
      answer: null,
      pending_question: "Xe chở mấy người?",
      lookup_facts: [],
      terminal_reason: null,
    });

    const result = await sendTurn(
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "Toi can xe dien",
    );

    expect(result.pending_question).toBe("Xe chở mấy người?");
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain("/agent/turn");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(JSON.parse(String(init.body))).toEqual({
      session_id: "11111111-1111-1111-1111-111111111111",
      client_turn_id: "22222222-2222-2222-2222-222222222222",
      message: "Toi can xe dien",
    });
  });

  it("ném AgentApiError mang mã lỗi và status khi backend từ chối", async () => {
    mockFetch({ detail: "authentication required" }, 401);

    await expect(sendTurn(
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "xin chao",
    )).rejects.toMatchObject({
      name: "AgentApiError",
      status: 401,
    });
  });

  it("không nuốt lỗi khi thân phản hồi không phải JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("Internal Server Error", { status: 500 })),
    );

    const error = await sendTurn(
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
      "xin chao",
    ).catch(
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(AgentApiError);
    expect((error as AgentApiError).status).toBe(500);
  });
});

describe("fetchReviewQueue", () => {
  it("trả nguyên danh sách hàng đợi", async () => {
    mockFetch([
      {
        review_id: "r-1",
        session_id: "s-1",
        run_id: "run-1",
        status: "PENDING",
        content: "Ban nhap",
        claimed_by: null,
        lease_expires_at: null,
        created_at: "2026-08-12T10:00:00Z",
      },
    ]);

    const items = await fetchReviewQueue();

    expect(items).toHaveLength(1);
    expect(items[0].status).toBe("PENDING");
  });
});

describe("fetchReviewDetail", () => {
  it("giữ nguyên ảnh base64 cho UI tự dựng data URI", async () => {
    const fetchMock = mockFetch({
      review_id: "r-1",
      session_id: "s-1",
      run_id: "run-1",
      status: "PENDING",
      content: "Ban nhap",
      edited_content: null,
      comparison_image_base64: "QUJD",
    });

    const detail = await fetchReviewDetail("r-1");

    expect(detail.comparison_image_base64).toBe("QUJD");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/review/r-1");
  });
});

describe("fetchDeliveries", () => {
  it("trả danh sách nội dung đã duyệt của phiên", async () => {
    const fetchMock = mockFetch({ items: [{ review_id: "r-1", content: "Noi dung", comparison_image_base64: null }] });

    const deliveries = await fetchDeliveries("s-1");

    expect(deliveries.items[0].content).toBe("Noi dung");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/deliveries/s-1");
  });
});

describe("claimReview", () => {
  it("gửi POST rỗng và trả kết quả tranh chấp", async () => {
    const fetchMock = mockFetch({ granted: false, rejection: "ALREADY_CLAIMED" });

    const outcome = await claimReview("r-1");

    expect(outcome.rejection).toBe("ALREADY_CLAIMED");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/review/r-1/claim");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });
});

describe("approveReview", () => {
  it("duyệt nguyên trạng gửi edited_content null", async () => {
    const fetchMock = mockFetch({ review_id: "r-1" });

    await approveReview("r-1");

    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ edited_content: null });
  });

  it("duyệt kèm sửa gửi đúng nội dung đã sửa", async () => {
    const fetchMock = mockFetch({ review_id: "r-1" });

    await approveReview("r-1", "Ban da sua");

    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      edited_content: "Ban da sua",
    });
  });

  it("giữ nguyên mã 422 khi bản sửa làm đổi số liệu", async () => {
    mockFetch({ detail: "Bản sửa làm đổi số liệu" }, 422);

    await expect(approveReview("r-1", "gia 999 trieu")).rejects.toMatchObject({ status: 422 });
  });
});

describe("rejectReview", () => {
  it("gọi đúng đường từ chối", async () => {
    const fetchMock = mockFetch({ review_id: "r-1" });

    await rejectReview("r-1");

    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/review/r-1/reject");
  });
});

describe("turnEventsUrl", () => {
  it("dựng URL tuyệt đối cho EventSource", () => {
    expect(turnEventsUrl("s-1")).toContain("/agent/events/s-1");
    expect(turnEventsUrl("s-1").startsWith("http")).toBe(true);
  });
});

describe("resolveReview", () => {
  it("duyệt không cấp ưu đãi vẫn là đường đi hợp lệ (D12)", async () => {
    const fetchMock = mockFetch({ review_id: "r-1" });

    await resolveReview("r-1", { status: "APPROVED" });

    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/review/r-1/resolve");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({
      status: "APPROVED",
      edited_content: null,
      offer_adjustment: null,
      handoff_requested: false,
    });
  });

  it("gửi nguyên gói ưu đãi và cờ chuyển tư vấn trực tiếp", async () => {
    const fetchMock = mockFetch({ review_id: "r-1" });

    await resolveReview("r-1", {
      status: "REJECTED",
      handoff_requested: true,
      offer_adjustment: {
        promotion_code: "KM-01",
        promotion_type: "FIXED_DISCOUNT",
        adjustment_type: "VND",
        amount_vnd: 5_000_000,
      },
    });

    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body));
    expect(body.status).toBe("REJECTED");
    expect(body.handoff_requested).toBe(true);
    expect(body.offer_adjustment.promotion_code).toBe("KM-01");
  });

  it("giữ mã lỗi vượt biên độ để UI dịch sang tiếng người", async () => {
    mockFetch({ detail: "adjustment_out_of_bounds" }, 422);

    await expect(
      resolveReview("r-1", { status: "APPROVED", offer_adjustment: { promotion_code: "KM-01" } }),
    ).rejects.toMatchObject({ code: "adjustment_out_of_bounds", status: 422 });
  });
});

describe("fetchReviews", () => {
  it("mặc định lọc pending và giữ nguyên hồ sơ từng dòng", async () => {
    const fetchMock = mockFetch([
      {
        review_id: "r-1",
        session_id: "s-1",
        run_id: "run-1",
        status: "PENDING",
        content: "Ban nhap",
        claimed_by: null,
        lease_expires_at: null,
        created_at: "2026-08-19T10:00:00Z",
        profile_snapshot: { offer_state: "BOTTLENECK_NO_OFFER" },
        offer_state: "BOTTLENECK_NO_OFFER",
        age_minutes: 4,
        handoff_requested: false,
        offer_suggestion_ignored: false,
      },
    ]);

    const entries = await fetchReviews();

    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/reviews?status=pending");
    expect(entries[0].offer_state).toBe("BOTTLENECK_NO_OFFER");
    expect(entries[0].age_minutes).toBe(4);
  });

  it("gửi status, limit và offset khi màn hàng đợi phân trang", async () => {
    const fetchMock = mockFetch([]);

    await fetchReviews({ status: "approved", limit: 20, offset: 40 });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("status=approved");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=40");
  });
});

describe("bottleneck signal API", () => {
  it("tải queue và detail từ endpoint signal", async () => {
    const fetchMock = mockFetch([]);

    await fetchBottleneckSignals({ status: "correct", limit: 20, offset: 10 });
    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/agent/bottleneck-signals?status=correct&limit=20&offset=10",
    );

    await fetchBottleneckSignalDetail("signal-1");
    expect(String(fetchMock.mock.calls[1][0])).toContain("/agent/bottleneck-signals/signal-1");
  });

  it("claim và verdict dùng POST đúng payload", async () => {
    const fetchMock = mockFetch({ signal_id: "signal-1", status: "PENDING" });

    await claimBottleneckSignal("signal-1");
    await sendBottleneckSignalVerdict("signal-1", "CORRECT");

    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({ verdict: "CORRECT" });
  });

  it("gửi offer qua endpoint signal và giữ error code", async () => {
    const fetchMock = mockFetch({ signal_id: "signal-1" });

    await sendBottleneckSignalOffer("signal-1", {
      promotion_code: "KM-01",
      promotion_type: "FIXED_DISCOUNT",
      amount_vnd: 3_000_000,
    });

    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/bottleneck-signals/signal-1/offer");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toMatchObject({
      promotion_code: "KM-01",
      amount_vnd: 3_000_000,
    });

    mockFetch({ detail: "promotion_expired" }, 409);
    await expect(sendBottleneckSignalOffer("signal-1", {
      promotion_code: "KM-01",
      promotion_type: "FIXED_DISCOUNT",
    })).rejects.toMatchObject({ code: "promotion_expired", status: 409 });
  });
});

describe("fetchSalesOpportunities", () => {
  it("trả danh sách cơ hội kèm hồ sơ rút gọn", async () => {
    const fetchMock = mockFetch([
      {
        session_id: "s-1",
        customer_id: "c-1",
        bottlenecks: ["PRICE", "CHARGING"],
        snapshot: { needs: ["Đi xa"], offer_state: "BOTTLENECK_OFFER_AVAILABLE" },
        last_active_at: "2026-08-19T10:00:00Z",
      },
    ]);

    const items = await fetchSalesOpportunities(10);

    expect(String(fetchMock.mock.calls[0][0])).toContain("/agent/sales-opportunities?limit=10");
    expect(items[0].bottlenecks).toEqual(["PRICE", "CHARGING"]);
    expect(items[0].snapshot.offer_state).toBe("BOTTLENECK_OFFER_AVAILABLE");
  });

  it("bỏ limit khi không truyền", async () => {
    const fetchMock = mockFetch([]);

    await fetchSalesOpportunities();

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/agent\/sales-opportunities$/);
  });
});

describe("fetchAllConversationMessages", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("đi hết con trỏ để hội thoại dài không cụt ở trang đầu", async () => {
    // `GET /conversations/{id}/messages` phân trang TIẾN, mặc định 50 mục một
    // trang. Gọi một lần rồi thôi thì hội thoại dài chỉ hiện đoạn đầu và khách
    // tưởng mất tin nhắn.
    const pages = [
      { items: [{ message_id: "m1", role: "USER", content: "một", created_at: "t1" }], next_cursor: "c1" },
      { items: [{ message_id: "m2", role: "ASSISTANT", content: "hai", created_at: "t2" }], next_cursor: null },
    ];
    const urls: string[] = [];
    const fetchMock = vi.fn(async (url: string) => {
      urls.push(url);
      return new Response(JSON.stringify(pages[urls.length - 1]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const messages = await fetchAllConversationMessages("session-1");

    expect(messages.map((item) => item.content)).toEqual(["một", "hai"]);
    expect(urls[1]).toContain("cursor=c1");
  });

  it("dừng ngay khi trang đầu đã hết, không gọi thừa một lần nào", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ items: [], next_cursor: null }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    expect(await fetchAllConversationMessages("session-1")).toEqual([]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("con trỏ hỏng không biến việc mở hội thoại thành vòng lặp vô tận", async () => {
    // Server trả mãi cùng một `next_cursor` → không có chốt chặn thì vòng lặp
    // gọi API không bao giờ dừng và tab treo.
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ items: [], next_cursor: "luon-luon" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await fetchAllConversationMessages("session-1");

    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(20);
  });
});

describe("mã lỗi có cấu trúc", () => {
  it("giữ detail.code khi backend trả object, không nuốt thành request_failed", async () => {
    // Backend trả `{"detail": {"code": "LOCATION_UNKNOWN"}}`. Parser cũ chỉ giữ
    // `detail` khi nó là CHUỖI, nên ba loại 409 khác nhau — chưa biết vị trí,
    // chưa biết loại xe, lỗi máy chủ — về client thành cùng một chữ
    // `request_failed`, và UI không phân biệt được để nói đúng câu.
    mockFetch({ detail: { code: "LOCATION_UNKNOWN" } }, 409);

    const error = await fetchTestDriveAvailability({ sessionId: "s-1", date: "2026-08-30" }).catch((e) => e);

    expect(error).toBeInstanceOf(AgentApiError);
    expect((error as AgentApiError).code).toBe("LOCATION_UNKNOWN");
    expect((error as AgentApiError).status).toBe(409);
  });

  it("detail dạng chuỗi vẫn giữ nguyên như trước", async () => {
    mockFetch({ detail: "Không tìm thấy phiên" }, 404);

    const error = await fetchTestDriveAvailability({ sessionId: "s-1", date: "2026-08-30" }).catch((e) => e);

    expect((error as AgentApiError).code).toBe("Không tìm thấy phiên");
  });

  it("không có detail nào thì rơi về request_failed", async () => {
    mockFetch({}, 500);

    const error = await fetchTestDriveAvailability({ sessionId: "s-1", date: "2026-08-30" }).catch((e) => e);

    expect((error as AgentApiError).code).toBe("request_failed");
  });
});
