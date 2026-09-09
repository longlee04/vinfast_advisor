"use client";

import { BellRing, CalendarDays, ChevronDown, CircleUserRound, LogIn, Menu, UserPlus, X } from "lucide-react";
import { useEmbedMode } from "@/lib/use-embed-mode";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { DemoResetButton } from "@/components/shared/demo-reset-button";
import { MobileMotorbikeMenu, MotorbikeMegaMenu } from "@/components/shared/motorbike-mega-menu";
import { RoleDemoSwitcher } from "@/components/shared/role-demo-switcher";
import { MobileVehicleMenu, VehicleMegaMenu } from "@/components/shared/vehicle-mega-menu";
import { useAuth } from "@/store/auth-store";

/**
 * Header chung cho MỌI trang khách — kể cả trang chủ (Sếp: hai thanh điều hướng
 * khác nhau là lỗi nặng).
 *
 * `variant="overlay"` dành cho trang có hero tràn lên đầu trang: khi chưa cuộn
 * quá 40px, header trong suốt chữ sáng nằm đè lên hero; cuộn quá thì trở về nền
 * đặc như mọi trang. Mở menu/tài khoản cũng ép nền đặc — popover trắng trên nền
 * trong suốt sẽ không đọc được.
 */
export function AppHeader({ variant = "default" }: Readonly<{ variant?: "default" | "overlay" }> = {}) {
  const embedded = useEmbedMode();
  const [accountOpen, setAccountOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const overlay = variant === "overlay";
  // Bắt đầu "đã cuộn" = false: SSR không có scrollY, và đầu trang là trạng thái
  // phổ biến khi vừa vào.
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    if (!overlay) return;
    // Nghe scroll thường (passive) thay vì IntersectionObserver: chỉ cần một
    // ngưỡng 40px, không cần sentinel trong DOM.
    const onScroll = (): void => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [overlay]);
  const accountMenuRef = useRef<HTMLDivElement>(null);
  const { status, user, profile, logout } = useAuth();
  const router = useRouter();
  const isAuthenticated = status === "authenticated" && user !== null;

  useEffect(() => {
    function closeAccountMenu(event: MouseEvent) {
      if (!accountMenuRef.current?.contains(event.target as Node)) {
        setAccountOpen(false);
      }
    }

    function closeMenusOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAccountOpen(false);
        setMenuOpen(false);
      }
    }

    document.addEventListener("mousedown", closeAccountMenu);
    document.addEventListener("keydown", closeMenusOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeAccountMenu);
      document.removeEventListener("keydown", closeMenusOnEscape);
    };
  }, []);

  function closeMobileMenu() {
    setMenuOpen(false);
  }

  async function handleLogout(): Promise<void> {
    await logout();
    setAccountOpen(false);
    setMenuOpen(false);
    router.push("/");
  }

  const transparent = overlay && !scrolled && !menuOpen && !accountOpen;

  if (embedded) return null; // trang đang nằm trong cửa sổ hội thoại

  return (
    <header className={transparent ? "customer-header is-overlay" : "customer-header"} data-variant={variant}>
      <Link className="wordmark" href="/" aria-label="VinFast AI Sales Advisor — Trang chủ">
        <Image
          alt="VinFast"
          height={29}
          priority
          src="/media/vinfast/vf2-page/vinfast-logo.webp"
          style={{ width: "auto", height: "auto" }}
          width={145}
        />
      </Link>

      <nav className="customer-nav" aria-label="Điều hướng khách hàng">
        <VehicleMegaMenu />
        <MotorbikeMegaMenu />
        <Link href="/compare">So sánh</Link>
        <Link href="/locations">Trạm sạc &amp; Showroom</Link>
      </nav>

      <div className="customer-header-actions">
        <div className="header-account-menu" ref={accountMenuRef}>
          <button
            aria-expanded={accountOpen}
            aria-haspopup="menu"
            className="header-account-link"
            onClick={() => {
              setMenuOpen(false);
              setAccountOpen((open) => !open);
            }}
            type="button"
          >
            <CircleUserRound aria-hidden="true" size={19} />
            <span>Tài khoản</span>
            <ChevronDown aria-hidden="true" className={accountOpen ? "is-open" : ""} size={14} />
          </button>
          {accountOpen ? (
            <div className="account-popover" role="menu">
              {isAuthenticated ? (
                <>
                  <div className="account-popover-heading">
                    <strong>{profile?.full_name?.trim() || "Tài khoản VinFast"}</strong>
                    <span className="header-user-email">{user.email}</span>
                  </div>
                  <Link href="/account" onClick={() => setAccountOpen(false)} role="menuitem">
                    <CircleUserRound aria-hidden="true" size={18} />
                    <span><strong>Tài khoản của tôi</strong><small>Xem hành trình tư vấn đã lưu</small></span>
                  </Link>
                  <Link href="/notifications" onClick={() => setAccountOpen(false)} role="menuitem">
                    <BellRing aria-hidden="true" size={18} />
                    <span><strong>Thông báo chính sách</strong><small>Xem nội dung đã được duyệt</small></span>
                  </Link>
                  <button onClick={handleLogout} role="menuitem" type="button">
                    <LogIn aria-hidden="true" size={18} />
                    <span><strong>Đăng xuất</strong><small>Kết thúc phiên đăng nhập</small></span>
                  </button>
                </>
              ) : (
                <>
                  <div className="account-popover-heading">
                    <strong>Tài khoản VinFast</strong>
                    <span>Đăng nhập để lưu hành trình tư vấn của bạn.</span>
                  </div>
                  <Link href="/login" onClick={() => setAccountOpen(false)} role="menuitem">
                    <LogIn aria-hidden="true" size={18} />
                    <span><strong>Đăng nhập</strong><small>Truy cập tài khoản của bạn</small></span>
                  </Link>
                  <Link href="/register" onClick={() => setAccountOpen(false)} role="menuitem">
                    <UserPlus aria-hidden="true" size={18} />
                    <span><strong>Đăng ký tài khoản</strong><small>Tạo tài khoản khách hàng mới</small></span>
                  </Link>
                </>
              )}
            </div>
          ) : null}
        </div>

        <Link className="header-test-drive-link" href="/test-drive">
          <CalendarDays aria-hidden="true" size={17} />
          <span>Đặt lịch lái thử</span>
        </Link>

        <button
          aria-expanded={menuOpen}
          aria-label={menuOpen ? "Đóng menu" : "Mở menu"}
          className="mobile-menu-button"
          onClick={() => {
            setAccountOpen(false);
            setMenuOpen((open) => !open);
          }}
          type="button"
        >
          {menuOpen ? <X aria-hidden="true" size={22} /> : <Menu aria-hidden="true" size={22} />}
        </button>
      </div>

      {menuOpen ? (
        <div className="mobile-nav-panel">
          <Link href="/vehicles" onClick={closeMobileMenu}>Xem tất cả ô tô</Link>
          <MobileVehicleMenu onVehicleClick={closeMobileMenu} />
          <Link href="/motorbikes" onClick={closeMobileMenu}>Xem tất cả xe máy điện</Link>
          <MobileMotorbikeMenu onMotorbikeClick={closeMobileMenu} />
          <Link href="/compare" onClick={closeMobileMenu}>So sánh</Link>
          <Link href="/locations" onClick={closeMobileMenu}>Trạm sạc &amp; Showroom</Link>
          <Link href="/test-drive" onClick={closeMobileMenu}>Đặt lịch lái thử</Link>
          {isAuthenticated ? <Link href="/notifications" onClick={closeMobileMenu}>Thông báo chính sách</Link> : null}
          <Link href="/account" onClick={closeMobileMenu}>Tài khoản</Link>
          {isAuthenticated ? (
            <button onClick={handleLogout} type="button">Đăng xuất ({user.email})</button>
          ) : (
            <>
              <Link href="/login" onClick={closeMobileMenu}>Đăng nhập</Link>
              <Link href="/register" onClick={closeMobileMenu}>Đăng ký</Link>
            </>
          )}
          <span className="demo-menu-label">Chuyển khu vực</span>
          <RoleDemoSwitcher />
          <DemoResetButton />
        </div>
      ) : null}
    </header>
  );
}
