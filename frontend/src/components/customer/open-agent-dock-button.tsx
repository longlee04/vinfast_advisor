"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

export const OPEN_AGENT_DOCK_EVENT = "vinfast:open-agent-dock";

type OpenAgentDockButtonProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick" | "type"> & {
  children: ReactNode;
  prompt?: string;
};

/** Opens and focuses the existing customer chat dock without navigating away. */
export function OpenAgentDockButton({ children, prompt, ...props }: Readonly<OpenAgentDockButtonProps>) {
  function openDock(): void {
    window.dispatchEvent(new CustomEvent(OPEN_AGENT_DOCK_EVENT, { detail: { prompt } }));
  }

  return <button {...props} onClick={openDock} type="button">{children}</button>;
}
