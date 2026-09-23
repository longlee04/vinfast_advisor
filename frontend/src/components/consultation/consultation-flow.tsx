"use client";

import { AlertCircle, ArrowLeft, Headset, History, LogIn, PanelRightOpen, Plus, RotateCcw, Send } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { AgentComparison } from "@/components/consultation/agent-comparison";
import { RichText } from "@/components/common/rich-text";
import { ConversationMessage } from "@/components/consultation/conversation-message";
import { ConversationHistorySidebar } from "@/components/customer/conversation-history-sidebar";
import { setCachedPreview } from "@/lib/conversation-helpers";
import { LocationRequest } from "@/components/consultation/location-request";
import { TcoCard } from "./tco-card";
import { TestDriveCard, type LocateWhere } from "./test-drive-card";
import { TourPanel } from "./tour-panel";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";
import { VehicleDetailsCard } from "./vehicle-details-card";
import { NearbyLocationCards } from "@/components/consultation/nearby-location-list";
import { PendingApproval } from "@/components/consultation/pending-approval";
import { TypingIndicator } from "@/components/consultation/typing-indicator";
import { VehiclePitchList } from "@/components/consultation/vehicle-pitch-list";
import {
  AgentApiError,
  fetchAllConversationMessages,
  fetchConversationMessages,
  fetchDeliveries,
  postNearestLocation,
  sendTurn,
} from "@/lib/api/agent";
import type {
  ConversationDetail,
  ConversationMessage as ConversationMessageDTO,
  LocationKind,
  QuickReply,
  TestDriveCard as TestDriveCardData,
  TestDriveOptionsResponse,
  TurnNavigate,
} from "@/types/agent";
import { createAgentSessionState, readStoredSession, useAgentSession } from "@/store/agent-session";

// Lời chào của màn chat trống. Trùng nguyên văn `nodes/classify_scope.SOCIAL_REPLY`
// — câu backend đáp khi khách chào — nên hai đường vào nói cùng một giọng.
//
// KHÔNG hỏi ngay ô tô hay xe máy (Sếp 2026-08-25): khách mở màn chat có thể chỉ
// muốn TRA CỨU giá hay thông tin, ép chọn loại xe ngay là hỏi sai câu đầu tiên.
// Nút chọn loại xe chỉ hiện khi backend thật sự bắt được ý định tư vấn và gửi
// kèm `quick_replies` (`nodes/ask_or_retrieve.VEHICLE_TYPE_CHOICES`).
// Sếp 2026-08-31 (cách B): bot KHÔNG mở lời. Khung chat mở trống, chỉ có dòng mờ
// mời hỏi; thiện cảm đến từ câu trả lời đầu tiên, không từ lời chào.
const NO_ANSWER_FALLBACK = "Mình chưa hỗ trợ được yêu cầu này, bạn thử diễn đạt lại nhé.";
// Không có gợi ý nào (chưa có lượt trợ lý, hoặc lượt đó không kèm quick_replies)
// thì rơi về đúng chữ tĩnh cũ — hành vi hiện tại KHÔNG đổi trong trường hợp này.
// Sếp 2026-08-31: trong đoạn chat KHÔNG gợi ý gì nữa (không nút, không chữ mờ,
// không "Ví dụ: …"). Gợi ý chỉ còn ở sảnh chính. `quick_replies` backend vẫn
// gửi — client bỏ qua.
// Rút gọn (đợt vá 2026-08-31): câu dài cũ tràn/đứt trên ô hẹp.
const COMPOSER_PLACEHOLDER = "Hỏi em về giá, sạc, chọn xe…";

// 401 gồm cả hai trường hợp: chưa đăng nhập bao giờ, và phiên hết hạn. Câu chữ
// phải đúng cho cả hai vì phía client không phân biệt được.
function isAuthError(error: unknown): boolean {
  return error instanceof AgentApiError && (error.status === 401 || error.status === 403);
}

