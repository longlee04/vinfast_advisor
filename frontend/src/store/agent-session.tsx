"use client";

import { createContext, useContext, useEffect, useMemo, useReducer, useState } from "react";

import type {
  VehicleDetails,
  TurnNavigate,
  NearbyLocationList,
  TcoCard,
  TestDriveCard,
  QuickReply,
  RecommendedVehicle,
  VehicleComparison,
} from "@/types/agent";

export type ChatMessage = {
  /**
   * `system`: dòng hệ thống nhỏ ("Em mở chi tiết VF 5 bên cạnh cho anh/chị ạ")
   * — KHÔNG phải tin của bot, không bong bóng, không avatar, không vào preview
   * của danh sách hội thoại.
   */
  readonly role: "assistant" | "user" | "system";
  readonly text: string;
  /** Xe được đề xuất trong đúng lượt này; card dựng từ đây. */
  readonly vehicles?: readonly RecommendedVehicle[];
  /**
   * Tư vấn viên đã sửa nội dung: card vẫn hiện vì nó là dữ liệu catalog, nhưng
   * `pitch` do LLM viết bị ẩn — tư vấn viên là nguồn sự thật cuối.
   */
  readonly pitchHidden?: boolean;
  /**
   * Bảng so sánh của đúng lượt này. Đi cùng tin nhắn chứ không nằm ở state
   * chung: khách có thể so sánh nhiều lần trong một phiên, và một bảng "hiện
   * tại" duy nhất sẽ ghi đè bảng của lượt trước ngay trên màn hình.
   */
  readonly comparison?: VehicleComparison | null;
  /**
   * Danh sách địa điểm của đúng lượt này.
   */
  readonly nearbyLocations?: NearbyLocationList | null;
  /** Thẻ chi phí 5 năm khách chỉnh được tại chỗ. */
  readonly tcoCard?: TcoCard | null;
  /** Thẻ chọn showroom + khung giờ lái thử. */
  readonly testDriveCard?: TestDriveCard | null;
  readonly vehicleDetails?: VehicleDetails | null;
  // `nextStepPanel` đã bỏ (đợt 10): không còn nút điều hướng trong đoạn chat.
  // Phiên cũ trong sessionStorage còn mang trường này thì cứ nằm đó vô hại —
  // không ai đọc nữa.
  /** Nút bấm gợi ý của đúng lượt này. */
  readonly quickReplies?: readonly QuickReply[];
};

export type AgentPhase = "chatting" | "waiting_review" | "delivered" | "error";

/**
 * Panel "trang web đi theo hội thoại" (đợt 9, 2026-08-31) — trạng thái CHUNG
 * của phiên, không nằm trong từng tin nhắn: chỉ có MỘT panel, nội dung là của
 * lượt `navigate` gần nhất, và lượt sau không có `navigate` thì giữ nguyên (khách
 * vẫn đang xem thứ vừa mở). `open=false` là khách tự thu gọn — vẫn giữ
 * `navigate` để có nút mở lại.
 *
 * `selectedShowroomId` đồng bộ ghim trên bản đồ với cột showroom của thẻ lái
 * thử cùng lượt: bấm ghim = chọn showroom trong thẻ, và ngược lại.
 */
export type TourPanelState = {
  readonly open: boolean;
  readonly navigate: TurnNavigate | null;
  readonly selectedShowroomId: string | null;
};

export const EMPTY_TOUR_PANEL: TourPanelState = { open: false, navigate: null, selectedShowroomId: null };

export type PendingSubmission = {
  readonly id: string;
  readonly message: string;
  /**
   * Lượt do khách BẤM NÚT chứ không gõ — không dựng bong bóng tin nhắn cho nó.
   *
   * Sếp 2026-08-26: "không hiện lựa chọn của khách như 1 câu trả lời đưa vào vì
   * nó có trải nghiệm rất tệ". Khách bấm "Ô tô điện" rồi thấy đúng chữ đó nhảy
   * vào khung chat như thể mình vừa gõ — đọc như hệ thống đang diễn lại thao tác
   * của mình, không phải như một cuộc trò chuyện.
   *
   * Chỉ giấu Ở GIAO DIỆN. Giá trị vẫn gửi lên server y nguyên như một tin nhắn
   * bình thường, nên hai đường vào cho cùng một ý định (bấm và gõ) vẫn chạy qua
   * đúng một nhánh xử lý ở backend.
   */
  readonly silent?: boolean;
};

