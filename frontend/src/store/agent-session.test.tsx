// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import {
  EMPTY_TOUR_PANEL,
  createAgentSessionState,
  readStoredSession,
  reduceAgentSession,
  writeStoredSession,
} from "@/store/agent-session";
import type { TcoCard, TurnNavigate, VehicleDetails } from "@/types/agent";

const SESSION = "11111111-1111-1111-1111-111111111111";

describe("reduceAgentSession", () => {
  it("giữ nguyên session_id qua nhiều lượt hỏi đáp", () => {
    let state = createAgentSessionState(SESSION);

    state = reduceAgentSession(state, { type: "customer_said", text: "Toi can xe dien" });
    state = reduceAgentSession(state, { type: "agent_asked", text: "Xe chở mấy người?" });
    state = reduceAgentSession(state, { type: "customer_said", text: "5 nguoi" });

    expect(state.sessionId).toBe(SESSION);
    expect(state.messages).toHaveLength(3);
    expect(state.phase).toBe("chatting");
  });

  it("thẻ lái thử đổi TẠI CHỖ trong đúng message, không thêm message mới", () => {
    const empty = {
      vehicle_id: "veh-vf8",
      vehicle_name: "VinFast VF 8",
      needs_location: true,
      showrooms: [],
      days: [],
      options: [],
      default_showroom_id: "",
      default_date: "",
    };
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "customer_said", text: "Lái thử VF 8" });
    state = reduceAgentSession(state, {
      type: "agent_answered",
      text: "Anh/chị bấm Dùng vị trí của tôi nhé.",
      testDriveCard: empty,
      quickReplies: [{ label: "Giá lăn bánh", value: "Giá lăn bánh" }],
    });
    const full = { ...empty, needs_location: false, default_showroom_id: "sr-lb", default_date: "2026-08-30" };

    const next = reduceAgentSession(state, {
      type: "test_drive_card_replaced",
      messageIndex: 1,
      card: full,
      quickReplies: [{ label: "Đặt lịch lái thử", value: "Đặt lịch lái thử" }],
    });

    expect(next.messages).toHaveLength(2);
    expect(next.messages[1].testDriveCard).toEqual(full);
    expect(next.messages[1].text).toBe("Anh/chị bấm Dùng vị trí của tôi nhé.");
    expect(next.messages[1].quickReplies?.map((r) => r.label)).toEqual(["Đặt lịch lái thử"]);
    expect(next.messages[0].testDriveCard).toBeUndefined();

    // Chỉ số trỏ vào bong bóng của KHÁCH (hay ngoài mảng) thì không đụng gì.
    expect(reduceAgentSession(state, { type: "test_drive_card_replaced", messageIndex: 0, card: full })).toBe(state);
    expect(reduceAgentSession(state, { type: "test_drive_card_replaced", messageIndex: 9, card: full })).toBe(state);
  });

  it("chuyển sang chờ duyệt khi agent nói đã gửi tư vấn viên", () => {
    const state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_finished",
      text: "Mình đã gửi tư vấn viên kiểm tra.",
    });

    expect(state.phase).toBe("waiting_review");
    expect(state.messages.at(-1)?.text).toContain("tư vấn viên");
  });

  it("giữ phiên ở trạng thái chat khi agent trả lời mà không bàn giao tư vấn viên", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "customer_said",
      text: "Cho hoi ban ban gi",
    });
    state = reduceAgentSession(state, {
      type: "agent_answered",
      text: "Mình chỉ hỗ trợ tư vấn xe điện thôi bạn nhé.",
    });

    expect(state.phase).toBe("chatting");
    expect(state.messages.at(-1)?.text).toBe("Mình chỉ hỗ trợ tư vấn xe điện thôi bạn nhé.");
  });

  it("chuyển sang đã nhận khi nội dung duyệt về", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_finished",
      text: "Đang gửi tư vấn viên",
    });
    state = reduceAgentSession(state, { type: "delivered", text: "Đề xuất VF 5", reviewId: "review-1" });

    expect(state.phase).toBe("delivered");
  });

  it("ghi lỗi mà không xoá lịch sử hội thoại", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "customer_said",
      text: "Toi can xe dien",
    });
    state = reduceAgentSession(state, { type: "failed", message: "authentication required" });

    expect(state.phase).toBe("error");
    expect(state.errorMessage).toBe("authentication required");
    expect(state.messages).toHaveLength(1);
  });

  it("bắt đầu lại thì đổi phiên và xoá sạch lịch sử", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "customer_said",
      text: "Toi can xe dien",
    });
    state = reduceAgentSession(state, {
      type: "restarted",
      sessionId: "22222222-2222-2222-2222-222222222222",
    });

    expect(state.sessionId).toBe("22222222-2222-2222-2222-222222222222");
    expect(state.messages).toHaveLength(0);
    expect(state.phase).toBe("chatting");
    expect(state.errorMessage).toBeNull();
  });
});

