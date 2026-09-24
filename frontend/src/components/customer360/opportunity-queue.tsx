"use client";

import { ChevronRight, LoaderCircle, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { bottleneckLabel } from "@/components/advisor/offer-state-labels";
import { StatusBadge } from "@/components/shared/status-badge";
import { fetchOpportunities, type OpportunityListItem } from "@/lib/api/agent";
import type { HeatBand, ViewerRole } from "@/types/customer360";

import { HEAT_BAND_BADGES, SALES_STAGE_LABELS, needSummary } from "./customer360-labels";
import { customerProfileHref } from "./profile-links";

const BANDS: readonly (HeatBand | "ALL")[] = ["ALL", "HOT", "WARM", "COLD"];

/**
 * Cơ hội bán hàng theo đơn vị CƠ HỘI (plan §2.5), nóng nhất trước. Không mở rộng tại chỗ —
 * mỗi dòng dẫn sang hồ sơ khách, nơi có đủ nhu cầu/rào cản/việc cần làm.
 */
export function OpportunityQueue({ role = "advisor" }: Readonly<{ role?: ViewerRole }>) {
  const [items, setItems] = useState<readonly OpportunityListItem[] | null>(null);
  const [band, setBand] = useState<HeatBand | "ALL">("ALL");
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    fetchOpportunities({ band: band === "ALL" ? undefined : band, limit: 100 })
      .then((rows) => {
        if (active) {
          setItems(rows);
          setError(false);
        }
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [band]);

  return (
    <section aria-label="Cơ hội bán hàng" className="ops-panel opportunity-queue">
      <div className="opportunity-queue-filters" role="group" aria-label="Lọc độ nóng">
        {BANDS.map((value) => (
          <button aria-pressed={band === value} key={value} onClick={() => setBand(value)} type="button">
            {value === "ALL" ? "Tất cả" : HEAT_BAND_BADGES[value].label}
          </button>
        ))}
      </div>
      {error ? (
        <p className="catalog-result-note" role="alert">
          Không tải được danh sách cơ hội.
        </p>
      ) : null}
      {items === null && !error ? (
        <div aria-busy="true" className="ops-state">
          <LoaderCircle className="spin" size={22} />
        </div>
      ) : null}
      {items !== null && items.length === 0 ? (
        <div className="ops-state">
          <Sparkles size={24} />
          <h2>Chưa có cơ hội nào</h2>
          <p>Cơ hội xuất hiện khi khách được giao cho bạn trao đổi nhu cầu mua xe.</p>
        </div>
      ) : null}
      {items?.length ? (
        <ul>
          {items.map((item) => {
            const heat = HEAT_BAND_BADGES[item.heat_band];
            return (
              <li key={item.opportunity_id}>
                <Link href={customerProfileHref(item.customer_id, role)}>
                  <div>
                    <strong>{item.display_name || item.customer_id}</strong>
                    <small>{needSummary(item.slots) ?? "Chưa rõ nhu cầu"}</small>
                    <span className="chat-row-chips">
                      <StatusBadge tone={heat.tone}>{`${heat.label} · ${item.heat_score}`}</StatusBadge>
                      <StatusBadge tone="info">{SALES_STAGE_LABELS[item.stage]}</StatusBadge>
                      {item.barriers.map((code) => (
                        <StatusBadge key={code} tone="neutral">
                          {bottleneckLabel(code)}
                        </StatusBadge>
                      ))}
                      {item.needs_review ? <StatusBadge tone="warning">Cần xác nhận nhu cầu</StatusBadge> : null}
                    </span>
                  </div>
                  <ChevronRight size={16} />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
