"use client";

import { ArrowUp, CalendarDays } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";

import { useTypewriter } from "@/lib/use-typewriter";
import { usePrefersReducedMotion } from "@/lib/use-prefers-reduced-motion";

import { OPEN_AGENT_DOCK_EVENT } from "@/components/customer/open-agent-dock-button";
import { useEmbedMode } from "@/lib/use-embed-mode";

//: Câu hỏi mẫu chạy chữ trong ô gõ ở SẢNH CHÍNH (Sếp 2026-08-31): cho khách
//: thấy hỏi được gì; trỏ chuột / bấm / gõ là tắt NGAY để không tranh chỗ.
const SAMPLE_QUESTIONS: readonly string[] = [
  "Xe điện khoảng 500 triệu cho gia đình 4 người?",
  "VF 5 sạc bao lâu, đi được bao xa?",
  "Chi phí nuôi VF 3 mỗi tháng hết bao nhiêu?",
  "Giá lăn bánh VF 6 ở Hà Nội là bao nhiêu?",
  "Đặt lịch lái thử ở showroom gần tôi thế nào?",
];

export function AgentDock() {
  const embedded = useEmbedMode();
  const router = useRouter();
  const pathname = usePathname();
  const [message, setMessage] = useState("");
  const [hintOff, setHintOff] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const reducedMotion = usePrefersReducedMotion();
  // Chỉ chạy chữ khi khách CHƯA đụng tới ô gõ; reduced-motion thì không chạy.
  const hintActive = !hintOff && message.length === 0 && !reducedMotion;
  const { display } = useTypewriter(SAMPLE_QUESTIONS, { active: hintActive });

  useEffect(() => {
    function openDock(event: Event): void {
      const detail = (event as CustomEvent<{ prompt?: string }>).detail;
      if (detail?.prompt) setMessage(detail.prompt);
      inputRef.current?.focus({ preventScroll: false });
    }

    window.addEventListener(OPEN_AGENT_DOCK_EVENT, openDock);
    return () => window.removeEventListener(OPEN_AGENT_DOCK_EVENT, openDock);
  }, []);

  if (pathname?.startsWith("/consultation")) {
    return null;
  }

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const query = message.trim();
    const params = new URLSearchParams();
    if (query) params.set("prompt", query);
    if (pathname && pathname !== "/" && !pathname.startsWith("/consultation")) {
      params.set("from", pathname);
    }
    const queryString = params.toString();
    router.push(queryString ? `/consultation?${queryString}` : "/consultation");
  }

  if (embedded) return null; // trang đang nằm trong cửa sổ hội thoại

  return (
    <aside className="agent-dock" aria-label="Trợ lý tư vấn">
      <form onSubmit={submit}>
        <div className="agent-dock-input-wrap">
          <input
            aria-label="Câu hỏi cho trợ lý"
            onChange={(event) => setMessage(event.target.value)}
            onFocus={() => setHintOff(true)}
            onPointerEnter={() => setHintOff(true)}
            placeholder={hintActive ? "" : "Bạn muốn hỏi gì về VinFast?"}
            ref={inputRef}
            value={message}
          />
          {hintActive ? (
            <span aria-hidden="true" className="agent-dock-hint">
              {display}
              <span className="agent-dock-hint-caret" />
            </span>
          ) : null}
        </div>
        <button aria-label="Gửi câu hỏi" type="submit"><ArrowUp aria-hidden="true" size={19} /></button>
      </form>
      {/* Cùng động từ với header ("Đặt lịch lái thử") — hai chữ khác nhau cho
          cùng một việc làm khách tưởng là hai việc. */}
      <Link href="/test-drive"><CalendarDays size={18} /><span>Đặt lịch lái thử</span></Link>
    </aside>
  );
}