export type AgentSessionState = {
  readonly sessionId: string;
  readonly messages: readonly ChatMessage[];
  readonly phase: AgentPhase;
  readonly errorMessage: string | null;
  // Lỗi lần này là do chưa/hết đăng nhập. "Bắt đầu lại" không chữa được việc đó
  // nên màn lỗi phải đưa thẳng nút sang trang đăng nhập.
  readonly authRequired: boolean;
  readonly pendingSubmission: PendingSubmission | null;
  // Mục duyệt đã đưa vào dòng hội thoại. Không có danh sách này thì mỗi lần
  // `EventSource` bắn lại (reconnect, hoặc phiên có hai lượt được duyệt) nội
  // dung cũ bị chèn thêm một lần nữa.
  readonly deliveredReviewIds: readonly string[];
  readonly panel: TourPanelState;
};

export type AgentSessionEvent =
  | { readonly type: "customer_said"; readonly text: string }
  | { readonly type: "submission_started"; readonly submission: PendingSubmission }
  | { readonly type: "submission_cleared" }
  | { readonly type: "system_noted"; readonly text: string }
  | {
      readonly type: "agent_asked";
      readonly text: string;
      /**
       * Nút gợi ý đi KÈM CÂU HỎI. Trước đây nhánh này vứt `quick_replies` đi và
       * chỉ nhánh `agent_answered` giữ lại — nên đúng lúc agent hỏi "ô tô hay
       * xe máy" thì không có nút nào để bấm (Sếp 2026-08-25).
       */
      readonly quickReplies?: readonly QuickReply[];
      readonly comparison?: VehicleComparison | null;
      readonly nearbyLocations?: NearbyLocationList | null;
    }
  | {
      readonly type: "agent_answered";
      readonly text: string;
      readonly vehicles?: readonly RecommendedVehicle[];
      readonly comparison?: VehicleComparison | null;
      readonly nearbyLocations?: NearbyLocationList | null;
      readonly tcoCard?: TcoCard | null;
      readonly testDriveCard?: TestDriveCard | null;
      readonly vehicleDetails?: VehicleDetails | null;
      readonly quickReplies?: readonly QuickReply[];
      /**
       * `true` khi lượt này kết thúc bởi guardrail (`terminal_reason` khác
       * null): card catalog vẫn hiện nhưng backend đã trả `pitch=""` cho từng
       * xe (A6-1) — đặt cờ này để client đồng thuận, không dựa hoàn toàn vào
       * backend (defense in depth), và để UI biết KHÔNG được ẩn bong bóng
       * trả lời (bong bóng là chỗ duy nhất khách đọc được nội dung lượt này).
       */
      readonly pitchHidden?: boolean;
    }
  | {
      readonly type: "agent_finished";
      readonly text: string;
      readonly vehicles?: readonly RecommendedVehicle[];
      /**
       * Lượt "chọn xe xong" thường đi qua nhánh này (bản nháp vào hàng đợi
       * duyệt) và backend vẫn gửi kèm 4 gợi ý (chi phí / lăn bánh / lái thử /
       * ưu đãi). Trước đây nhánh này vứt chúng đi nên ô gõ im bặt đúng lúc
       * khách vừa chốt mẫu — "gợi ý bị fail sau khi chọn xe" (Sếp 2026-08-30).
       */
      readonly quickReplies?: readonly QuickReply[];
    }
  | {
      readonly type: "delivered";
      readonly text: string;
      readonly reviewId: string;
      readonly vehicles?: readonly RecommendedVehicle[];
    }
  | {
      /**
       * Thẻ lái thử tự đổi TẠI CHỖ sau khi khách cho vị trí ngay trên thẻ
       * (`/agent/test-drive/options`). Không thêm message mới: cùng một lượt,
       * chỉ thẻ "xin vị trí" biến thành thẻ đủ showroom/giờ. Gợi ý của lượt đi
       * theo thẻ mới để ô gõ xoay đúng việc kế tiếp.
       *
       * `messageIndex: -1` = chat CHƯA có thẻ nào để thay (khách cho vị trí từ
       * panel bản đồ) → NỐI message assistant mới mang thẻ, text rỗng (bong
       * bóng rỗng không render). Trước đây nhánh này vứt thẻ trong im lặng:
       * panel còn map + showroom mà không bao giờ có khung giờ (Sếp 2026-08-31).
       */
      readonly type: "test_drive_card_replaced";
      readonly messageIndex: number;
      readonly card: TestDriveCard;
      readonly quickReplies?: readonly QuickReply[];
    }
  | {
      /** Lượt có `navigate`: mở panel với nội dung mới (đè nội dung cũ nếu có). */
      readonly type: "navigated";
      readonly navigate: TurnNavigate;
      /** Dòng hệ thống thêm vào chat khi cửa sổ MỞ TỰ ĐỘNG theo lượt (không khi khách tự mở lại). */
      readonly note?: string;
    }
  | { readonly type: "panel_toggled"; readonly open: boolean }
  | { readonly type: "panel_showroom_picked"; readonly showroomId: string }
  | { readonly type: "test_drive_cards_cleared" }
  | { readonly type: "failed"; readonly message: string; readonly authRequired?: boolean }
  | { readonly type: "restarted"; readonly sessionId: string }
  | { readonly type: "restored"; readonly state: AgentSessionState };

