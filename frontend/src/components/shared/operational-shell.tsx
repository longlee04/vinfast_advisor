"use client";

import {
  Bell,
  CarFront,
  ChartNoAxesCombined,
  Edit3,
  FileText,
  Loader2,
  Megaphone,
  Menu,
  MessageSquareText,
  UserCog,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FormEvent, useState } from "react";

import { ADVISOR_FEATURES, ADVISOR_MENU } from "@/components/advisor/advisor-features";
import { useWaitingConversations } from "@/components/advisor/waiting-customers";
import { DemoResetButton } from "@/components/shared/demo-reset-button";
import { RoleDemoSwitcher } from "@/components/shared/role-demo-switcher";
import { useAuth } from "@/store/auth-store";
import type { DemoRole } from "@/types/demo";

/** Menu tư vấn viên = 6 tính năng (plan §17), cùng nguồn với tiêu đề trang. */
const advisorNavigation: readonly NavItem[] = ADVISOR_MENU.map((key) => {
  const feature = ADVISOR_FEATURES[key];
  return {
    href: feature.href,
    label: feature.label,
    icon: feature.icon,
    match: "match" in feature ? feature.match : undefined,
    badge: key === "customers" ? "waiting" : undefined,
  };
});

type NavItem = {
  readonly href: string;
  readonly label: string;
  readonly icon: typeof Bell;
  /** Các đường dẫn khiến mục này sáng (mặc định: chính `href`). */
  readonly match?: readonly string[];
  /** Mục có badge đếm việc cần xử lý ngay. */
  readonly badge?: "waiting";
};

const adminNavigation: readonly NavItem[] = [
  { href: "/admin", label: "Dashboard", icon: ChartNoAxesCombined },
  { href: "/admin/vehicles", label: "Catalog xe", icon: CarFront },
  { href: "/admin/documents", label: "Chính sách AI", icon: FileText },
  { href: "/admin/chat-sessions", label: "Phiên chat", icon: MessageSquareText },
  { href: "/admin/notices", label: "Thông báo", icon: Megaphone },
  { href: "/admin/turn-traces", label: "Vì sao agent đáp", icon: ChartNoAxesCombined },
  { href: "/admin/users", label: "Người dùng", icon: UserCog },
];

function getInitials(name?: string | null, email?: string | null): string {
  if (name?.trim()) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
  }
  if (email?.trim()) {
    return email.slice(0, 2).toUpperCase();
  }
  return "AD";
}