describe("chống chèn trùng nội dung đã duyệt", () => {
  it("cùng một review_id chỉ vào dòng hội thoại đúng một lần", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_finished",
      text: "Đang gửi tư vấn viên",
    });

    state = reduceAgentSession(state, {
      type: "delivered",
      text: "Đề xuất VF 5",
      reviewId: "review-1",
    });
    const afterFirst = state;
    // EventSource reconnect và bắn lại cùng sự kiện.
    state = reduceAgentSession(state, {
      type: "delivered",
      text: "Đề xuất VF 5",
      reviewId: "review-1",
    });

    expect(state).toBe(afterFirst);
    expect(state.messages.filter((message) => message.text === "Đề xuất VF 5")).toHaveLength(1);
  });

  it("review_id khác thì vẫn được thêm", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "delivered",
      text: "Đề xuất VF 5",
      reviewId: "review-1",
    });
    state = reduceAgentSession(state, {
      type: "delivered",
      text: "Đề xuất VF 6",
      reviewId: "review-2",
    });

    expect(state.messages).toHaveLength(2);
    expect(state.deliveredReviewIds).toEqual(["review-1", "review-2"]);
  });
});

describe("pending submission", () => {
  it("giữ một bong bóng và cùng payload qua lỗi rồi xoá pending khi agent trả lời", () => {
    const submission = {
      id: "22222222-2222-2222-2222-222222222222",
      message: "Toi can xe dien",
    };
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "submission_started",
      submission,
    });
    state = reduceAgentSession(state, { type: "failed", message: "network" });
    state = reduceAgentSession(state, {
      type: "submission_started",
      submission,
    });

    expect(state.messages.filter((message) => message.text === "Toi can xe dien")).toHaveLength(1);
    expect(state.pendingSubmission).toEqual({
      id: "22222222-2222-2222-2222-222222222222",
      message: "Toi can xe dien",
    });

    state = reduceAgentSession(state, { type: "agent_asked", text: "Xe chở mấy người?" });
    expect(state.pendingSubmission).toBeNull();
  });
});

describe("khôi phục phiên sau khi tải lại trang", () => {
  it("đọc được state cũ chưa có pending submission", () => {
    sessionStorage.setItem(
      "p150.agent-session",
      JSON.stringify({
        sessionId: SESSION,
        messages: [{ role: "user", text: "Toi can xe dien" }],
        phase: "chatting",
        errorMessage: null,
        deliveredReviewIds: [],
      }),
    );

    const state = readStoredSession();

    expect(state?.sessionId).toBe(SESSION);
    expect(state?.pendingSubmission).toBeNull();
  });

  it("thay toàn bộ state bằng bản đã lưu, giữ nguyên session_id", () => {
    const stored = {
      sessionId: "22222222-2222-2222-2222-222222222222",
      messages: [{ role: "user", text: "Toi can xe dien" }] as const,
      phase: "waiting_review",
      errorMessage: null,
      authRequired: false,
      pendingSubmission: null,
      deliveredReviewIds: ["review-9"],
      panel: EMPTY_TOUR_PANEL,
    } as const;

    const state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "restored",
      state: stored,
    });

    expect(state.sessionId).toBe("22222222-2222-2222-2222-222222222222");
    expect(state.phase).toBe("waiting_review");
    expect(state.messages).toHaveLength(1);
    expect(state.deliveredReviewIds).toEqual(["review-9"]);
  });
});

