"use client";

import { useId, useState } from "react";

/**
 * Biểu đồ thanh ngang MỘT chuỗi cho Admin Dashboard (plan §2.7: biểu đồ CHỈ ở đây).
 *
 * Theo skill dataviz: một hue tuần tự (step 400 `#3987e5`, đã chạy validator — PASS trên
 * nền sáng), thanh ≤ 24px, đầu bo 4px vuông ở gốc, khe 2px giữa các thanh, giá trị ở đầu
 * thanh bằng mực chữ (không mặc màu dữ liệu), hover từng thanh có tooltip, và luôn có bảng
 * dữ liệu cho trình đọc màn hình/bản in. Một chuỗi → tiêu đề gọi tên, không cần chú giải.
 */
export type BarDatum = { readonly label: string; readonly value: number };

export function HorizontalBarChart({
  title,
  data,
  unit = "",
  emptyText = "Chưa có dữ liệu",
}: Readonly<{ title: string; data: readonly BarDatum[]; unit?: string; emptyText?: string }>) {
  const tableId = useId();
  const [active, setActive] = useState<string | null>(null);
  const max = Math.max(0, ...data.map((item) => item.value));
  const total = data.reduce((sum, item) => sum + item.value, 0);

  return (
    <figure className="c360-chart">
      <figcaption>{title}</figcaption>
      {total === 0 ? (
        <p className="customer360-empty">{emptyText}</p>
      ) : (
        <div aria-describedby={tableId} className="c360-bars" role="img" aria-label={title}>
          {data.map((item) => {
            const width = max ? Math.max((item.value / max) * 100, item.value > 0 ? 2 : 0) : 0;
            const share = total ? Math.round((item.value / total) * 100) : 0;
            return (
              <div
                className={active === item.label ? "c360-bar-row is-active" : "c360-bar-row"}
                key={item.label}
                onBlur={() => setActive(null)}
                onFocus={() => setActive(item.label)}
                onMouseEnter={() => setActive(item.label)}
                onMouseLeave={() => setActive(null)}
                tabIndex={0}
              >
                <span className="c360-bar-label">{item.label}</span>
                <span className="c360-bar-track">
                  <span className="c360-bar" style={{ width: `${width}%` }} />
                  <span className="c360-bar-value">{item.value.toLocaleString("vi-VN")}</span>
                </span>
                {active === item.label ? (
                  <span className="c360-tooltip" role="tooltip">
                    <strong>{item.label}</strong> {item.value.toLocaleString("vi-VN")}
                    {unit} · {share}%
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      )}
      <table className="sr-only" id={tableId}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Nhóm</th>
            <th scope="col">Số lượng</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.label}>
              <th scope="row">{item.label}</th>
              <td>{item.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
