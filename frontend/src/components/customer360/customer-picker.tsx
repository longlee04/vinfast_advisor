"use client";

import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import { type CustomerPickerItem, fetchCustomerPicker } from "@/lib/api/agent";

import { HEAT_BAND_BADGES } from "./customer360-labels";

/**
 * Chọn khách để phân công (plan §2.6) — thay ô gõ tay Customer ID. Tìm theo tên hoặc mã,
 * mỗi dòng kèm độ nóng và TVV hiện tại; SĐT đã che ở backend.
 */
export function CustomerPicker({
  value,
  onChange,
}: Readonly<{ value: string; onChange: (customerId: string, item: CustomerPickerItem | null) => void }>) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<readonly CustomerPickerItem[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      fetchCustomerPicker(query, 20)
        .then((rows) => {
          if (active) {
            setItems(rows);
            setError(false);
          }
        })
        .catch(() => {
          if (active) setError(true);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [query]);

  return (
    <div className="customer-picker">
      <label className="ops-search">
        <Search size={15} />
        <span className="sr-only">Tìm khách hàng</span>
        <input onChange={(event) => setQuery(event.target.value)} placeholder="Tìm theo tên hoặc mã khách..." value={query} />
      </label>
      {error ? (
        <p className="catalog-result-note" role="alert">
          Không tải được danh sách khách.
        </p>
      ) : null}
      <ul aria-label="Khách hàng" role="listbox">
        {items.map((item) => {
          const heat = item.heat_band ? HEAT_BAND_BADGES[item.heat_band] : null;
          return (
            <li
              aria-selected={item.customer_id === value}
              key={item.customer_id}
              onClick={() => onChange(item.customer_id, item)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") onChange(item.customer_id, item);
              }}
              role="option"
              tabIndex={0}
            >
              <div>
                <strong>{item.display_name || item.customer_id}</strong>
                <small>
                  {item.phone ?? "Chưa có SĐT"} · {item.advisor_id ? `Đang giao: ${item.advisor_id}` : "Chưa phân công"}
                </small>
              </div>
              {heat ? <StatusBadge tone={heat.tone}>{`${heat.label} · ${item.heat_score ?? 0}`}</StatusBadge> : null}
            </li>
          );
        })}
        {!error && items.length === 0 ? <li className="customer360-empty">Không tìm thấy khách phù hợp.</li> : null}
      </ul>
    </div>
  );
}