export function OperationalShell({ children, role }: Readonly<{ children: React.ReactNode; role: Exclude<DemoRole, "customer"> }>) {
  const pathname = usePathname();
  const { user, profile, saveProfile } = useAuth();
  const [open, setOpen] = useState(false);
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [fullName, setFullName] = useState(profile?.full_name || "");
  const [phoneNumber, setPhoneNumber] = useState(profile?.phone_number || "");
  const [showroomName, setShowroomName] = useState(profile?.showroom_name || "");
  const [title, setTitle] = useState(profile?.title || "");
  const [bio, setBio] = useState(profile?.bio || "");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const navigation = role === "advisor" ? advisorNavigation : adminNavigation;
  // Khách xin gặp tư vấn viên: đếm để hiện badge đỏ trên menu — không phải tự vào mò.
  const waitingCount = useWaitingConversations(role === "advisor").length;
  const label = role === "advisor" ? "Advisor Workspace" : "Admin Preview";

  const initials = role === "advisor" ? getInitials(profile?.full_name, user?.email) : "AD";

  function openProfileModal(): void {
    if (role !== "advisor") return;
    setFullName(profile?.full_name || "");
    setPhoneNumber(profile?.phone_number || "");
    setShowroomName(profile?.showroom_name || "");
    setTitle(profile?.title || "");
    setBio(profile?.bio || "");
    setSaveSuccess(false);
    setProfileModalOpen(true);
  }

  async function handleSaveAdvisorProfile(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    try {
      setSaving(true);
      await saveProfile({
        full_name: fullName,
        phone_number: phoneNumber,
        showroom_name: showroomName,
        title: title,
        bio: bio,
      });
      setSaveSuccess(true);
      setTimeout(() => {
        setProfileModalOpen(false);
        setSaveSuccess(false);
      }, 600);
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="ops-shell">
      <aside className={open ? "ops-sidebar is-open" : "ops-sidebar"}>
        <div className="ops-brand-row">
          <Link className="ops-wordmark" href={role === "advisor" ? "/advisor" : "/admin"}>
            <strong>VINFAST AI</strong><span>{label}</span>
          </Link>
          <button className="ops-close" aria-label="Đóng điều hướng" onClick={() => setOpen(false)} type="button"><X size={20} /></button>
        </div>
        <nav className="ops-nav" aria-label={`Điều hướng ${label}`}>
          {navigation.map((item) => {
            const active =
              item.href === pathname ||
              (item.href !== `/${role}` && (item.match ?? [item.href]).some((prefix) => pathname.startsWith(prefix)));
            const Icon = item.icon;
            const badge = item.badge === "waiting" && waitingCount > 0 ? waitingCount : null;
            return (
              <Link className={active ? "ops-nav-item is-active" : "ops-nav-item"} href={item.href} key={item.href} onClick={() => setOpen(false)}>
                <Icon size={18} />
                <span>{item.label}</span>
                {badge !== null ? (
                  <span aria-label={`${badge} khách đang chờ gặp tư vấn viên`} className="ops-nav-badge" role="status">
                    {badge > 99 ? "99+" : badge}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>
        <div className="ops-sidebar-footer"><RoleDemoSwitcher /><DemoResetButton /></div>
      </aside>
      {open ? <button className="ops-scrim" aria-label="Đóng điều hướng" onClick={() => setOpen(false)} type="button" /> : null}
      <div className="ops-main">
        <header className="ops-topbar">
          <button className="ops-menu" aria-label="Mở điều hướng" onClick={() => setOpen(true)} type="button"><Menu size={21} /></button>
          <div><span className="ops-kicker">Trung tâm vận hành</span><strong>{label}</strong></div>
          <div className="ops-topbar-actions">
            {role === "advisor" ? (
              <button
                className="px-2.5 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer mr-1"
                onClick={openProfileModal}
                type="button"
                title="Hồ sơ tư vấn viên"
              >
                <Edit3 size={13} />
                <span>{profile?.full_name?.trim() || "Cập nhật hồ sơ"}</span>
              </button>
            ) : null}
            <button className="icon-button" aria-label="Thông báo" type="button"><Bell size={18} /></button>
            <span
              className="ops-avatar cursor-pointer"
              onClick={openProfileModal}
              title={role === "advisor" ? (profile?.full_name || user?.email || "Advisor") : "Admin"}
            >
              {initials}
            </span>
          </div>
        </header>
        <main className="ops-content">{children}</main>
      </div>

      {profileModalOpen ? (
        <div className="chat-confirm-backdrop" role="presentation">
          <section className="chat-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="advisor-profile-title" style={{ maxWidth: "500px" }}>
            <button className="chat-confirm-close" onClick={() => setProfileModalOpen(false)} type="button" aria-label="Đóng">
              <X size={18} />
            </button>
            <span className="eyebrow text-indigo-600">Hồ sơ tư vấn viên</span>
            <h2 id="advisor-profile-title">Thông tin cá nhân Advisor</h2>
            <p>Họ tên và thông tin sẽ hiển thị trực tiếp với khách hàng khi nhận tư vấn.</p>

            <form onSubmit={handleSaveAdvisorProfile} className="flex flex-col gap-3 mt-4 text-left">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Email đăng nhập</label>
                <input
                  type="text"
                  disabled
                  className="w-full px-3 py-2 bg-slate-100 border border-slate-200 rounded-lg text-sm text-slate-500"
                  value={user?.email || ""}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Họ và tên tư vấn viên</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                  placeholder="Ví dụ: Nguyễn Hoàng Nam"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Số điện thoại liên hệ</label>
                  <input
                    type="tel"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                    placeholder="Ví dụ: 0988776655"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Chức danh / Vị trí</label>
                  <input
                    type="text"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                    placeholder="Ví dụ: Chuyên viên tư vấn xe điện"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Showroom / Chi nhánh trực thuộc</label>
                <input
                  type="text"
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                  placeholder="Ví dụ: VinFast Times City Hà Nội"
                  value={showroomName}
                  onChange={(e) => setShowroomName(e.target.value)}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Giới thiệu ngắn (Bio)</label>
                <textarea
                  rows={2}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:border-indigo-500"
                  placeholder="Kinh nghiệm tư vấn và hỗ trợ khách hàng..."
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                />
              </div>

              <div className="flex justify-end gap-2 mt-4">
                <button className="secondary-button" onClick={() => setProfileModalOpen(false)} type="button">
                  Huỷ
                </button>
                <button
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-sm font-semibold transition-all shadow-sm flex items-center gap-1.5 cursor-pointer"
                  disabled={saving}
                  type="submit"
                >
                  {saving ? <Loader2 className="spin" size={16} /> : null}
                  {saveSuccess ? "Đã lưu thành công!" : "Lưu thay đổi"}
                </button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}