/**
 * Reducer là SEAM cuối trước khi dữ liệu tới màn hình.
 *
 * Bug thật (2026-08-28): `consultation-flow.tsx` gửi `vehicleDetails` vào
 * `dispatch`, nhánh `agent_answered` copy bảy trường khác NHƯNG bỏ rơi đúng
 * trường này — nên `message.vehicleDetails` luôn rỗng và thẻ chi tiết chưa
 * từng render trên prod dù backend đã gửi đủ.
 *
 * Test component cô lập không bắt được: chúng truyền props thẳng tay nên đi
 * vòng qua đúng chỗ hỏng. Bộ này đi qua reducer thật.
 * (`nextStepPanel` từng đi cùng đường này — đã bỏ ở đợt 10 cùng nút điều
 * hướng trong đoạn chat.)
 */
describe("payload giàu của một lượt", () => {
  const DETAILS: VehicleDetails = {
    vehicle_name: "VinFast VF 8",
    spec_groups: [{ title: "Giá bán", rows: [["Eco", "1.190.000.000 đồng"]] }],
  };

  it("giữ vehicleDetails vào đúng tin nhắn của lượt", () => {
    const state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_answered",
      text: "Dạ VF 8 phù hợp ạ.",
      vehicleDetails: DETAILS,
    });

    const message = state.messages.at(-1);
    expect(message?.vehicleDetails).toEqual(DETAILS);
  });

  it("lượt không có thẻ thì ghi null, không để trống", () => {
    // `undefined` bốc hơi khi state đi qua `JSON.stringify` của
    // `writeStoredSession`; `null` thì sống sót. Hai thứ render giống nhau hôm
    // nay, nhưng sau một lần tải lại trang chỉ `null` còn kể đúng câu chuyện
    // "lượt này không có thẻ".
    const state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_answered",
      text: "Dạ vâng ạ.",
    });

    const message = state.messages.at(-1);
    expect(message?.vehicleDetails).toBeNull();
  });

  it("lượt sau không kéo thẻ chi tiết của lượt trước theo", () => {
    // Thẻ đi CÙNG tin nhắn chứ không nằm ở state chung — khách chốt VF 8 rồi
    // hỏi tiếp một câu thường thì thẻ VF 8 phải đứng yên ở lượt cũ, không nhân
    // đôi xuống lượt mới.
    const first = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_answered",
      text: "Dạ VF 8 phù hợp ạ.",
      vehicleDetails: DETAILS,
    });

    const second = reduceAgentSession(first, {
      type: "agent_answered",
      text: "Dạ showroom mở 8h ạ.",
    });

    expect(second.messages.at(-1)?.vehicleDetails).toBeNull();
    expect(second.messages.at(-2)?.vehicleDetails).toEqual(DETAILS);
  });
});

/**
 * Panel "trang web đi theo hội thoại" là trạng thái CHUNG của phiên: một panel,
 * nội dung của lượt `navigate` gần nhất, lượt không có `navigate` thì giữ nguyên.
 */
