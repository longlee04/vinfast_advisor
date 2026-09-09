"use client";

import { AlertTriangle, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { DeliveredAnswer } from "@/components/consultation/delivered-answer";
import { fetchDeliveries, turnEventsUrl } from "@/lib/api/agent";
import { useAgentSession } from "@/store/agent-session";
import type { CustomerDelivery } from "@/types/agent";

// Sau bao nhiêu lỗi liên tiếp thì ngừng để EventSource tự reconnect vô hạn.
const MAX_CONSECUTIVE_ERRORS = 3;

export function PendingApproval() {
  const { state, dispatch, ready } = useAgentSession();
  const [delivery, setDelivery] = useState<CustomerDelivery | null>(null);
  const [connectionLost, setConnectionLost] = useState(false);
  const deliveredReviewIds = useRef(state.deliveredReviewIds);
  const phase = useRef(state.phase);

  useEffect(() => {
    deliveredReviewIds.current = state.deliveredReviewIds;
    phase.current = state.phase;
  }, [state.deliveredReviewIds, state.phase]);

  useEffect(() => {
    if (!ready) return;
    // `withCredentials` là bắt buộc: kênh sự kiện đi qua cùng cookie phiên với
    // REST, và backend chặn phiên không phải chủ sở hữu bằng 403.
    const source = new EventSource(turnEventsUrl(state.sessionId), { withCredentials: true });
    let active = true;
    let consecutiveErrors = 0;

    function load(): void {
      const rehydrateDelivered = phase.current === "delivered";
      fetchDeliveries(state.sessionId)
        .then((deliveries) => {
          const latest =
            rehydrateDelivered
              ? deliveries.items.at(-1)
              : [...deliveries.items]
                  .reverse()
                  .find((item) => !deliveredReviewIds.current.includes(item.review_id));
          if (!active || !latest) return;
          setDelivery(latest);
          // Store tự bỏ qua `review_id` đã đưa vào hội thoại, nên gọi lại nhiều
          // lần (mount, reconnect, nhiều event) không sinh nội dung trùng.
          dispatch({ type: "delivered", text: latest.content, reviewId: latest.review_id });
        })
        .catch(() => undefined);
    }

    source.onmessage = () => {
      consecutiveErrors = 0;
      load();
    };

    // Broker không replay: một lượt duyệt xảy ra đúng lúc kết nối đang rớt (mất
    // mạng, tab bị trình duyệt tạm dừng, backend restart) là mất vĩnh viễn, và
    // trước đây trang chỉ gọi lại `load()` khi có message mới — không có message
    // nào nữa thì khách kẹt màn hình chờ dù đề xuất đã duyệt xong từ lâu. Gọi lại
    // ở mỗi lần kết nối lại thành công để tự bắt kịp phần đã lỡ.
    source.onopen = () => {
      consecutiveErrors = 0;
      load();
    };

    source.onerror = () => {
      consecutiveErrors += 1;
      // Broker chỉ fan-out cho queue đã subscribe, không replay — nếu backend
      // 401/403 hoặc restart, EventSource tự reconnect mỗi ~3s vô thời hạn còn
      // khách vẫn thấy spinner. Đóng hẳn sau vài lần lỗi và báo khách tải lại.
      if (consecutiveErrors >= MAX_CONSECUTIVE_ERRORS) {
        source.close();
        if (active) setConnectionLost(true);
      }
    };

    // Gọi ngay khi mount, không chỉ chờ `onmessage`: nếu tư vấn viên duyệt đúng
    // vào khoảng giữa lúc turn trả lời và EventSource bắt tay xong (hoặc trong
    // lúc reconnect), sự kiện phát ra sẽ bị bỏ lỡ vĩnh viễn vì broker không
    // replay, và khách sẽ chờ vô thời hạn nội dung thực ra đã có sẵn.
    load();

    return () => {
      active = false;
      source.close();
    };
  }, [dispatch, ready, state.sessionId]);

  if (delivery) return <DeliveredAnswer imageBase64={delivery.comparison_image_base64} />;

  return (
    <div className="pending-page">
      <div aria-hidden="true" className="pending-animation">
        <span />
        <span />
        <span />
        <ShieldCheck size={36} />
      </div>
      <span className="eyebrow">Human-in-the-loop</span>
      <h1>Đề xuất đang được tư vấn viên kiểm tra</h1>
      <p>
        Bản nháp đã vào hàng đợi duyệt. Nội dung chỉ hiện ra sau khi một tư vấn viên duyệt hoặc
        chỉnh sửa — trang này tự cập nhật, không cần tải lại.
      </p>
      {connectionLost ? (
        <div className="inline-warning">
          <AlertTriangle size={16} />
          Mất kết nối theo dõi trạng thái duyệt. Vui lòng tải lại trang để tiếp tục chờ.
        </div>
      ) : null}
      <div className="pending-steps">
        <div className="is-done">
          <span>✓</span>
          <strong>Hồ sơ hoàn tất</strong>
        </div>
        <i />
        <div className="is-active">
          <span>2</span>
          <strong>Đang kiểm tra</strong>
        </div>
        <i />
        <div>
          <span>3</span>
          <strong>Nhận đề xuất</strong>
        </div>
      </div>
    </div>
  );
}
