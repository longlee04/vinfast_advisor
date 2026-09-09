"use client";

import {
  AlertTriangle,
  BadgePercent,
  CheckCircle2,
  LoaderCircle,
  MessageSquare,
  PencilLine,
  Send,
  XCircle,
} from "lucide-react";

import { RichText } from "@/components/common/rich-text";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import {
  AgentApiError,
  approveReview,
  claimReview,
  fetchReviewDetail,
  rejectReview,
  resolveReview,
} from "@/lib/api/agent";
import type {
  MatchedPromotion,
  OfferAdjustment,
  OfferAdjustmentPolicy,
  OfferState,
  ProfileSnapshot,
  PromotionType,
  ReviewDetail,
} from "@/types/agent";
import {
  BOTTLENECK_LABELS,
  OFFER_STATE_BADGES,
  PROMOTION_TYPE_LABELS,
} from "./offer-state-labels";


type PanelMode = "view" | "edit" | "offer" | "confirmed";

/** Trường nào có nghĩa với loại ưu đãi nào — soi đúng `validate_adjustment` backend. */
const OFFER_FIELDS: Record<PromotionType, readonly OfferFieldKey[]> = {
  FIXED_DISCOUNT: ["amount_vnd"],
  PERCENT_DISCOUNT: ["percent"],
  GIFT: ["gift_code", "amount_vnd"],
  FINANCING: ["months", "amount_vnd"],
  REGISTRATION_SUPPORT: ["amount_vnd"],
  OTHER: ["amount_vnd"],
};

/** Loại điều chỉnh ghi vào nhật ký — theo trường chính của từng loại ưu đãi. */
const ADJUSTMENT_TYPES: Record<PromotionType, string> = {
  FIXED_DISCOUNT: "VND",
  PERCENT_DISCOUNT: "PERCENT",
  GIFT: "GIFT_CODE",
  FINANCING: "MONTHS",
  REGISTRATION_SUPPORT: "VND",
  OTHER: "VND",
};

type OfferFieldKey = "amount_vnd" | "percent" | "months" | "gift_code";

type Bound = { readonly min: number | null; readonly max: number | null };

function messageForError(error: unknown): string {
  if (error instanceof AgentApiError && error.code === "adjustment_out_of_bounds") {
    return "Ưu đãi vượt biên độ ADMIN cấu hình — chỉnh lại trong biên rồi gửi.";
  }
  if (error instanceof AgentApiError && error.code === "promotion_expired") {
    return "Chương trình ưu đãi đã hết hiệu lực — chọn chương trình khác.";
  }
  if (error instanceof AgentApiError && error.code === "untraced_number") {
    return "Nội dung có con số không truy vết được — sửa lại trước khi duyệt.";
  }
  if (error instanceof AgentApiError && error.status === 422) {
    return "Bản sửa làm đổi số liệu — đổi số phải qua catalog Admin.";
  }
  if (error instanceof AgentApiError && error.status === 404) return "Mục duyệt không còn tồn tại.";
  if (error instanceof AgentApiError && error.status === 403) {
    return "Tài khoản này không có quyền duyệt.";
  }
  return "Không thực hiện được thao tác duyệt.";
}

function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Biên của một trường theo đúng bảng tra trong `_validate_money`/`_validate_percent`
 * /`_validate_months` của module products: cùng một luật, chép sang UI để tư vấn
 * viên thấy trần TRƯỚC khi bấm gửi thay vì ăn 422 rồi mới biết.
 */