describe("panel đi theo hội thoại", () => {
  const VEHICLE: TurnNavigate = { kind: "vehicle", vehicle_id: "v-5", slug: "vf-5", name: "VinFast VF 5" };
  const MAP: TurnNavigate = {
    kind: "map",
    vehicle_id: "v-5",
    center: { lat: 21.0, lng: 105.8 },
    showrooms: [
      { showroom_id: "sr-1", name: "VinFast Cầu Giấy", address: "HN", lat: 21.03, lng: 105.79, distance_km: 2.1 },
      { showroom_id: "sr-2", name: "VinFast Long Biên", address: "HN", lat: 21.04, lng: 105.88, distance_km: 6.4 },
    ],
    needs_location: false,
  };

  it("lượt có navigate thì MỞ panel với nội dung đó", () => {
    const state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: VEHICLE });

    expect(state.panel).toEqual({ open: true, navigate: VEHICLE, selectedShowroomId: null });
  });

  it("lượt sau KHÔNG có navigate thì panel giữ nguyên, không tự đóng", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: VEHICLE });
    state = reduceAgentSession(state, { type: "agent_answered", text: "Dạ showroom mở 8h ạ." });

    expect(state.panel.open).toBe(true);
    expect(state.panel.navigate).toEqual(VEHICLE);
  });

  it("navigate mới đè nội dung cũ và mở lại kể cả khi khách đã thu gọn", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: VEHICLE });
    state = reduceAgentSession(state, { type: "panel_toggled", open: false });
    expect(state.panel.open).toBe(false);
    expect(state.panel.navigate).toEqual(VEHICLE);

    state = reduceAgentSession(state, { type: "navigated", navigate: MAP });

    expect(state.panel.open).toBe(true);
    expect(state.panel.navigate).toEqual(MAP);
    // bản đồ mở ra thì ghim đầu (gần nhất) được chọn sẵn — khớp thẻ lái thử
    expect(state.panel.selectedShowroomId).toBe("sr-1");
  });

  it("test_drive_card_replaced với messageIndex -1: THÊM message mới mang thẻ (panel xin vị trí khi chat chưa có thẻ)", () => {
    // Bug Sếp 2026-08-31: khách cho vị trí từ PANEL lúc chat không có thẻ lái
    // thử nào — thẻ đầy đủ (có giờ) server trả về bị vứt, cửa sổ chỉ còn map
    // + showroom. -1 = không có thẻ cũ để thay → nối message mới, text rỗng
    // (bong bóng rỗng không render, chỉ thẻ hiện).
    const card = {
      vehicle_id: "v-5",
      vehicle_name: "VinFast VF 5",
      showrooms: [],
      days: [],
      options: [],
      default_showroom_id: "sr-1",
      default_date: "2026-09-01",
    };
    let state = createAgentSessionState(SESSION);
    state = reduceAgentSession(state, {
      type: "test_drive_card_replaced",
      messageIndex: -1,
      card,
      quickReplies: [{ label: "Đặt lịch", value: "dat lich" }],
    });

    const last = state.messages.at(-1);
    expect(last?.role).toBe("assistant");
    expect(last?.text).toBe("");
    expect(last?.testDriveCard).toEqual(card);
    expect(last?.quickReplies).toEqual([{ label: "Đặt lịch", value: "dat lich" }]);
  });

  it("bấm ghim đổi showroom đang chọn", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: MAP });
    state = reduceAgentSession(state, { type: "panel_showroom_picked", showroomId: "sr-2" });

    expect(state.panel.selectedShowroomId).toBe("sr-2");
  });

  it("bấm showroom khi panel bản đồ đang thu gọn thì panel MỞ LẠI (Sếp 2026-08-31)", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: MAP });
    state = reduceAgentSession(state, { type: "panel_toggled", open: false });

    state = reduceAgentSession(state, { type: "panel_showroom_picked", showroomId: "sr-2" });

    expect(state.panel.open).toBe(true);
    expect(state.panel.selectedShowroomId).toBe("sr-2");
  });

  it("bấm showroom khi panel đang bày trang XE (không phải bản đồ) thì không kéo panel mở", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: VEHICLE });
    state = reduceAgentSession(state, { type: "panel_toggled", open: false });

    state = reduceAgentSession(state, { type: "panel_showroom_picked", showroomId: "sr-2" });

    expect(state.panel.open).toBe(false);
  });

  it("panel sống qua F5; phiên lưu từ bản cũ không có panel thì rỗng", () => {
    window.sessionStorage.clear();
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: MAP });
    state = reduceAgentSession(state, { type: "customer_said", text: "ok" });
    writeStoredSession(state);

    expect(readStoredSession(SESSION)?.panel).toEqual(state.panel);

    window.sessionStorage.setItem(
      `p150.agent-session.${SESSION}`,
      JSON.stringify({ sessionId: SESSION, messages: [], phase: "chatting" }),
    );
    expect(readStoredSession(SESSION)?.panel).toEqual(EMPTY_TOUR_PANEL);
  });

  it("hội thoại mới thì panel về rỗng", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), { type: "navigated", navigate: MAP });
    state = reduceAgentSession(state, { type: "restarted", sessionId: "33333333-3333-3333-3333-333333333333" });

    expect(state.panel).toEqual(EMPTY_TOUR_PANEL);
  });
});

