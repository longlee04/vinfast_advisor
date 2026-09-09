"use client";

import { AlertTriangle, LoaderCircle, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  OFFER_STATE_BADGES,
  PROMOTION_TYPE_LABELS,
  bottleneckLabel,
} from "@/components/advisor/offer-state-labels";
import { StatusBadge } from "@/components/shared/status-badge";
import { fetchSalesOpportunities } from "@/lib/api/agent";
import type { SalesOpportunity } from "@/types/agent";

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;

/**
 * "Hoạt động lần cuối" là thứ tư vấn viên dùng để chọn gọi ai TRƯỚC, nên vài
 * phút vừa qua phải đọc được ngay; xa hơn một ngày thì mốc ngày cụ thể có ích
 * hơn con số "38 giờ trước".
 */
export function formatLastActive(iso: string, now: number = Date.now()): string {
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;
  const elapsed = now - at;
  if (elapsed < MINUTE_MS) return "Vừa xong";
  if (elapsed < HOUR_MS) return `${Math.floor(elapsed / MINUTE_MS)} phút trước`;
  if (elapsed < DAY_MS) return `${Math.floor(elapsed / HOUR_MS)} giờ trước`;
  return new Date(at).toLocaleDateString("vi-VN");
}

/** Mới hoạt động xếp trước — không tin thứ tự backend gửi sang. */
function sortByLastActive(items: readonly SalesOpportunity[]): SalesOpportunity[] {
  return [...items].sort((left, right) => {
    const leftAt = Date.parse(left.last_active_at);
    const rightAt = Date.parse(right.last_active_at);
    if (Number.isNaN(leftAt) || Number.isNaN(rightAt)) return 0;
    return rightAt - leftAt;
  });
}

function SalesOpportunityCard({ item }: Readonly<{ item: SalesOpportunity }>) {
  const [expanded, setExpanded] = useState(false);
  const snapshot = item.snapshot ?? {};
  const badge = OFFER_STATE_BADGES[snapshot.offer_state ?? "NONE_BOTTLENECK"];
  const evidences = snapshot.bottlenecks ?? [];
  const needs = snapshot.needs ?? [];
  const consideredVehicles = snapshot.considered_vehicles ?? [];
  const promotions = snapshot.matched_promotions ?? [];

  return (
    <article aria-label={`Cơ hội bán hàng của khách ${item.customer_id}`}>
      <header>
        <h3>Khách {item.customer_id}</h3>
        <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
      </header>

      <dl>
        <div>
          <dt>Nút thắt</dt>
          <dd>
            {item.bottlenecks.length > 0
              ? item.bottlenecks.map(bottleneckLabel).join(", ")
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Hoạt động lần cuối</dt>
          <dd>{formatLastActive(item.last_active_at)}</dd>
        </div>
      </dl>

      {evidences.length > 0 ? (
        <ul>
          {evidences.map((evidence) => (
            <li key={`${evidence.bottleneck}-${evidence.verbatim_quote}`}>
              <strong>{bottleneckLabel(evidence.bottleneck)}</strong>
              <blockquote>{evidence.verbatim_quote}</blockquote>
            </li>
          ))}
        </ul>
      ) : (
        <p className="profile-empty">Chưa trích được nguyên văn câu khách nói.</p>
      )}

      {snapshot.unmet_demand_flag ? (
        <div className="inline-warning">
          <AlertTriangle size={16} />
          Nhu cầu chưa có chương trình đáp ứng
          {snapshot.unmet_bottleneck ? ` (${snapshot.unmet_bottleneck})` : ""}.
        </div>
      ) : null}

      <button
        aria-expanded={expanded}
        className="table-action"
        onClick={() => setExpanded((current) => !current)}
        type="button"
      >
        {expanded ? "Thu gọn" : "Xem chi tiết"}
      </button>

      {expanded ? (
        <div>
          <dl>
            <div>
              <dt>Nhu cầu</dt>
              <dd>{needs.length > 0 ? needs.join(", ") : "—"}</dd>
            </div>
            <div>
              <dt>Xe đang cân nhắc</dt>
              <dd>{consideredVehicles.length > 0 ? consideredVehicles.join(", ") : "—"}</dd>
            </div>
            <div>
              <dt>Màu ưu tiên</dt>
              <dd>{snapshot.color_preference ?? "—"}</dd>
            </div>
            <div>
              <dt>Mã phiên</dt>
              <dd>{item.session_id}</dd>
            </div>
          </dl>
          {promotions.length > 0 ? (
            <ul>
              {promotions.map((promotion) => (
                <li key={promotion.promotion_code}>
                  <strong>{promotion.promotion_code}</strong>
                  <small>{PROMOTION_TYPE_LABELS[promotion.promotion_type]}</small>
                </li>
              ))}
            </ul>
          ) : (
            <p className="profile-empty">Không có chương trình nào khớp nút thắt của khách.</p>
          )}
        </div>
      ) : null}
    </article>
  );
}

/**
 * Màn "Cơ hội bán hàng" (D9 — cách nhẹ hơn): danh sách phiên đang chạy đã bộc
 * lộ nút thắt, TÁCH HẲN khỏi hàng đợi duyệt nội dung. Không có thao tác duyệt ở
 * đây: mục đích là để tư vấn viên biết nên chủ động liên hệ ai trước.
 */
export function SalesOpportunityList() {
  const [items, setItems] = useState<readonly SalesOpportunity[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchSalesOpportunities()
      .then((loaded) => {
        if (active) setItems(loaded);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, []);

  const sorted = useMemo(() => (items === null ? [] : sortByLastActive(items)), [items]);

  if (failed) {
    return (
      <div className="ops-state">
        <AlertTriangle size={32} />
        <h2>Không tải được cơ hội bán hàng</h2>
        <p>Thử tải lại trang sau ít phút.</p>
      </div>
    );
  }

  if (items === null) {
    return (
      <div className="ops-state">
        <LoaderCircle className="spin" size={32} />
        <h2>Đang tải cơ hội bán hàng</h2>
      </div>
    );
  }

  if (sorted.length === 0) {
    return (
      <div className="ops-state">
        <Sparkles size={32} />
        <h2>Chưa có cơ hội bán hàng</h2>
        <p>Khi khách bộc lộ nút thắt trong lúc trò chuyện, phiên sẽ xuất hiện ở đây.</p>
      </div>
    );
  }

  return (
    <section className="ops-panel">
      <div className="ops-panel-heading">
        <div>
          <h2>Cơ hội bán hàng</h2>
          <p>Phiên đang trò chuyện đã bộc lộ nút thắt — mới hoạt động xếp trước</p>
        </div>
        <StatusBadge tone="info">{sorted.length} phiên</StatusBadge>
      </div>
      <div className="customer-profile sales-opportunity-list">
        {sorted.map((item) => (
          <SalesOpportunityCard item={item} key={item.session_id} />
        ))}
      </div>
    </section>
  );
}
