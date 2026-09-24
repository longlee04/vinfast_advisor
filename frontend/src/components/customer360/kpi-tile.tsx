export type KpiTileProps = {
  readonly title: string;
  readonly value: number | null;
  readonly hint: string;
  /** Tô số màu cảnh báo (thẻ "Khách nóng"). */
  readonly emphasis?: boolean;
  /** Có thì cả thẻ là nút áp bộ lọc tương ứng. */
  readonly onSelect?: () => void;
  readonly selected?: boolean;
};

/** Thẻ số đầu màn "Khách cần xử lý". `value = null` = đang tải/không lấy được. */
export function KpiTile({ title, value, hint, emphasis, onSelect, selected }: KpiTileProps) {
  const body = (
    <>
      <span className="c360-kpi-title">{title}</span>
      <strong className="c360-kpi-value" data-emphasis={emphasis || undefined}>
        {value === null ? "—" : value}
      </strong>
      <span className="c360-kpi-hint">{hint}</span>
    </>
  );
  if (!onSelect) return <div className="c360-kpi">{body}</div>;
  return (
    <button aria-pressed={selected ?? false} className="c360-kpi" onClick={onSelect} type="button">
      {body}
    </button>
  );
}
