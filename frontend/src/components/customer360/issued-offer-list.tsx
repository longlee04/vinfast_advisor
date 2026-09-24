"use client";

import { useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { fetchCustomerOffers, offerAction, type OpportunityOffer, PromotionApiError } from "@/lib/api/promotions";

type IssuedOffer = OpportunityOffer & { readonly sent_at: string | null; readonly updated_at: string };

const STATUS: Record<OpportunityOffer["status"], { tone: "success" | "warning" | "neutral" | "info"; label: string }> = {
  SUGGESTED: { tone: "warning", label: "Chờ tư vấn viên khác duyệt" },
  APPROVED: { tone: "info", label: "Đã duyệt — chưa gửi" },
  SENT: { tone: "info", label: "Đã gửi khách" },
  ENGAGED: { tone: "success", label: "Khách phản hồi" },
  CONVERTED: { tone: "success", label: "Đã chốt" },
  EXPIRED: { tone: "neutral", label: "Hết hạn" },
  DISMISSED: { tone: "neutral", label: "Đã bỏ" },
};

/** Lý do hàng rào chặn gửi → câu TVV đọc được. */
const BLOCK_REASONS: Record<string, string> = {
  NEEDS_MANAGER: "Vượt hạn mức — cần một tư vấn viên khác duyệt trước (mục Ưu đãi).",
  PROMOTION_NOT_ACTIVE: "Ưu đãi không còn áp dụng.",
  PROMOTION_EXPIRED: "Ưu đãi đã hết hạn.",
  NO_USES_LEFT: "Ưu đãi đã hết suất.",
  NO_OPEN_SESSION: "Khách không có phiên chat đang mở để gửi.",
};

/** Tab "Ưu đãi đã cấp" (plan §2.5) — vòng đời từng ưu đãi và nút gửi/chốt/bỏ. */
export function IssuedOfferList({ customerId, readOnly }: Readonly<{ customerId: string; readOnly: boolean }>) {
  const [items, setItems] = useState<readonly IssuedOffer[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchCustomerOffers(customerId)
      .then(setItems)
      .catch(() => setError("Không tải được ưu đãi đã cấp."));
  }, [customerId]);

  useEffect(() => {
    load();
  }, [load]);

  async function act(offerId: string, action: "send" | "engage" | "convert" | "dismiss") {
    try {
      await offerAction(offerId, action);
      setError(null);
      load();
    } catch (err) {
      const code = err instanceof PromotionApiError ? err.code : "";
      setError(BLOCK_REASONS[code] ?? "Không thực hiện được thao tác.");
    }
  }

  if (error && !items) return <p className="customer360-empty">{error}</p>;
  if (!items) return null;
  if (!items.length) return <p className="customer360-empty">Chưa cấp ưu đãi nào cho khách này.</p>;

  return (
    <div className="eligible-offers">
      {error ? <p role="alert">{error}</p> : null}
      <ul>
        {items.map((offer) => {
          const badge = STATUS[offer.status];
          return (
            <li key={offer.offer_id}>
              <div>
                <strong className="mono-text">{offer.promotion_code}</strong>
                <small>
                  {offer.discount_vnd ? `${offer.discount_vnd.toLocaleString("vi-VN")} đ · ` : ""}
                  {new Date(offer.updated_at).toLocaleString("vi-VN")}
                </small>
              </div>
              <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
              {!readOnly ? (
                <span className="chat-row-actions">
                  {offer.status === "APPROVED" ? (
                    <button className="secondary-button" onClick={() => void act(offer.offer_id, "send")} type="button">
                      Gửi khách
                    </button>
                  ) : null}
                  {offer.status === "SENT" ? (
                    <button className="text-button" onClick={() => void act(offer.offer_id, "engage")} type="button">
                      Khách phản hồi
                    </button>
                  ) : null}
                  {offer.status === "SENT" || offer.status === "ENGAGED" ? (
                    <button className="text-button" onClick={() => void act(offer.offer_id, "convert")} type="button">
                      Đã chốt
                    </button>
                  ) : null}
                  {offer.status === "SUGGESTED" || offer.status === "APPROVED" ? (
                    <button className="text-button" onClick={() => void act(offer.offer_id, "dismiss")} type="button">
                      Bỏ
                    </button>
                  ) : null}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
