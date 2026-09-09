import type { ReactNode } from "react";

export function PageHeading({
  eyebrow,
  title,
  description,
  actions,
}: Readonly<{ eyebrow: string; title: string; description: string; actions?: ReactNode }>) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions ? <div className="page-heading-actions">{actions}</div> : null}
    </div>
  );
}
