import { AppHeader } from "@/components/shared/app-header";
import { AgentDock } from "@/components/customer/agent-dock";
import { SiteFooter } from "@/components/layout/site-footer";

export function CustomerShell({
  children,
  headerVariant = "default",
}: Readonly<{ children: React.ReactNode; headerVariant?: "default" | "overlay" }>) {
  return (
    <div className="customer-shell">
      <AppHeader variant={headerVariant} />
      <main>{children}</main>
      <AgentDock />
      <SiteFooter />
    </div>
  );
}
