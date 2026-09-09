import type { ReactNode } from "react";

type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export function StatusBadge({ children, tone = "neutral" }: Readonly<{ children: ReactNode; tone?: Tone }>) {
  return <span className={`status-badge status-${tone}`}>{children}</span>;
}