export function createAgentSessionState(sessionId: string): AgentSessionState {
  return {
    sessionId,
    messages: [],
    phase: "chatting",
    errorMessage: null,
    authRequired: false,
    pendingSubmission: null,
    deliveredReviewIds: [],
    panel: EMPTY_TOUR_PANEL,
  };
}

/** Ghim chọn sẵn khi panel bản đồ mở: showroom đầu (gần nhất) — khớp `default_showroom_id` của thẻ. */
function defaultShowroomOf(navigate: TurnNavigate): string | null {
  return navigate.kind === "map" ? (navigate.showrooms[0]?.showroom_id ?? null) : null;
}

/** Chỉ gửi prompt từ URL sau khi khôi phục phiên và khi chưa có hội thoại cũ. */
export function shouldSendInitialPrompt(
  initialPrompt: string | undefined,
  sessionReady: boolean,
  messages: readonly ChatMessage[],
): boolean {
  return sessionReady && messages.length === 0 && Boolean(initialPrompt?.trim());
}

function withMessage(
  state: AgentSessionState,
  message: ChatMessage,
  phase: AgentPhase,
): AgentSessionState {
  return { ...state, messages: [...state.messages, message], phase, errorMessage: null, authRequired: false };
}

export function reduceAgentSession(
  state: AgentSessionState,
  event: AgentSessionEvent,
): AgentSessionState {
  switch (event.type) {
    case "customer_said":
      return withMessage(state, { role: "user", text: event.text }, "chatting");
    case "submission_started":
      if (state.pendingSubmission) {
        return { ...state, phase: "chatting", errorMessage: null, authRequired: false };
      }
      if (event.submission.silent) {
        return {
          ...state,
          phase: "chatting",
          errorMessage: null,
          authRequired: false,
          pendingSubmission: event.submission,
        };
      }
      return {
        ...withMessage(state, { role: "user", text: event.submission.message }, "chatting"),
        pendingSubmission: event.submission,
      };
    case "submission_cleared":
      return { ...state, pendingSubmission: null };
    case "agent_asked":
      return {
        ...withMessage(
          state,
          {
            role: "assistant",
            text: event.text,
            quickReplies: event.quickReplies ?? [],
            comparison: event.comparison ?? null,
            nearbyLocations: event.nearbyLocations ?? null,
          },
          "chatting",
        ),
        pendingSubmission: null,
      };
    // Agent trả lời trong lượt nhưng KHÔNG bàn giao tư vấn viên: từ chối ngoài
    // phạm vi (`terminal_reason` khác null) hoặc tra cứu catalog thuần
    // (`lookup_facts`). Phiên vẫn ở trạng thái chat bình thường, không mở SSE.
    case "agent_answered": {
      // Sếp 2026-08-31: MỘT thẻ chi phí sống cả phiên cho mỗi xe. Lượt mới mang
      // `tcoCard` CÙNG vehicle_id với một thẻ đã có trong lịch sử thì CẬP NHẬT
      // thẻ cũ tại chỗ (giữ nguyên vị trí trong dòng hội thoại; component tự
      // nháy viền khi prop đổi) — tin nhắn mới chỉ chở câu chữ "em đã cập
      // nhật", KHÔNG mọc thẻ thứ hai. Xe KHÁC thì vẫn là thẻ mới như thường.
      const incomingCard = event.tcoCard ?? null;
      // Không dùng findLastIndex: tsconfig target ES2017 chưa có nó.
      let holderIndex = -1;
      if (incomingCard) {
        for (let index = state.messages.length - 1; index >= 0; index -= 1) {
          const candidate = state.messages[index];
          if (candidate.role === "assistant" && candidate.tcoCard?.vehicle_id === incomingCard.vehicle_id) {
            holderIndex = index;
            break;
          }
        }
      }
      const base =
        holderIndex >= 0
          ? {
              ...state,
              messages: state.messages.map((message, index) =>
                index === holderIndex ? { ...message, tcoCard: incomingCard } : message,
              ),
            }
          : state;
      return {
        ...withMessage(
          base,
          {
            role: "assistant",
            text: event.text,
            vehicles: event.vehicles ?? [],
            pitchHidden: event.pitchHidden ?? false,
            comparison: event.comparison ?? null,
            nearbyLocations: event.nearbyLocations ?? null,
            tcoCard: holderIndex >= 0 ? null : incomingCard,
            testDriveCard: event.testDriveCard ?? null,
            // Trường này từng bị bỏ rơi ở đúng chỗ này: `consultation-flow`
            // gửi nó vào dispatch, reducer copy bảy trường bên trên rồi
            // dừng — nên `message.vehicleDetails` luôn rỗng và thẻ chi tiết
            // chưa lần nào tới khách dù backend đã gửi đủ. `?? null` chứ không
            // để trống: `undefined` bốc hơi khi state đi qua `JSON.stringify`
            // của `writeStoredSession`, và sau reload thì không còn phân biệt
            // được "lượt này không có thẻ" với "thẻ đã rơi mất".
            vehicleDetails: event.vehicleDetails ?? null,
            quickReplies: event.quickReplies ?? [],
          },
          "chatting",
        ),
        pendingSubmission: null,
      };
    }
    // Lượt cuối của agent chỉ báo đã đẩy sang hàng đợi; nội dung thật chỉ đến
    // qua `/agent/deliveries` sau khi tư vấn viên duyệt. `pitch` từng xe (nếu
    // backend chưa kịp gỡ) là văn bản LLM CHƯA được duyệt — client tự ẩn thêm
    // một lớp (defense in depth), không phụ thuộc hoàn toàn vào backend.
    case "agent_finished":
      return {
        ...withMessage(
          state,
          {
            role: "assistant",
            text: event.text,
            vehicles: event.vehicles ?? [],
            pitchHidden: true,
            quickReplies: event.quickReplies ?? [],
          },
          "waiting_review",
        ),
        pendingSubmission: null,
      };
    case "delivered": {
      if (state.deliveredReviewIds.includes(event.reviewId)) return state;
      const delivered = withMessage(
        state,
        // Nội dung tư vấn viên gửi là bản cuối: hiện nó thành MỘT khối chung,
        // ẩn pitch từng xe để không mâu thuẫn với bản đã sửa.
        { role: "assistant", text: event.text, vehicles: event.vehicles ?? [], pitchHidden: true },
        "delivered",
      );
      return {
        ...delivered,
        deliveredReviewIds: [...state.deliveredReviewIds, event.reviewId],
      };
    }
    case "test_drive_card_replaced": {
      if (event.messageIndex < 0) {
        return {
          ...state,
          messages: [
            ...state.messages,
            { role: "assistant", text: "", testDriveCard: event.card, quickReplies: event.quickReplies ?? [] },
          ],
        };
      }
      const target = state.messages[event.messageIndex];
      if (!target || target.role !== "assistant") return state;
      const messages = state.messages.map((message, index) =>
        index === event.messageIndex
          ? {
              ...message,
              testDriveCard: event.card,
              quickReplies: event.quickReplies ?? message.quickReplies ?? [],
            }
          : message,
      );
      return { ...state, messages };
    }
    case "system_noted": {
      // Dòng hệ thống nhỏ cho những lượt bot CỐ Ý im (tư vấn viên đang cầm
      // phiên). Không có nó, khách gõ vào khoảng không: lượt đã tới server,
      // server trả `answer=""`, và giao diện không hiện gì cả (đo 2026-09-23).
      //
      // Lặp lại y nguyên dòng vừa hiện thì bỏ qua: khách nhắn ba câu liên tiếp
      // không cần ba dòng giống hệt nhau.
      const last = state.messages[state.messages.length - 1];
      if (last && last.role === "system" && last.text === event.text) return state;
      return { ...state, messages: [...state.messages, { role: "system", text: event.text }] };
    }
    case "navigated": {
      // Xe máy chưa có trang chi tiết: backend có thể gửi kind=vehicle với slug
      // RỖNG. Mở panel lúc đó chỉ ra khung "chưa có trang" + link /vehicles/
      // trống — bỏ qua trọn gói: không panel, không dòng hệ thống.
      if (event.navigate.kind === "vehicle" && event.navigate.slug.trim() === "") return state;
      // Lượt mới có `navigate` thì MỞ LẠI kể cả khi khách đã thu gọn: nội dung
      // đổi rồi, thu gọn cũ không còn là ý của khách với nội dung này.
      const panel = { open: true, navigate: event.navigate, selectedShowroomId: defaultShowroomOf(event.navigate) };
      if (!event.note) return { ...state, panel };
      return { ...state, panel, messages: [...state.messages, { role: "system", text: event.note }] };
    }
    case "test_drive_cards_cleared": {
      // Đặt lịch xong (Sếp 2026-08-31): BẢNG chọn giờ đã xong việc — để lại
      // là mời khách bấm tiếp một lịch nữa ngay dưới câu xác nhận. Gỡ thẻ khỏi
      // mọi message, chữ của lượt giữ nguyên.
      if (!state.messages.some((message) => message.testDriveCard)) return state;
      return {
        ...state,
        messages: state.messages.map((message) =>
          message.testDriveCard ? { ...message, testDriveCard: null } : message,
        ),
      };
    }
    case "panel_toggled":
      return { ...state, panel: { ...state.panel, open: event.open } };
    case "panel_showroom_picked":
      // Bấm showroom trong THẺ lái thử lúc panel bản đồ đang thu gọn thì mở lại
      // (Sếp 2026-08-31: "click showroom sẽ hiện showroom đó trên map"): đổi
      // ghim trong một panel đang giấu là khách không thấy gì đổi. Panel đang
      // bày trang XE thì giữ nguyên — bấm showroom không phải ý xin xem trang xe.
      return {
        ...state,
        panel: {
          ...state.panel,
          open: state.panel.navigate?.kind === "map" ? true : state.panel.open,
          selectedShowroomId: event.showroomId,
        },
      };
    case "failed":
      return { ...state, phase: "error", errorMessage: event.message, authRequired: event.authRequired ?? false };
    case "restarted":
      return createAgentSessionState(event.sessionId);
    case "restored":
      return event.state;
  }
}

