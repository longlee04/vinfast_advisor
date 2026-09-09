import { RoleGuard } from "@/components/shared/role-guard";

export default function AdminLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <RoleGuard allow={["admin"]} loginPath="/staff-login">{children}</RoleGuard>;
}
