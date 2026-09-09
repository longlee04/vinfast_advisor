"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useDemoStore } from "@/store/demo-store";
import type { DemoRole } from "@/types/demo";

const roleRoutes: Record<DemoRole, string> = {
  customer: "/",
  advisor: "/advisor",
  admin: "/admin",
};

const labels: Record<DemoRole, string> = {
  customer: "Khách hàng",
  advisor: "Tư vấn viên",
  admin: "Admin",
};

export function RoleDemoSwitcher({ compact = false }: Readonly<{ compact?: boolean }>) {
  const pathname = usePathname();
  const { setActiveRole } = useDemoStore();
  const activeRole: DemoRole = pathname.startsWith("/advisor")
    ? "advisor"
    : pathname.startsWith("/admin")
      ? "admin"
      : "customer";

  return (
    <div className={compact ? "role-switcher role-switcher-compact" : "role-switcher"} aria-label="Chuyển khu vực làm việc">
      {(["customer", "advisor", "admin"] as const).map((role) => (
        <Link
          aria-current={activeRole === role ? "page" : undefined}
          className={activeRole === role ? "role-option is-active" : "role-option"}
          href={roleRoutes[role]}
          key={role}
          onClick={() => setActiveRole(role)}
        >
          {labels[role]}
        </Link>
      ))}
    </div>
  );
}
