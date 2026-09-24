"use client";

import { ArrowRight, CalendarClock, Compass, MessageCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ProfileCompletionForm } from "@/components/customer/profile-completion-form";
import { AppHeader } from "@/components/shared/app-header";
import { refreshCustomerIdentity } from "@/lib/api/agent";
import { getProfile, me, type UserProfile } from "@/lib/api/auth";
import { isProfileComplete } from "@/lib/api/customer-profile";

/** Cờ báo "đã cho xem màn chào ở phiên này" — chỉ hiện một lần mỗi lượt đăng nhập. */
const WELCOME_SHOWN_KEY = "p150.welcomed";
/** Tiền tố khoá localStorage đánh dấu trình duyệt này đã từng thấy email đó đăng nhập.
 *
 * Không có cờ "lần đăng nhập đầu tiên" nào từ backend (`/auth/me` không trả nó),
 * nên đây là phỏng đoán ở phía trình duyệt: lần đầu THIẾT BỊ NÀY thấy email này
 * là lần đầu, không phải lần đầu của tài khoản trên mọi thiết bị. Đủ dùng cho câu
 * chào — sai vô hại (chào "gặp lại" hơi sớm) chứ không chặn luồng nào.
 */
const KNOWN_USER_PREFIX = "p150.knownUser:";

function safeSessionGet(key: string): string | null {
  try {
    return window.sessionStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSessionSet(key: string, value: string): void {
  try {
    window.sessionStorage.setItem(key, value);
  } catch {
    // Chế độ riêng tư / storage bị chặn: bỏ qua, không chặn trải nghiệm.
  }
}

function hasSeenBefore(email: string): boolean {
  try {
    return window.localStorage.getItem(`${KNOWN_USER_PREFIX}${email}`) === "1";
  } catch {
    return false;
  }
}

function markSeen(email: string): void {
  try {
    window.localStorage.setItem(`${KNOWN_USER_PREFIX}${email}`, "1");
  } catch {
    // Chế độ riêng tư / storage bị chặn: bỏ qua, không chặn trải nghiệm.
  }
}

function greetingName(fullName: string | null | undefined, email: string): string {
  const trimmed = fullName?.trim();
  if (trimmed) return trimmed;
  const [prefix] = email.split("@");
  return prefix || email;
}

/** `profile`: hồ sơ còn thiếu tên/SĐT — xin thông tin trước lời chào (plan §19). */
type ViewState = "checking" | "profile" | "ready";

export default function WelcomePage() {
  const router = useRouter();
  const [view, setView] = useState<ViewState>("checking");
  const [name, setName] = useState("");
  const [returning, setReturning] = useState(true);
  const [email, setEmail] = useState("");
  const [profile, setProfile] = useState<UserProfile | null>(null);

  useEffect(() => {
    let active = true;

    async function bootstrap(): Promise<void> {
      if (safeSessionGet(WELCOME_SHOWN_KEY) === "1") {
        router.replace("/");
        return;
      }

      const currentUser = await me().catch(() => null);
      if (!active) return;
      if (!currentUser) {
        router.replace("/login");
        return;
      }

      const profile = await getProfile().catch(() => null);
      if (!active) return;
      // Khách đăng nhập = có hồ sơ bên tư vấn viên ngay (plan §20), kể cả khi bỏ qua bước khai.
      if (currentUser.role === "customer") void refreshCustomerIdentity().catch(() => undefined);

      const seenBefore = hasSeenBefore(currentUser.email);
      markSeen(currentUser.email);
      safeSessionSet(WELCOME_SHOWN_KEY, "1");

      setName(greetingName(profile?.full_name, currentUser.email));
      setReturning(seenBefore);
      setEmail(currentUser.email);
      setProfile(profile);
      // Chỉ KHÁCH mới được hỏi; tài khoản không phải khách (hiếm khi tới đây) đi thẳng lời chào.
      setView(currentUser.role === "customer" && !isProfileComplete(profile) ? "profile" : "ready");
    }

    bootstrap();
    return () => {
      active = false;
    };
  }, [router]);

  if (view === "checking") {
    return (
      <>
        <AppHeader />
        <main className="welcome-page" />
      </>
    );
  }

  if (view === "profile") {
    return (
      <>
        <AppHeader />
        <main className="welcome-page">
          <section className="welcome-card">
            <ProfileCompletionForm
              onSaved={(saved) => {
                setName(greetingName(saved.full_name, email));
                setView("ready");
              }}
              onSkip={() => setView("ready")}
              profile={profile}
            />
          </section>
        </main>
      </>
    );
  }

  return (
    <>
    <AppHeader />
    <main className="welcome-page">
      <section className="welcome-card">
        <span className="eyebrow">VinFast AI Sales Advisor</span>
        <h1>
          Chào {name}, rất vui được gặp{returning ? " lại" : ""}
        </h1>
        <p>Hôm nay anh/chị muốn bắt đầu từ đâu?</p>
        <div className="welcome-actions">
          <Link className="welcome-action" href="/consultation">
            <MessageCircle aria-hidden="true" size={22} />
            <span>Tư vấn chọn xe theo nhu cầu</span>
            <ArrowRight aria-hidden="true" size={18} />
          </Link>
          <Link className="welcome-action" href="/vehicles">
            <Compass aria-hidden="true" size={22} />
            <span>Xem các mẫu xe</span>
            <ArrowRight aria-hidden="true" size={18} />
          </Link>
          <Link className="welcome-action" href="/account#test-drive-bookings">
            <CalendarClock aria-hidden="true" size={22} />
            <span>Lịch lái thử của tôi</span>
            <ArrowRight aria-hidden="true" size={18} />
          </Link>
        </div>
        <Link className="welcome-skip" href="/">
          Bỏ qua
        </Link>
      </section>
    </main>
    </>
  );
}