describe("reduceAgentSession — navigate xe không có trang chi tiết (đợt vá UI 2026-08-31)", () => {
  it("kind=vehicle slug RỖNG (xe máy): KHÔNG mở panel, KHÔNG thêm dòng hệ thống", () => {
    const state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "navigated",
      navigate: { kind: "vehicle", vehicle_id: "moto-1", slug: "", name: "Evo200" },
      note: "Em mở chi tiết Evo200 bên cạnh cho anh/chị ạ.",
    });

    expect(state.panel).toEqual(EMPTY_TOUR_PANEL);
    expect(state.messages).toHaveLength(0);
  });
});


describe("thẻ chi phí sống cả phiên (Sếp 2026-08-31)", () => {
  const tcoCardOf = (vehicleId: string, total: string): TcoCard => ({
    vehicle_id: vehicleId,
    vehicle_name: "VinFast VF 8",
    total_vnd: total,
    components: [],
    daily_distance_km: 30,
    daily_distance_known: false,
    province_code: null,
    region_code: "KHU_VUC_II",
    assumption_note: "",
  });

  it("lượt sau CÙNG xe: cập nhật thẻ ở message cũ tại chỗ, không mọc thẻ mới", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_answered",
      text: "Bảng chi phí đây ạ.",
      tcoCard: tcoCardOf("veh-1", "900000000"),
    });
    state = reduceAgentSession(state, { type: "customer_said", text: "anh ở Đà Nẵng cơ" });
    state = reduceAgentSession(state, {
      type: "agent_answered",
      text: "Dạ, em đã cập nhật lại bảng chi phí giúp anh/chị ạ.",
      tcoCard: tcoCardOf("veh-1", "905000000"),
    });

    // MỘT thẻ duy nhất, đứng nguyên vị trí cũ và mang số MỚI.
    expect(state.messages.filter((message) => message.tcoCard)).toHaveLength(1);
    expect(state.messages[0].tcoCard?.total_vnd).toBe("905000000");
    // Tin nhắn mới chỉ chở câu chữ xác nhận, không chở thẻ thứ hai.
    expect(state.messages.at(-1)?.tcoCard).toBeNull();
    expect(state.messages.at(-1)?.text).toContain("cập nhật");
  });

  it("xe KHÁC thì vẫn là thẻ mới như thường", () => {
    let state = reduceAgentSession(createAgentSessionState(SESSION), {
      type: "agent_answered",
      text: "Chi phí VF 8.",
      tcoCard: tcoCardOf("veh-1", "900000000"),
    });
    state = reduceAgentSession(state, {
      type: "agent_answered",
      text: "Chi phí VF 5.",
      tcoCard: tcoCardOf("veh-2", "600000000"),
    });

    expect(state.messages.filter((message) => message.tcoCard)).toHaveLength(2);
    expect(state.messages.at(-1)?.tcoCard?.vehicle_id).toBe("veh-2");
  });

  it("test_drive_cards_cleared: gỡ thẻ lái thử khỏi chat sau khi đặt xong, chữ giữ nguyên", () => {
    const card = {
      vehicle_id: "v-5",
      vehicle_name: "VinFast VF 5",
      showrooms: [],
      days: [],
      options: [],
      default_showroom_id: "sr-1",
      default_date: "2026-09-01",
    };
    let state = createAgentSessionState(SESSION);
    state = reduceAgentSession(state, { type: "test_drive_card_replaced", messageIndex: -1, card });
    state = reduceAgentSession(state, { type: "test_drive_cards_cleared" });

    expect(state.messages.some((m) => m.testDriveCard)).toBe(false);
    expect(state.messages.length).toBeGreaterThan(0);
  });
});