/** Gộp mọi khoảng trắng về một dấu cách — so chữ giữa bong bóng và thẻ xe. */
function squashSpaces(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function messageForError(error: unknown): string {
  if (isAuthError(error)) {
    return "Bạn cần đăng nhập để tiếp tục hội thoại.";
  }
  if (error instanceof AgentApiError) return `Không gửi được lượt chat (${error.status}).`;
  return "Không kết nối được tới máy chủ.";
}

// Dòng hệ thống đi kèm khi cửa sổ mở TỰ ĐỘNG theo lượt — để khách hiểu vì sao
// màn hình vừa đổi, nhưng không giả làm một câu của bot.
function navigateNote(navigate: TurnNavigate): string {
  return navigate.kind === "vehicle"
    ? `Em dẫn anh/chị qua xem tận nơi ${navigate.name} nhé — chi tiết em mở sẵn ngay bên cạnh đây ạ.`
    : "Em dẫn anh/chị qua bản đồ showroom bên cạnh, mình chọn chỗ nào tiện đường nhất nhé ạ.";
}

function formatVnd(value: unknown): string {
  if (typeof value !== "string") return "chưa có giá hiệu lực";
  const amount = Number(value);
  return Number.isFinite(amount) ? `${amount.toLocaleString("vi-VN")} đ` : value;
}

// `lookup_facts` là tra cứu catalog thuần (khách hỏi tên xe cụ thể), không phải
// đề xuất — không qua HITL nên phải tự dựng câu trả lời đọc được ở đây, không
// hiện JSON thô.
function summarizeLookupFacts(facts: readonly Record<string, unknown>[]): string {
  return facts
    .map((fact) => {
      const name = typeof fact.display_name === "string" ? fact.display_name : "Xe";
      return `${name}: giá từ ${formatVnd(fact.starting_price_vnd)}.`;
    })
    .join("\n");
}

export function ConsultationFlow({
  initialPrompt: propInitialPrompt,
  initialConversationId,
}: Readonly<{ initialPrompt?: string; initialConversationId?: string }> = {}) {
  const { state, dispatch, ready } = useAgentSession();
  const searchParams = useSearchParams();
  const activeConversationId = searchParams.get("conversation") || initialConversationId;
  const urlPrompt = searchParams.get("prompt")?.trim() || "";
  const fromParam = searchParams.get("from")?.trim() || "";
  const initialPrompt = propInitialPrompt || urlPrompt;

  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const loadedConversationId = useRef<string | undefined>(undefined);
  // Đọc phiên hiện tại trong hiệu ứng tải hội thoại mà KHÔNG đưa nó vào deps.
  //
  // Đưa vào deps là một cái bẫy: nút "Hội thoại mới" đổi `sessionId` bằng
  // `window.history.pushState`, mà `pushState` không phải điều hướng của Next
  // nên `useSearchParams()` vẫn trả id CŨ. Hiệu ứng sẽ chạy lại với id cũ đó và
  // kéo hội thoại cũ về đè lên hội thoại vừa tạo — đúng cái lỗi đang đi chữa.
  const sessionIdRef = useRef(state.sessionId);
  const messageCountRef = useRef(state.messages.length);
  // Đồng bộ trong hiệu ứng, không gán thẳng lúc render (`react-hooks/refs`).
  // Khai báo TRƯỚC hiệu ứng tải hội thoại: hiệu ứng chạy theo thứ tự khai báo,
  // nên hiệu ứng dưới luôn đọc được giá trị của đúng lần render này.
  useEffect(() => {
    sessionIdRef.current = state.sessionId;
    messageCountRef.current = state.messages.length;
  }, [state.sessionId, state.messages.length]);

  useEffect(() => {
    if (!ready || !activeConversationId || loadedConversationId.current === activeConversationId) return;

    // 1. Kiểm tra session cục bộ (giữ nguyên toàn bộ card, địa điểm, bảng so sánh và tin nhắn)
    const localStored = readStoredSession(activeConversationId);
    if (localStored && localStored.messages.length > 0) {
      loadedConversationId.current = activeConversationId;
      dispatch({ type: "restored", state: localStored });
      return;
    }

    // Phiên trong tab ĐÃ là hội thoại này thì không tải lại từ server.
    if (sessionIdRef.current === activeConversationId && messageCountRef.current > 0) {
      loadedConversationId.current = activeConversationId;
      return;
    }
    loadedConversationId.current = activeConversationId;
    // Nội dung hội thoại cũ lấy từ `GET /conversations/{id}/messages`, KHÔNG
    // phải từ `GET /conversations/{id}`.
    //
    // Bug thật Sếp báo 2026-08-26: mở một hội thoại cũ ra khung chat TRỐNG.
    // Đường cũ gọi `fetchConversation` và đọc `conversation.messages`, nhưng
    // `ConversationResponse` của backend chỉ có `conversation_id`, `state`,
    // `created_at`, `last_activity_at`, `archived_at` — **không có `messages`**.
    // Chỉ endpoint của TƯ VẤN VIÊN mới trả kèm nội dung.
    //
    // Và `|| []` đứng ngay đó biến "field không tồn tại" thành "hội thoại
    // rỗng": không lỗi, không log, khách chỉ thấy màn hình trắng. Bỏ hẳn nó —
    // endpoint mới luôn trả `items`, còn hỏng thật thì phải rơi vào `catch`.
    void fetchAllConversationMessages(activeConversationId)
      .then((messages) => {
        dispatch({
          type: "restored",
          state: {
            ...createAgentSessionState(activeConversationId),
            messages: messages.map((message) => ({
              role: message.role.toUpperCase() === "USER" ? "user" : "assistant",
              text: message.content,
            })),
          },
        });
      })
      .catch(() => dispatch({ type: "failed", message: "Không tải được nội dung phiên chat này." }));
  }, [dispatch, activeConversationId, ready]);

  const handleNewConversation = useCallback(() => {
    loadedConversationId.current = undefined;
    if (typeof window !== "undefined") {
      window.sessionStorage.removeItem("p150.agent-session");
      window.history.pushState({}, "", "/consultation");
    }
    dispatch({ type: "restarted", sessionId: crypto.randomUUID() });
  }, [dispatch]);

  const sendMessage = useCallback(
    async (rawMessage: string, options?: { readonly silent?: boolean }): Promise<void> => {
      const message = rawMessage.trim();
      // `pendingSubmission` giữ nguyên `client_turn_id` khi khách bấm gửi lại:
      // server khử trùng lặp theo id đó, nên một lượt lỗi mạng không sinh ra hai
      // lượt tư vấn.
      if ((!message && !state.pendingSubmission) || sending) return;
      // `silent` chỉ đi kèm lượt MỚI. Lượt gửi lại giữ nguyên submission cũ —
      // kể cả cách hiển thị, nếu không thì bong bóng của lần gửi trước biến mất
      // hoặc mọc thêm giữa chừng.
      const submission = state.pendingSubmission ?? {
        id: crypto.randomUUID(),
        message,
        silent: options?.silent,
      };
      setDraft("");
      setSending(true);
      dispatch({ type: "submission_started", submission });
      try {
        const turn = await sendTurn(state.sessionId, submission.id, submission.message);
        if (turn.terminal_reason === "ADVISOR_ACTIVE") {
          // Tư vấn viên đang trực tiếp chat với khách, bot giữ im lặng. Phải xoá
          // submission: lượt này ĐÃ tới server, giữ lại id cũ thì lần gửi sau bị
          // server khử trùng lặp và câu mới không bao giờ được xử lý.
          dispatch({ type: "submission_cleared" });
          return;
        }
        // `awaiting_review` là thứ DUY NHẤT quyết định có dựng màn chờ duyệt hay
        // không, và nó do server nói ra (A7-4). Suy từ hình dạng câu trả lời là
        // sai kể từ khi giá niêm yết được trả thẳng: lượt đó cũng có `answer` khác
        // null và `terminal_reason` null, y hệt lượt đã vào hàng đợi — nên UI cũ
        // dựng "đang chờ tư vấn viên" ngay dưới một câu trả lời đã hoàn tất.
        const vehicles = turn.tco_card ? [] : turn.recommendations ?? [];
        // "Trang web đi theo hội thoại": độc lập với nhánh bên dưới, vì lượt
        // chốt xe có thể đi qua `agent_finished` (vào hàng đợi duyệt) chứ không
        // chỉ `agent_answered`. Không có `navigate` thì KHÔNG đụng panel.
        if (turn.navigate) dispatch({ type: "navigated", navigate: turn.navigate, note: navigateNote(turn.navigate) });
        // Đặt lịch lái thử xong (lượt là mã giờ đã ký) → panel bản đồ tự thu
        // lại: việc của nó xong rồi, để mở là che mất câu cảm ơn + xác nhận
        // (Sếp 2026-08-31 "đặt lịch xong thì phải tự động thụt map vào").
        if (submission.message.startsWith("__lichlaithu__") && !turn.terminal_reason) {
          dispatch({ type: "panel_toggled", open: false });
          dispatch({ type: "test_drive_cards_cleared" });
        }
        if (turn.awaiting_review) {
          dispatch({
            type: "agent_finished",
            text: turn.answer || NO_ANSWER_FALLBACK,
            vehicles,
            quickReplies: turn.quick_replies ?? [],
          });
        } else if (turn.terminal_reason) {
          // Guardrail đã chặn bản nháp (A6-1): backend trả `pitch=""` cho từng
          // card, còn `answer` mang câu báo đã chuyển tư vấn viên — đó là nội
          // dung DUY NHẤT khách đọc được, nên đánh dấu `pitchHidden` để bong
          // bóng không bị màn cards-only (I3) nuốt mất.
          dispatch({
            type: "agent_answered",
            text: turn.answer || NO_ANSWER_FALLBACK,
            vehicles,
            pitchHidden: true,
          });
        } else if (turn.pending_question) {
          dispatch({
            type: "agent_asked",
            text: turn.pending_question,
            quickReplies: turn.quick_replies ?? [],
            nearbyLocations: turn.nearby_locations ?? null,
            comparison: turn.comparison ?? null,
          });
        } else if (turn.answer) {
          // Lượt so sánh đi qua đúng nhánh này: nó có `answer` (toàn văn bảng
          // dạng chữ, cho client chưa render bảng) và có thêm `comparison`.
          dispatch({
            type: "agent_answered",
            text: turn.answer,
            vehicles,
            comparison: turn.comparison ?? null,
            nearbyLocations: turn.nearby_locations ?? null,
            tcoCard: turn.tco_card ?? null,
            testDriveCard: turn.test_drive_card ?? null,
            quickReplies: turn.quick_replies ?? [],
            vehicleDetails: turn.vehicle_details ?? null,
            // `turn.next_step_panel` bị BỎ QUA có chủ đích (đợt 10): nút điều
            // hướng trong đoạn chat làm khách rời mạch trò chuyện — backend vẫn
            // gửi trường này cho client cũ, client mới không dựng panel nữa.
          });
        } else if (turn.lookup_facts.length > 0) {
          dispatch({ type: "agent_answered", text: summarizeLookupFacts(turn.lookup_facts) });
        } else {
          dispatch({ type: "submission_cleared" });
          dispatch({ type: "failed", message: "Agent không trả lời được lượt này." });
        }
      } catch (error) {
        if (error instanceof AgentApiError && error.status < 500) {
          // Lỗi 4xx là lỗi của chính nội dung lượt — gửi lại cùng id chỉ nhận
          // lại đúng lỗi đó, nên bỏ submission và trả chữ về ô nhập.
          dispatch({ type: "submission_cleared" });
          setDraft(message);
        } else {
          setDraft(submission.message);
        }
        dispatch({ type: "failed", message: messageForError(error), authRequired: isAuthError(error) });
      } finally {
        setSending(false);
      }
    },
    [dispatch, sending, state.pendingSubmission, state.sessionId],
  );

  const resolveWithCoordinates = useCallback(
    async (
      position: { latitude: number; longitude: number },
      locationTypes: readonly string[],
    ): Promise<void> => {
      if (sending) return;
      setSending(true);
      try {
        const found = await postNearestLocation({
          ...position,
          locationType: locationTypes as readonly LocationKind[],
          sessionId: state.sessionId,
        });
        dispatch({
          type: "agent_answered",
          text: found.reply_text,
           nearbyLocations: found,
           quickReplies: found.quick_replies ?? [],

        });
      } catch (error) {
        dispatch({ type: "failed", message: messageForError(error), authRequired: isAuthError(error) });
      } finally {
        setSending(false);
      }
    },
    [dispatch, sending, state.sessionId],
  );

  // Thẻ lái thử vừa có showroom (khách cho vị trí — từ thẻ trong chat HOẶC từ
  // panel bản đồ): thay thẻ tại chỗ ở đúng lượt, và mở/cập nhật bản đồ. Backend
  // gửi `navigate` kèm thì dùng luôn; không thì dựng bản đồ tối thiểu với toạ
  // độ GPS (nếu có) — ghim showroom cần toạ độ mà thẻ không chở.
  const handleTestDriveFound = useCallback(
    (
      messageIndex: number,
      card: TestDriveCardData,
      quickReplies: readonly QuickReply[],
      navigate: TurnNavigate | null | undefined,
      where: LocateWhere | null,
    ): void => {
      dispatch({ type: "test_drive_card_replaced", messageIndex, card, quickReplies });
      if (navigate) {
        dispatch({ type: "navigated", navigate });
        return;
      }
      if (state.panel.navigate?.kind !== "map") return;
      const center = where && "latitude" in where ? { lat: where.latitude, lng: where.longitude } : null;
      dispatch({
        type: "navigated",
        navigate: { kind: "map", vehicle_id: card.vehicle_id, center, showrooms: [], needs_location: false },
      });
    },
    [dispatch, state.panel.navigate],
  );

  // Panel xin vị trí xong: thẻ cần thay là thẻ lái thử GẦN NHẤT trong chat.
  // Chat chưa có thẻ nào thì index = -1 và store NỐI message mới mang thẻ —
  // bản cũ nhánh này chỉ cập nhật bản đồ, vứt luôn thẻ có khung giờ, nên cửa
  // sổ mãi chỉ có map + showroom, không có giờ để đặt (Sếp 2026-08-31).
  const handlePanelLocated = useCallback(
    (result: TestDriveOptionsResponse, where: LocateWhere): void => {
      const index = state.messages.map((m) => Boolean(m.testDriveCard)).lastIndexOf(true);
      handleTestDriveFound(index, result.test_drive_card, result.quick_replies ?? [], result.navigate, where);
    },
    [handleTestDriveFound, state.messages],
  );

  const autoSubmittedRef = useRef(false);
  const threadRef = useRef<HTMLDivElement>(null);

  // Neo hội thoại đang mở vào URL ngay khi có lượt đầu tiên.
  //
  // Đây là nửa còn lại của bản vá "vào trang chat lại rơi vào hội thoại cũ"
  // (Sếp 2026-08-25): `AgentSessionProvider` nay CHỈ khôi phục `sessionStorage`
  // khi URL mang đúng `?conversation=`. Không có dòng này thì F5 giữa chừng một
  // cuộc trò chuyện sẽ mất sạch — đổi một lỗi lấy một lỗi khác.
  //
  // `replaceState` chứ không `pushState`: nút Back của trình duyệt phải đưa
  // khách về trang trước đó, không phải về chính màn chat này ở trạng thái rỗng.
  // Cũng gán luôn `loadedConversationId` để hiệu ứng tải hội thoại bên trên
  // không quay ra gọi `fetchConversation` cho phiên vừa tạo ngay tại client.
  useEffect(() => {
    if (!ready || state.messages.length === 0 || typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("conversation") === state.sessionId) return;
    params.set("conversation", state.sessionId);
    params.delete("prompt");
    loadedConversationId.current = state.sessionId;
    window.history.replaceState(null, "", `/consultation?${params.toString()}`);
  }, [ready, state.messages.length, state.sessionId]);

  // Cập nhật preview cho sidebar cuộc trò chuyện (bỏ dòng hệ thống)
  useEffect(() => {
    if (!state.sessionId || state.messages.length === 0) return;
    const lastMsg = [...state.messages].reverse().find((m) => m.role !== "system");
    if (lastMsg?.text) {
      setCachedPreview(state.sessionId, lastMsg.text, state.messages.length);
    }
  }, [state.sessionId, state.messages]);

  // Thread cuộn trong khung riêng nên tin nhắn mới nằm dưới tầm nhìn: phải tự
  // kéo xuống đáy mỗi khi có thêm lượt hoặc khi hiện chỉ báo đang gõ.
  useEffect(() => {
    const thread = threadRef.current;
    if (thread) thread.scrollTop = thread.scrollHeight;
  }, [state.messages, state.phase, sending]);

  // Panel trượt vào/ra làm cột chat co giãn từng frame → bong bóng xuống dòng
  // khác, `scrollHeight` đổi, và chỗ khách đang đọc trôi đi. Giữ bất biến
  // "khoảng cách tới đáy" trong suốt lúc chuyển cảnh: đo trước, bù lại mỗi lần
  // khung đổi cỡ, thôi sau khi transition chắc chắn đã xong.
  // Sếp CHỐT đợt 10: khi cửa sổ mở, chat ĐƯỢC PHÉP hẹp lại — panel là vai
  // chính. Bề rộng ba cột do MỘT MÌNH CSS quyết ([56px | minmax(440px, 38%) |
  // minmax(560px, 1fr)], transition trên grid) — bỏ hẳn cơ chế đo rồi ghim
  // `--chat-col` cũ: hai nguồn quyết một bề rộng là mảnh đất của lỗi lệch nhau
  // (đã từng cắt mất 20px mép phải). Chữ chat reflow là chấp nhận được; thứ
  // PHẢI giữ là neo cuộn đáy — effect ResizeObserver ngay dưới lo việc đó.
  const panelOpen = state.panel.open;
  useEffect(() => {
    const thread = threadRef.current;
    if (!thread || typeof ResizeObserver === "undefined") return;
    const bottomGap = thread.scrollHeight - thread.scrollTop - thread.clientHeight;
    const observer = new ResizeObserver(() => {
      thread.scrollTop = thread.scrollHeight - thread.clientHeight - bottomGap;
    });
    observer.observe(thread);
    // 500ms > transition dài nhất của cửa sổ (mở 400ms, đợt 11) — ngắn hơn là
    // thôi bù cuộn giữa lúc lưới còn đang trượt.
    const timer = setTimeout(() => observer.disconnect(), 500);
    return () => {
      clearTimeout(timer);
      observer.disconnect();
    };
  }, [panelOpen]);
  useEffect(() => {
    if (ready && initialPrompt && !autoSubmittedRef.current) {
      autoSubmittedRef.current = true;
      void sendMessage(initialPrompt);
      if (typeof window !== "undefined") {
        const nextUrl = fromParam ? `/consultation?from=${encodeURIComponent(fromParam)}` : "/consultation";
        window.history.replaceState(null, "", nextUrl);
      }
    }
  }, [fromParam, initialPrompt, ready, sendMessage]);

  // Lắng nghe phản hồi từ tư vấn viên (Advisor) hoặc đề xuất được duyệt (Deliveries)
  useEffect(() => {
    if (!ready || !state.sessionId) return;
    let active = true;

    async function pollAdvisorMessages(): Promise<void> {
      try {
        const [deliveriesRes, messagesRes] = await Promise.allSettled([
          fetchDeliveries(state.sessionId),
          fetchConversationMessages(state.sessionId),
        ]);

        if (!active) return;

        if (deliveriesRes.status === "fulfilled" && deliveriesRes.value?.items) {
          for (const item of deliveriesRes.value.items) {
            if (!state.deliveredReviewIds.includes(item.review_id)) {
              dispatch({ type: "delivered", text: item.content, reviewId: item.review_id });
            }
          }
        }

        if (messagesRes.status === "fulfilled" && messagesRes.value?.items) {
          const newAdvisorMessages = messagesRes.value.items.filter(
            (m: { message_id: string; role: string; content: string; created_at: string }) =>
              m.role === "ADVISOR"
          );
          for (const m of newAdvisorMessages) {
            const alreadyExists = state.messages.some(
              (msg) => msg.text === m.content || msg.text === `[Tư vấn viên]: ${m.content}`
            );
            if (!alreadyExists && m.content) {
              dispatch({ type: "agent_answered", text: `[Tư vấn viên]: ${m.content}` });
            }
          }
        }
      } catch {
        // Silent catch for background polling
      }
    }

    const interval = setInterval(() => {
      void pollAdvisorMessages();
    }, 2500);

    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [dispatch, ready, state.deliveredReviewIds, state.messages, state.sessionId]);

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void sendMessage(draft);
  }

  // Gợi ý chạy chữ trong ô gõ lấy từ `quick_replies` của LƯỢT TRỢ LÝ GẦN NHẤT.
  const showReviewStatus = state.phase === "waiting_review" || state.phase === "delivered";
  const waitingForReview = state.phase === "waiting_review";

  const backHref = fromParam || "/";
  const backLabel = fromParam
    ? fromParam.includes("vehicle") || fromParam.includes("motorbike")
      ? "Quay lại trang sản phẩm"
      : "Quay lại trang trước"
    : "Quay lại trang chủ";

  const tourPanel = state.panel;
  // Thẻ lái thử GẦN NHẤT trong chat — panel bản đồ dùng chính thẻ này để bày
  // ngày/khung giờ của showroom đang chọn (đợt 11, Sếp: "đăng ký giờ của tôi ở
  // đâu"). Duyệt ngược để lượt mới nhất thắng; thẻ trong chat GIỮ NGUYÊN.
  const latestTestDriveCard =
    [...state.messages].reverse().find((message) => message.testDriveCard)?.testDriveCard ?? null;
  const railMode = Boolean(mounted && tourPanel.navigate && tourPanel.open);
  const workspaceClass = [
    "consultation-workspace",
    tourPanel.navigate ? "has-tour-panel" : "",
    railMode ? "tour-panel-open is-rail" : "",
  ]
    .filter(Boolean)
    .join(" ");
  const railVehicle =
    tourPanel.navigate?.kind === "vehicle" ? getVehicleMenuEntry(tourPanel.navigate.slug) : undefined;

  return (
    <div className={workspaceClass}>
      <ConversationHistorySidebar
        activeConversationId={state.sessionId}
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
        onNewConversation={handleNewConversation}
        rail={
          railMode && tourPanel.navigate
            ? {
                avatar: railVehicle ? { src: railVehicle.imageUrl, alt: railVehicle.name } : null,
                label:
                  tourPanel.navigate.kind === "vehicle"
                    ? `Mở lại chi tiết ${tourPanel.navigate.name}`
                    : "Mở lại bản đồ showroom",
                // Bung danh sách = đóng cửa sổ (bố cục chỉ có hai trạng thái).
                onExpand: () => dispatch({ type: "panel_toggled", open: false }),
                onAvatarClick: () => dispatch({ type: "panel_toggled", open: true }),
              }
            : null
        }
      />
      <div className="consultation-stage">
        {/* Khách thu gọn panel thì nội dung vẫn còn — một nút nhỏ để mở lại,
            không bắt khách hỏi lại bot chỉ để thấy lại trang xe. */}
        {mounted && tourPanel.navigate && !tourPanel.open ? (
          <button
            className="tour-panel-reopen"
            onClick={() => dispatch({ type: "panel_toggled", open: true })}
            type="button"
          >
            <PanelRightOpen aria-hidden="true" size={16} />
            <span>{tourPanel.navigate.kind === "vehicle" ? tourPanel.navigate.name : "Bản đồ showroom"}</span>
          </button>
        ) : null}
        <div className="consultation-nav">
          <div className="consultation-nav-left">
            <button
              aria-label="Mở lịch sử chat"
              className="history-drawer-toggle"
              onClick={() => setHistoryOpen(true)}
              type="button"
            >
              <History aria-hidden="true" size={16} />
              <span>Lịch sử chat</span>
            </button>
            <Link className="consultation-back-link" href={backHref}>
              <ArrowLeft aria-hidden="true" size={16} />
              <span>{backLabel}</span>
            </Link>
          </div>
          <button
            aria-label="Tạo hội thoại mới"
            className="consultation-nav-new"
            onClick={handleNewConversation}
            type="button"
          >
            <Plus aria-hidden="true" size={15} />
            <span>Hội thoại mới</span>
          </button>
        </div>
        <div className="conversation-thread" ref={threadRef} suppressHydrationWarning>
          {/* Lời chào là TRẠNG THÁI RỖNG, không phải một lượt trong hội thoại.
              Bản cũ render nó vô điều kiện nên bong bóng đầu tiên khách nhìn
              thấy luôn là của bot — sai với thực tế: khách bấm vào từ trang
              chính, tức chính khách mới là người mở lời (Sếp 2026-08-25).
              Có lượt đầu tiên thì lời chào biến mất và dòng hội thoại bắt đầu
              bằng đúng câu khách nhắn. */}
          {mounted && ready && state.messages.length > 0 ? state.messages.map((message, index) => {
            // Thẻ xe đã in nguyên đoạn giới thiệu của từng mẫu, mà `answer` của
            // lượt đề xuất chính là các đoạn ấy nối lại (`nodes/synthesize`:
            // `draft_answer = "\n\n".join(pitches)`). In cả hai là khách đọc
            // đúng một nội dung hai lần (Sếp 2026-08-25).
            //
            // Biến này đã được tính từ trước nhưng KHÔNG dùng ở đâu — ý định
            // đúng, chỗ dùng bị mất. Nối lại.
            //
            // `pitchHidden` (guardrail chặn bản nháp) vẫn giữ bong bóng: lúc đó
            // `pitch` của từng thẻ rỗng, bong bóng là chỗ DUY NHẤT khách đọc được.
            //
            // 2026-09-23: giấu bong bóng CHỈ KHI nó lặp lại nội dung card. Điều
            // kiện cũ ("có card là giấu") đúng cho đường `synthesize`, nhưng sai
            // cho mọi đường khác: lượt dự phòng và lượt đi một bậc giá có
            // `answer` là LỜI DẪN ("Em đưa anh/chị lên tầm cao hơn một bậc ạ:"),
            // khác hẳn pitch trên card. Giấu nó đi thì khách nhận một rừng thẻ
            // không ai dẫn — đúng thứ Sếp bắt được trên giao diện.
            const pitchRepeatsBubble = (pitch: string | null | undefined) => {
              const body = squashSpaces(pitch ?? "");
              return body.length > 0 && squashSpaces(message.text ?? "").includes(body);
            };
            const hasVisiblePitches =
              (message.vehicles?.length ?? 0) > 0 &&
              !message.pitchHidden &&
              (message.vehicles ?? []).every((vehicle) => pitchRepeatsBubble(vehicle.pitch));
            const comparison = message.comparison ?? null;
            const hasVisibleComparison = Boolean(
              comparison && comparison.vehicles && comparison.vehicles.some((v) => v.found),
            );
            const places = message.nearbyLocations ?? null;
            const isLastMessage = index === state.messages.length - 1;
            if (message.role === "system") {
              return (
                <p className="conversation-system-note" key={`system-${index}`} role="status">
                  {message.text}
                </p>
              );
            }
            const askingForLocation = Boolean(places?.needs_location) && isLastMessage;
            return (
              <div className="conversation-turn" key={`${message.role}-${index}`}>
                {message.text && !hasVisiblePitches && !hasVisibleComparison ? (
                  <ConversationMessage role={message.role}>
                    <RichText text={message.text} />
                  </ConversationMessage>
                ) : null}
                {hasVisibleComparison && comparison ? <AgentComparison comparison={comparison} /> : null}
                {places ? <NearbyLocationCards locations={places} /> : null}
                {message.vehicleDetails ? (
                  <VehicleDetailsCard details={message.vehicleDetails} />
                ) : null}
                {message.tcoCard ? (
                  <TcoCard card={message.tcoCard} sessionId={state.sessionId} />
                ) : null}
                {message.testDriveCard ? (
                  <TestDriveCard
                    card={message.testDriveCard}
                    disabled={sending}
                    sessionId={state.sessionId}
                    onConfirm={(value) => void sendMessage(value, { silent: true })}
                    onCardReplaced={(card, quickReplies) =>
                      handleTestDriveFound(index, card, quickReplies, null, null)
                    }
                    onShowroomChange={(showroomId) => dispatch({ type: "panel_showroom_picked", showroomId })}
                    selectedShowroomId={state.panel.selectedShowroomId}
                  />
                ) : null}
                {askingForLocation ? (
                  <LocationRequest
                    disabled={sending}
                    onCoordinates={(position) =>
                      void resolveWithCoordinates(position, places?.location_types ?? [])
                    }
                    onLocationText={(text) => void sendMessage(text)}
                  />
                ) : null}
                {message.vehicles && message.vehicles.length > 0 ? (
                  <VehiclePitchList
                    disabled={sending}
                    onSelect={(vehicle) =>
                      // Gửi TÊN mẫu như một tin nhắn bình thường — cùng quy ước
                      // với gõ tay, nên backend không cần một nhánh riêng chỉ
                      // dành cho nút bấm. `silent` giấu bong bóng ở giao diện,
                      // không đổi thứ gửi lên server.
                      void sendMessage(`Tôi chọn ${vehicle.display_name}`, { silent: true })
                    }
                    pitchHidden={message.pitchHidden ?? false}
                    vehicles={message.vehicles}
                  />
                ) : null}
              </div>
            );
          }) : null}
          {sending ? <TypingIndicator /> : null}
          {showReviewStatus ? <PendingApproval /> : null}
          {state.phase === "error" ? (
            <div className="conversation-error">
              <AlertCircle size={36} />
              <h1>{state.errorMessage}</h1>
              {state.authRequired ? (
                <Link className="primary-button" href="/login">
                  <LogIn size={17} /> Đăng nhập
                </Link>
              ) : (
                <button
                  className="primary-button"
                  onClick={() => dispatch({ type: "restarted", sessionId: crypto.randomUUID() })}
                  type="button"
                >
                  <RotateCcw size={17} /> Bắt đầu lại
                </button>
              )}
            </div>
          ) : null}
        </div>
        {/* Cùng bố cục với thanh trợ lý ngoài sảnh (`components/customer/agent-dock`):
            khung viên thuốc, ô nhập chìm bên trong, nút gửi tròn, rồi các nút phụ
            dạng viên thuốc bên phải. Trước đây ô nhập trong màn chat là khung chữ
            nhật bo nhẹ với nút gửi vuông màu primary, còn nút "Làm mới" là một cục
            Tailwind rời — ba thứ nằm cạnh nhau mà không thứ nào giống thứ nào
            (Sếp 2026-08-25). */}
        <div className="conversation-composer">
          <button
            className="composer-action composer-action-advisor"
            disabled={sending}
            onClick={() => void sendMessage("Tôi muốn gặp tư vấn viên")}
            title="Kết nối trực tiếp với tư vấn viên VinFast"
            type="button"
          >
            <Headset aria-hidden="true" size={20} />
            <span>Gặp tư vấn viên</span>
          </button>
          <form onSubmit={submit}>
            <div className="composer-input-wrap">
              <input
                aria-label="Tin nhắn gửi trợ lý"
                onChange={(event) => setDraft(event.target.value)}
                placeholder={COMPOSER_PLACEHOLDER}
                value={draft}
              />
            </div>
            <button aria-label="Gửi" disabled={sending || !draft.trim()} type="submit">
              <Send size={18} />
            </button>
          </form>
          {mounted && ready && state.messages.length > 0 ? (
            <button
              className="composer-action composer-action-icon"
              onClick={handleNewConversation}
              title="Bắt đầu cuộc trò chuyện mới"
              aria-label="Làm mới cuộc trò chuyện"
              type="button"
            >
              <RotateCcw aria-hidden="true" size={17} />
            </button>
          ) : null}
        </div>
      </div>
      {mounted && ready && tourPanel.navigate ? (
        <TourPanel
          disabled={sending}
          onClose={() => dispatch({ type: "panel_toggled", open: false })}
          onLocated={handlePanelLocated}
          // Cùng đường gửi với nút "Đặt lịch" của thẻ trong chat: mã đã ký đi
          // như một tin nhắn `silent` — backend không cần nhánh riêng cho panel.
          onSendMessage={(value) => void sendMessage(value, { silent: true })}
          onShowroomPick={(showroomId) => dispatch({ type: "panel_showroom_picked", showroomId })}
          panel={tourPanel}
          sessionId={state.sessionId}
          testDriveCard={latestTestDriveCard}
        />
      ) : null}
    </div>
  );
}