const STORAGE_KEY = "p150.agent-session";
const STORAGE_PREFIX = "p150.agent-session.";

/** Đọc phiên đã lưu; trả `null` khi không có, sai định dạng, hoặc trên server. */
export function readStoredSession(targetSessionId?: string): AgentSessionState | null {
  if (typeof window === "undefined") return null;
  try {
    const key = targetSessionId ? `${STORAGE_PREFIX}${targetSessionId}` : STORAGE_KEY;
    let raw = window.sessionStorage.getItem(key);
    if (!raw && targetSessionId) {
      const fallbackRaw = window.sessionStorage.getItem(STORAGE_KEY);
      if (fallbackRaw) {
        const parsedFallback = JSON.parse(fallbackRaw) as Partial<AgentSessionState>;
        if (parsedFallback.sessionId === targetSessionId) {
          raw = fallbackRaw;
        }
      }
    }
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<AgentSessionState>;
    if (typeof parsed.sessionId !== "string" || !Array.isArray(parsed.messages)) return null;
    if (targetSessionId && parsed.sessionId !== targetSessionId) return null;
    return {
      sessionId: parsed.sessionId,
      messages: parsed.messages as ChatMessage[],
      // Trạng thái lỗi không đáng khôi phục: người dùng vừa tải lại trang chính
      // là để thoát khỏi nó.
      phase: parsed.phase === "error" || !parsed.phase ? "chatting" : parsed.phase,
      errorMessage: null,
      authRequired: false,
      pendingSubmission:
        parsed.pendingSubmission &&
        typeof parsed.pendingSubmission.id === "string" &&
        typeof parsed.pendingSubmission.message === "string"
          ? parsed.pendingSubmission
          : null,
      deliveredReviewIds: Array.isArray(parsed.deliveredReviewIds)
        ? (parsed.deliveredReviewIds as string[])
        : [],
      // Panel sống qua F5: khách đang xem chi tiết xe/bản đồ thì tải lại trang
      // không được làm nó biến mất. Phiên lưu từ bản cũ không có `panel` → rỗng.
      panel:
        parsed.panel && typeof parsed.panel === "object" && "navigate" in parsed.panel
          ? {
              open: Boolean(parsed.panel.open),
              navigate: parsed.panel.navigate ?? null,
              selectedShowroomId: parsed.panel.selectedShowroomId ?? null,
            }
          : EMPTY_TOUR_PANEL,
    };
  } catch {
    return null;
  }
}

