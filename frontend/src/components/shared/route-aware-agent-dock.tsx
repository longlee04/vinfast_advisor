"use client";

import { usePathname } from "next/navigation";

import { AgentDock } from "@/components/customer/agent-dock";

function isOperationsRoute(pathname: string): boolean {
  return pathname === "/advisor" || pathname.startsWith("/advisor/") || pathname === "/admin" || pathname.startsWith("/admin/");
}

export function RouteAwareAgentDock(): React.JSX.Element | null {
  const pathname = usePathname();
  return isOperationsRoute(pathname) ? null : <AgentDock />;
}
