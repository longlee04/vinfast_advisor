import { SLOT_LABELS } from "./customer360-labels";

export type NeedCell = {
  readonly key: string;
  readonly label: string;
  /** Giá trị đã có (đã định dạng), hoặc `null` khi còn thiếu. */
  readonly value: string | null;
  readonly previous?: string | null;
  /** Khách né câu hỏi (bot hỏi ≥ 2 lần mà chưa có). */
  readonly evaded?: boolean;
  /** Số lần bot đã hỏi — backend cũ không trả thì chỉ ghi "Khách né". */
  readonly evadedAskCount?: number;
};

/** Lưới nhu cầu 3 cột: ô đã có viền liền; ô còn thiếu viền đứt "Chưa có"; ô khách né chữ cam. */
export function NeedGrid({ cells, tags = [] }: Readonly<{ cells: readonly NeedCell[]; tags?: readonly string[] }>) {
  return (
    <>
      <ul className="c360-need-grid">
        {cells.map((cell) => (
          <li data-missing={cell.value === null || undefined} key={cell.key}>
            <span>{cell.label}</span>
            {cell.value !== null ? (
              <strong>
                {cell.value}
                {cell.previous ? <small> (trước: {cell.previous})</small> : null}
              </strong>
            ) : cell.evaded ? (
              <strong data-evaded="true">{cell.evadedAskCount ? `Khách né · hỏi ${cell.evadedAskCount} lần` : "Khách né"}</strong>
            ) : (
              <strong data-empty="true">Chưa có</strong>
            )}
          </li>
        ))}
      </ul>
      {tags.length ? (
        <ul aria-label={SLOT_LABELS.habit_need_tags} className="c360-tag-list">
          {tags.map((tag) => (
            <li key={tag}>{tag}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
