"use client";

import { Gift, HelpCircle } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { PROMOTION_TYPE_LABELS } from "@/components/advisor/offer-state-labels";
import { StatusBadge } from "@/components/shared/status-badge";
import { type EligibleOffer, fetchEligibleOffers, PromotionApiError, proposeOffer } from "@/lib/api/promotions";

function formatDiscount(offer: EligibleOffer): string | null {
  if (offer.discount_amount_vnd) return `${offer.discount_amount_vnd.toLocaleString("vi-VN")} đ`;
  if (offer.discount_percent) return `${offer.discount_percent}%`;
  return null;
}

/**
 * "Ưu đãi phù hợp" của MỘT cơ hội (plan Customer 360 §2.5): luật đánh giá tất định ở backend.
 * ELIGIBLE kèm lý do + nút Đề xuất (TVV); NEED_INFO kèm câu hỏi gợi ý — TVV hỏi khách rồi mới đề xuất.
 */
export function EligibleOfferList({
  opportunityId,
  readOnly,
  onProposed,
}: Readonly<{ opportunityId: string; readOnly: boolean; onProposed?: () => void }>) {
  const [data, setData] = useState<{ eligible: readonly EligibleOffer[]; need_info: readonly EligibleOffer[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchEligibleOffers(opportunityId)
      .then((result) => {
        setData(result);
        setError(null);
      })
      .catch(() => setError("Không tải được ưu đãi phù hợp."));
  }, [opportunityId]);

  useEffect(() => {
    load();
  }, [load]);

  async function propose(offer: EligibleOffer) {
    try {
      const created = await proposeOffer(opportunityId, offer.promotion_code);
      setMessage(
        created.status === "SUGGESTED"
          ? `Đã đề xuất ${offer.promotion_code} — vượt hạn mức, chờ một tư vấn viên khác duyệt ở mục Ưu đãi.`
          : `Đã duyệt ${offer.promotion_code} — gửi cho khách ở tab "Ưu đãi đã cấp".`,
      );
      onProposed?.();
    } catch (err) {
      setMessage(null);
      setError(err instanceof PromotionApiError ? `Không đề xuất được: ${err.code}` : "Không đề xuất được.");
    }
  }

  if (error && !data) return <p className="customer360-empty">{error}</p>;
  if (!data) return null;
  if (!data.eligible.length && !data.need_info.length) return <p className="customer360-empty">Chưa có ưu đãi phù hợp.</p>;

  return (
    <div className="eligible-offers">
      {message ? <p role="status">{message}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <ul>
        {data.eligible.map((offer) => (
          <li key={offer.promotion_code}>
            <div>
              <strong>
                <Gift size={14} /> {offer.title}
              </strong>
              <small>
                {PROMOTION_TYPE_LABELS[offer.promotion_type] ?? offer.promotion_type}
                {formatDiscount(offer) ? ` · ${formatDiscount(offer)}` : ""}
                {offer.reasons?.length ? ` · ${offer.reasons.join("; ")}` : ""}
              </small>
            </div>
            <StatusBadge tone="success">Phù hợp</StatusBadge>
            {!readOnly ? (
              <button className="secondary-button" onClick={() => void propose(offer)} type="button">
                Đề xuất
              </button>
            ) : null}
          </li>
        ))}
        {data.need_info.map((offer) => (
          <li key={offer.promotion_code}>
            <div>
              <strong>
                <HelpCircle size={14} /> {offer.title}
              </strong>
              <small>Cần hỏi: {offer.question_hints?.join(" ") || offer.missing_fields?.join(", ")}</small>
            </div>
            <StatusBadge tone="warning">Cần thêm thông tin</StatusBadge>
          </li>
        ))}
      </ul>
    </div>
  );
}
