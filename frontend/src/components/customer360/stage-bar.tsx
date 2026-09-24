import type { SalesStage, StageMark } from "@/types/customer360";

import { BOOKING_NOTE_LABELS, SALES_STAGE_LABELS, SALES_STAGE_ORDER, shortDate } from "./customer360-labels";

export type StageBarProps = {
  readonly stage: SalesStage;
  /** `compact`: 5 vạch nhỏ + nhãn giai đoạn (danh sách). Mặc định: vạch rộng + mốc ngày (hồ sơ). */
  readonly variant?: "compact" | "full";
  readonly history?: readonly StageMark[];
};

/**
 * Thanh 5 giai đoạn. Vạch đã qua (kể cả giai đoạn hiện tại) màu chủ đạo, vạch chưa qua xám.
 * Bản đầy đủ chỉ hiện NGÀY khi backend chứng minh được mốc — không có mốc thì chỉ có nhãn.
 */
export function StageBar({ stage, variant = "full", history = [] }: StageBarProps) {
  const current = SALES_STAGE_ORDER.indexOf(stage);
  if (variant === "compact") {
    return (
      <div className="c360-stage-compact">
        <div aria-hidden="true" className="c360-stage-dots">
          {SALES_STAGE_ORDER.map((item, index) => (
            <span data-reached={index <= current || undefined} key={item} />
          ))}
        </div>
        <span>
          <span className="sr-only">Giai đoạn {current + 1}/5: </span>
          {SALES_STAGE_LABELS[stage]}
        </span>
      </div>
    );
  }
  const marks = new Map(history.map((mark) => [mark.stage, mark]));
  return (
    <ol aria-label="Giai đoạn mua" className="c360-stage-full">
      {SALES_STAGE_ORDER.map((item, index) => {
        const mark = marks.get(item);
        const note = mark?.note ? (BOOKING_NOTE_LABELS[mark.note] ?? mark.note) : null;
        const detail = mark ? [shortDate(mark.at), note].filter(Boolean).join(" · ") : index > current ? "—" : "";
        return (
          <li
            aria-current={index === current ? "step" : undefined}
            data-current={index === current || undefined}
            data-reached={index <= current || undefined}
            key={item}
          >
            <span aria-hidden="true" className="c360-stage-track" />
            <strong>
              {SALES_STAGE_LABELS[item]}
              {index === current ? " · hiện tại" : ""}
            </strong>
            {detail ? <small>{detail}</small> : null}
          </li>
        );
      })}
    </ol>
  );
}