export function clearStoredSession(sessionId?: string): void {
  if (typeof window === "undefined") return;
  try {
    if (sessionId) {
      window.sessionStorage.removeItem(`${STORAGE_PREFIX}${sessionId}`);
    }
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Cùng lý do với `writeStoredSession`: không đáng làm hỏng lượt đang chạy.
  }
}

export function writeStoredSession(state: AgentSessionState): void {
  if (typeof window === "undefined" || !state.sessionId) return;
  try {
    const serialized = JSON.stringify(state);
    window.sessionStorage.setItem(STORAGE_KEY, serialized);
    window.sessionStorage.setItem(`${STORAGE_PREFIX}${state.sessionId}`, serialized);
  } catch {
    // Chế độ riêng tư hoặc hết quota: mất khả năng khôi phục sau F5 là phiền,
    // nhưng không đáng làm hỏng cuộc hội thoại đang diễn ra.
  }
}

type AgentSessionStore = {
  readonly state: AgentSessionState;
  readonly dispatch: (event: AgentSessionEvent) => void;
  readonly ready: boolean;
  readonly isRestored: boolean;
};

const AgentSessionContext = createContext<AgentSessionStore | null>(null);

export function AgentSessionProvider({
  conversationId,
  children,
}: Readonly<{ conversationId?: string; children: React.ReactNode }>): React.JSX.Element {
  const [state, dispatch] = useReducer(
    reduceAgentSession,
    null,
    () => createAgentSessionState(conversationId || ""),
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!conversationId) {
      clearStoredSession();
      if (!state.sessionId) {
        dispatch({ type: "restarted", sessionId: crypto.randomUUID() });
      }
      setReady(true);
      return;
    }
    const stored = readStoredSession(conversationId);
    if (stored && stored.sessionId === conversationId) {
      dispatch({ type: "restored", state: stored });
    }
    setReady(true);
  }, [conversationId, state.sessionId]);

  useEffect(() => {
    if (!ready) return;
    writeStoredSession(state);
  }, [ready, state]);

  const store = useMemo<AgentSessionStore>(
    () => ({ state, dispatch, ready, isRestored: ready }),
    [ready, state],
  );
  return <AgentSessionContext.Provider value={store}>{children}</AgentSessionContext.Provider>;
}

export function useAgentSession(): AgentSessionStore {
  const store = useContext(AgentSessionContext);
  if (!store) throw new Error("useAgentSession must be used inside AgentSessionProvider");
  return store;
}
