import { RoleGuard } from "@/components/shared/role-guard";

export default function AdvisorLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <RoleGuard allow={["advisor"]} loginPath="/staff-login">{children}</RoleGuard>;
}
