export function MetricCard({ label, value, note }: Readonly<{ label: string; value: string; note: string }>) {
  return <article className="metric-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></article>;
}