function boundFor(
  field: OfferFieldKey,
  policy: OfferAdjustmentPolicy | null,
  promotionType: PromotionType,
): Bound {
  if (policy === null) return { min: null, max: null };
  if (field === "percent") {
    return {
      min: toNumber(policy.adjust_min_percent),
      max: toNumber(policy.adjust_max_percent),
    };
  }
  if (field === "months") {
    return { min: toNumber(policy.financing_months_min), max: toNumber(policy.financing_months_max) };
  }
  if (field === "gift_code") return { min: null, max: null };
  switch (promotionType) {
    case "FIXED_DISCOUNT":
      return { min: toNumber(policy.adjust_min_vnd), max: toNumber(policy.adjust_max_vnd) };
    case "GIFT":
      return { min: null, max: toNumber(policy.gift_value_max_vnd) };
    case "FINANCING":
      return { min: null, max: toNumber(policy.financing_support_max_vnd) };
    case "REGISTRATION_SUPPORT":
      return { min: 0, max: toNumber(policy.registration_support_max_vnd) };
    case "OTHER":
      return { min: 0, max: toNumber(policy.other_max_vnd) };
    default:
      return { min: null, max: null };
  }
}

function formatBound(bound: Bound, unit: string): string {
  if (bound.min === null && bound.max === null) return "Không giới hạn";
  if (bound.min === null) return `Tối đa ${bound.max}${unit}`;
  if (bound.max === null) return `Tối thiểu ${bound.min}${unit}`;
  return `Trong khoảng ${bound.min}–${bound.max}${unit}`;
}

function outOfBound(raw: string, bound: Bound): boolean {
  if (raw.trim() === "") return false;
  const value = Number(raw);
  if (!Number.isFinite(value)) return true;
  if (bound.min !== null && value < bound.min) return true;
  return bound.max !== null && value > bound.max;
}

const FIELD_LABELS: Record<OfferFieldKey, string> = {
  amount_vnd: "Giá trị (VND)",
  percent: "Phần trăm (%)",
  months: "Số tháng trả góp",
  gift_code: "Mã quà tặng",
};

const FIELD_UNITS: Record<OfferFieldKey, string> = {
  amount_vnd: " VND",
  percent: "%",
  months: " tháng",
  gift_code: "",
};

/** Trường chính của một loại ưu đãi — giá trị ghi vào `new_value` của nhật ký. */
function primaryValue(
  promotionType: PromotionType,
  fields: Record<OfferFieldKey, string>,
): string {
  if (promotionType === "PERCENT_DISCOUNT") return fields.percent.trim();
  if (promotionType === "FINANCING") return fields.months.trim();
  if (promotionType === "GIFT") return fields.gift_code.trim();
  return fields.amount_vnd.trim();
}

function promotionsOf(detail: ReviewDetail, snapshot: ProfileSnapshot | null): MatchedPromotion[] {
  const fromDetail = detail.matched_promotions ?? [];
  if (fromDetail.length > 0) return [...fromDetail];
  return [...(snapshot?.matched_promotions ?? [])];
}

export function AdvisorReviewPanel({ reviewId }: Readonly<{ reviewId: string }>) {
  const [detail, setDetail] = useState<ReviewDetail | null>(null);
  const [mode, setMode] = useState<PanelMode>("view");
  const [editedText, setEditedText] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  // T19 — cờ chuyển tư vấn trực tiếp. Sống ngoài `mode` vì tư vấn viên tick nó
  // trước rồi mới bấm Từ chối, và đổi mode không được xoá lựa chọn đó.
  const [handoffRequested, setHandoffRequested] = useState(false);
  const [promotionCode, setPromotionCode] = useState("");
  const [offerFields, setOfferFields] = useState<Record<OfferFieldKey, string>>({
    amount_vnd: "",
    percent: "",
    months: "",
    gift_code: "",
  });
  const [offerReason, setOfferReason] = useState("");
  // Panel này đã giữ claim chưa — set khi backend chấp nhận claim lần đầu, để
  // các lần bấm sau (sửa số liệu bị 422, sửa lại rồi bấm tiếp...) không gọi
  // claim lần nữa và tự khoá chính mình 15 phút.
  const claimedRef = useRef(false);

  useEffect(() => {
    let active = true;
    // Đổi sang mục duyệt khác thì lease của mục cũ không còn giá trị: quên reset
    // sẽ khiến mục mới được duyệt mà chưa hề nhận, phá ràng buộc một-người-một-mục.
    claimedRef.current = false;
    fetchReviewDetail(reviewId)
      .then((loaded) => {
        if (!active) return;
        setDetail(loaded);
        setEditedText(loaded.edited_content ?? loaded.content);
      })
      .catch((error: unknown) => {
        if (active) setNotice(messageForError(error));
      });
    return () => {
      active = false;
    };
  }, [reviewId]);

  const snapshot = detail?.profile_snapshot ?? null;
  const offerState: OfferState | null =
    detail?.offer_state ?? snapshot?.offer_state ?? null;
  const badge = OFFER_STATE_BADGES[offerState ?? "NONE_BOTTLENECK"];
  const promotions = useMemo(
    () => (detail === null ? [] : promotionsOf(detail, snapshot)),
    [detail, snapshot],
  );
  const selectedPromotion = promotions.find((item) => item.promotion_code === promotionCode) ?? null;
  const policy =
    selectedPromotion === null
      ? null
      : ((detail?.adjustment_policies ?? []).find(
          (item) => item.promotion_type === selectedPromotion.promotion_type,
        ) ?? null);
  // Không có biên độ cấu hình cho loại này thì backend chắc chắn trả 422; khoá
  // hẳn field còn hơn để tư vấn viên gõ xong mới biết không gửi được.
  const policyMissing = selectedPromotion !== null && policy === null;
  const visibleFields: readonly OfferFieldKey[] =
    selectedPromotion === null ? [] : OFFER_FIELDS[selectedPromotion.promotion_type];
  const violations = visibleFields.filter((field) => {
    if (selectedPromotion === null || field === "gift_code") return false;
    return outOfBound(offerFields[field], boundFor(field, policy, selectedPromotion.promotion_type));
  });
  const allowedGiftCodes = policy?.allowed_gift_codes ?? null;
  const giftCodeViolation =
    visibleFields.includes("gift_code") &&
    allowedGiftCodes !== null &&
    offerFields.gift_code.trim() !== "" &&
    !allowedGiftCodes.includes(offerFields.gift_code);
  const offerBlocked =
    selectedPromotion === null || policyMissing || violations.length > 0 || giftCodeViolation;

  function buildAdjustment(): OfferAdjustment | null {
    if (selectedPromotion === null) return null;
    const promotionType = selectedPromotion.promotion_type;
    const amount = offerFields.amount_vnd.trim();
    const percent = offerFields.percent.trim();
    const months = offerFields.months.trim();
    const giftCode = offerFields.gift_code.trim();
    return {
      promotion_code: selectedPromotion.promotion_code,
      promotion_type: promotionType,
      adjustment_type: ADJUSTMENT_TYPES[promotionType],
      amount_vnd: amount === "" ? null : Number(amount),
      percent: percent === "" ? null : Number(percent),
      months: months === "" ? null : Number(months),
      gift_code: giftCode === "" ? null : giftCode,
      new_value: primaryValue(promotionType, offerFields),
      reason: offerReason.trim() === "" ? null : offerReason.trim(),
    };
  }

  async function resolve(
    action: "approve" | "reject",
    options: { readonly edited?: string; readonly offer?: OfferAdjustment | null } = {},
  ): Promise<void> {
    setBusy(true);
    setNotice("");
    const offer = options.offer ?? null;
    try {
      // Nhận mục trước: hai tư vấn viên mở cùng một mục là chuyện thường, và
      // backend quyết ai thắng qua lease chứ không phải UI. Nhưng chỉ nhận một
      // lần — `approveReview`/`rejectReview` không tự kiểm tra lại lease, nên
      // gọi lại claim ở lần bấm thứ hai chỉ có nguy cơ tự khoá chính mình.
      if (!claimedRef.current) {
        const outcome = await claimReview(reviewId);
        if (!outcome.granted) {
          setNotice(
            outcome.rejection === "ALREADY_CLAIMED"
              ? "Mục này đang có người khác giữ."
              : "Mục này không còn trong hàng đợi.",
          );
          return;
        }
        claimedRef.current = true;
      }
      // `/resolve` là cửa THÊM cho luồng có ưu đãi hoặc handoff; luồng duyệt trơn
      // vẫn đi `/approve` + `/reject` — hai hợp đồng đang chạy, không đụng vào.
      if (offer !== null || handoffRequested) {
        await resolveReview(reviewId, {
          status: action === "approve" ? "APPROVED" : "REJECTED",
          edited_content: options.edited ?? null,
          offer_adjustment: offer,
          handoff_requested: handoffRequested,
        });
      } else if (action === "approve") {
        await approveReview(reviewId, options.edited);
      } else {
        await rejectReview(reviewId);
      }
      const approved =
        offer !== null
          ? "Đã duyệt kèm ưu đãi. Nội dung đã gửi tới phiên của khách."
          : "Đã duyệt. Nội dung đã gửi tới phiên của khách.";
      const rejected = handoffRequested
        ? "Đã từ chối và chuyển hồ sơ để tư vấn viên liên hệ trực tiếp."
        : "Đã từ chối bản nháp này.";
      setNotice(action === "approve" ? approved : rejected);
      setMode("confirmed");
    } catch (error) {
      setNotice(messageForError(error));
    } finally {
      setBusy(false);
    }
  }

  if (!detail) {
    return (
      <div className="ops-state">
        {notice ? <AlertTriangle size={32} /> : <LoaderCircle className="spin" size={32} />}
        <h2>{notice || "Đang tải bản nháp"}</h2>
        <Link className="secondary-button" href="/advisor">
          Quay lại hàng đợi
        </Link>
      </div>
    );
  }

  if (mode === "confirmed") {
    return (
      <div className="review-confirmation">
        <CheckCircle2 size={44} />
        <h1>Đã xử lý</h1>
        <p>{notice}</p>
        <div className="flex gap-3 mt-4">
          {detail ? (
            <Link className="primary-button flex items-center gap-2" href={`/advisor/conversations/${detail.session_id}`}>
              <MessageSquare size={17} /> Bắt đầu chat với khách hàng
            </Link>
          ) : null}
          <Link className="secondary-button" href="/advisor">
            Quay lại hàng đợi
          </Link>
        </div>
      </div>
    );
  }

  const needs = snapshot?.needs ?? [];
  const consideredVehicles = snapshot?.considered_vehicles ?? [];
  const bottlenecks = snapshot?.bottlenecks ?? [];

  return (
    <div className="review-layout">
      <section className="review-content">
        <div className="review-section-heading">
          <div>
            <span className="eyebrow">Bản nháp của AI</span>
            <h2>Mục {detail.review_id.slice(0, 8)}</h2>
          </div>
          <StatusBadge tone="warning">{detail.status}</StatusBadge>
        </div>
        <div className="delivered-text"><RichText text={detail.content} /></div>
        {detail.comparison_image_base64 ? (
          // eslint-disable-next-line @next/next/no-img-element -- ảnh là base64 tại chỗ, không có URL cho next/image
          <img
            alt="Bảng so sánh các mẫu xe trong bản nháp"
            className="comparison-image"
            src={`data:image/png;base64,${detail.comparison_image_base64}`}
          />
        ) : (
          <div className="inline-warning">
            <AlertTriangle size={16} />
            Chưa dựng được ảnh so sánh cho mục này.
          </div>
        )}

        <div className="customer-profile">
          <article aria-label="Tổng hợp nhu cầu">
            <header>
              <h3>Tổng hợp nhu cầu</h3>
            </header>
            {needs.length > 0 ? (
              <ul>
                {needs.map((need) => (
                  <li key={need}>{need}</li>
                ))}
              </ul>
            ) : (
              <p className="profile-empty">Chưa ghi nhận nhu cầu cụ thể trong phiên này.</p>
            )}
            <dl>
              <div>
                <dt>Xe đang cân nhắc</dt>
                <dd>{consideredVehicles.length > 0 ? consideredVehicles.join(", ") : "—"}</dd>
              </div>
              <div>
                <dt>Màu ưu tiên</dt>
                <dd>{snapshot?.color_preference ?? "—"}</dd>
              </div>
            </dl>
          </article>

          <article aria-label="Đề xuất ưu đãi">
            <header>
              <h3>Đề xuất ưu đãi</h3>
              <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
            </header>
            {promotions.length > 0 ? (
              <ul>
                {promotions.map((promotion) => (
                  <li key={promotion.promotion_code}>
                    <strong>{promotion.promotion_code}</strong>
                    <small>{PROMOTION_TYPE_LABELS[promotion.promotion_type]}</small>
                    {promotion.gift_group_unclassified ? (
                      <small>Nhóm quà chưa phân loại — kiểm tra trước khi cấp.</small>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="profile-empty">Không có chương trình nào khớp nút thắt của khách.</p>
            )}
            {snapshot?.unmet_demand_flag ? (
              <div className="inline-warning">
                <AlertTriangle size={16} />
                Nhu cầu chưa có chương trình đáp ứng
                {snapshot.unmet_bottleneck ? ` (${snapshot.unmet_bottleneck})` : ""}.
              </div>
            ) : null}
          </article>

          <article aria-label="Hướng tiếp cận">
            <header>
              <h3>Hướng tiếp cận</h3>
            </header>
            {bottlenecks.length > 0 ? (
              <ul>
                {bottlenecks.map((evidence) => (
                  <li key={`${evidence.bottleneck}-${evidence.verbatim_quote}`}>
                    <strong>{BOTTLENECK_LABELS[evidence.bottleneck] ?? evidence.bottleneck}</strong>
                    <blockquote>{evidence.verbatim_quote}</blockquote>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="profile-empty">
                Khách chưa bộc lộ nút thắt nào — tiếp cận theo hướng giới thiệu chung.
              </p>
            )}
          </article>
        </div>
      </section>

      <aside className="review-actions-panel">
        {notice ? <div className="inline-warning">{notice}</div> : null}
        {mode === "view" ? (
          <>
            <span className="eyebrow">Hành động duyệt</span>
            <h2>Kiểm tra trước khi gửi</h2>
            <button
              className="review-action approve"
              disabled={busy}
              onClick={() => resolve("approve")}
              type="button"
            >
              <CheckCircle2 size={21} />
              <span>
                <strong>Duyệt nguyên trạng</strong>
                <small>Gửi nội dung hiện tại tới khách</small>
              </span>
            </button>
            <button className="review-action" disabled={busy} onClick={() => setMode("edit")} type="button">
              <PencilLine size={21} />
              <span>
                <strong>Chỉnh sửa nội dung</strong>
                <small>Giữ nguyên mọi số liệu</small>
              </span>
            </button>
            <Link
              className="review-action"
              href={`/advisor/conversations/${detail.session_id}`}
            >
              <MessageSquare size={21} />
              <span>
                <strong>Nhắn tin trực tiếp</strong>
                <small>Mở phòng chat với khách hàng</small>
              </span>
            </Link>
            <button
              className="review-action"
              disabled={busy || promotions.length === 0}
              onClick={() => setMode("offer")}
              title={
                promotions.length === 0
                  ? "Không có chương trình nào khớp hồ sơ này"
                  : "Cấp ưu đãi kèm khi duyệt"
              }
              type="button"
            >
              <BadgePercent size={21} />
              <span>
                <strong>Cấp ưu đãi</strong>
                <small>Tuỳ chọn — duyệt không cấp ưu đãi vẫn hợp lệ</small>
              </span>
            </button>
            <button
              className="review-action reject"
              disabled={busy}
              onClick={() => resolve("reject")}
              type="button"
            >
              <XCircle size={21} />
              <span>
                <strong>Từ chối</strong>
                <small>Không gửi gì tới khách</small>
              </span>
            </button>
            <label className="checkbox-label">
              <input
                checked={handoffRequested}
                onChange={(event) => setHandoffRequested(event.target.checked)}
                type="checkbox"
              />
              Chuyển tư vấn trực tiếp
            </label>
            <p className="source-lock-note">
              Tick trước khi từ chối để hồ sơ được chuyển cho tư vấn viên liên hệ trực tiếp.
            </p>
          </>
        ) : null}
        {mode === "edit" ? (
          <div className="review-mode">
            <span className="eyebrow">Chỉnh sửa nội dung</span>
            <textarea
              aria-label="Nội dung đã chỉnh sửa"
              onChange={(event) => setEditedText(event.target.value)}
              value={editedText}
            />
            <div>
              <button className="secondary-button" onClick={() => setMode("view")} type="button">
                Huỷ
              </button>
              <button
                className="primary-button"
                disabled={busy || !editedText.trim()}
                onClick={() => resolve("approve", { edited: editedText })}
                type="button"
              >
                <Send size={17} /> Lưu &amp; gửi
              </button>
            </div>
          </div>
        ) : null}
        {mode === "offer" ? (
          <div className="review-mode offer-mode">
            <span className="eyebrow">Cấp ưu đãi (tuỳ chọn)</span>
            <label className="offer-field">
              <span>Chương trình</span>
              <select
                aria-label="Chương trình ưu đãi"
                onChange={(event) => setPromotionCode(event.target.value)}
                value={promotionCode}
              >
                <option value="">— Chọn chương trình —</option>
                {promotions.map((promotion) => (
                  <option key={promotion.promotion_code} value={promotion.promotion_code}>
                    {promotion.promotion_code} · {PROMOTION_TYPE_LABELS[promotion.promotion_type]}
                  </option>
                ))}
              </select>
            </label>

            {policyMissing ? (
              <div className="inline-warning">
                <AlertTriangle size={16} />
                Chưa có biên độ ADMIN cấu hình cho loại ưu đãi này — không cấp được.
              </div>
            ) : null}

            {visibleFields.map((field) => {
              // `visibleFields` rỗng khi chưa chọn chương trình, nên nhánh này chỉ
              // chạy khi đã có `selectedPromotion`; "OTHER" chỉ là giá trị chết.
              const bound = boundFor(field, policy, selectedPromotion?.promotion_type ?? "OTHER");
              const hint = formatBound(bound, FIELD_UNITS[field]);
              const invalid = field === "gift_code" ? giftCodeViolation : violations.includes(field);
              return (
                <label className="offer-field" key={field}>
                  <span>{FIELD_LABELS[field]}</span>
                  {field === "gift_code" && allowedGiftCodes !== null ? (
                    <select
                      aria-label={FIELD_LABELS[field]}
                      disabled={policyMissing}
                      onChange={(event) =>
                        setOfferFields((current) => ({ ...current, gift_code: event.target.value }))
                      }
                      value={offerFields.gift_code}
                    >
                      <option value="">— Chọn mã quà —</option>
                      {allowedGiftCodes.map((code) => (
                        <option key={code} value={code}>
                          {code}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      aria-label={FIELD_LABELS[field]}
                      aria-invalid={invalid}
                      disabled={policyMissing}
                      max={bound.max ?? undefined}
                      min={bound.min ?? undefined}
                      onChange={(event) =>
                        setOfferFields((current) => ({ ...current, [field]: event.target.value }))
                      }
                      title={hint}
                      type={field === "gift_code" ? "text" : "number"}
                      value={offerFields[field]}
                    />
                  )}
                  <small>{field === "gift_code" ? "Chỉ mã trong danh sách cho phép" : hint}</small>
                  {invalid ? (
                    <span className="inline-warning">
                      <AlertTriangle size={16} />
                      Giá trị vượt biên độ cho phép ({hint}).
                    </span>
                  ) : null}
                </label>
              );
            })}

            {selectedPromotion !== null && !policyMissing ? (
              <label className="offer-field">
                <span>Lý do</span>
                <input
                  aria-label="Lý do cấp ưu đãi"
                  onChange={(event) => setOfferReason(event.target.value)}
                  type="text"
                  value={offerReason}
                />
              </label>
            ) : null}

            <div>
              <button className="secondary-button" onClick={() => setMode("view")} type="button">
                Huỷ
              </button>
              <button
                className="primary-button"
                disabled={busy || offerBlocked}
                onClick={() => resolve("approve", { offer: buildAdjustment() })}
                type="button"
              >
                <Send size={17} /> Duyệt &amp; cấp ưu đãi
              </button>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
