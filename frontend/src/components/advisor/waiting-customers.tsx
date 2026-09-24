"use client";

import { Hand } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { customerProfileFromSessionHref } from "@/components/customer360/profile-links";
import { relativeAge } from "@/components/customer360/customer360-labels";
import { useClock } from "@/components/customer360/use-clock";
import { type AdvisorConversationDetail, joinAdvisorConversation, listAdvisorConversations } from "@/lib/api/agent";

/** Làm mới số khách đang chờ — đủ nhanh để khách không phải chờ lâu, đủ thưa để không dội backend. */
const POLL_MS = 30_000;

/** Phiên khách đang CHỜ người thật (khách xin gặp tư vấn viên, AI đã dừng). */
export function isWaiting(item: AdvisorConversationDetail): boolean {
  const status = item.status?.toUpperCase();
  if (status === "COMPLETED" || status === "CLOSED") return false;
  return status === "WAITING_ADVISOR" || item.ownership === "PENDING_HANDOFF";
}

/**
 * Các phiên đang chờ tư vấn viên trong phạm vi của người xem (backend lọc — Phase 0: khách
 * mình phụ trách + khách chưa ai nhận đang chờ). Chờ lâu nhất trước. `enabled=false` → không gọi.
 */
export function useWaitingConversations(enabled = true): readonly AdvisorConversationDetail[] {
  const [items, setItems] = useState<readonly AdvisorConversationDetail[]>([]);

  useEffect(() => {
    if (!enabled) return;
    let active = true;
    const load = () =>
      listAdvisorConversations()
        .then((response) => {
          if (!active) return;
          const waiting = (response.items || []).filter(isWaiting);
          setItems([...waiting].sort((a, b) => a.last_activity_at.localeCompare(b.last_activity_at)));
        })
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [enabled]);

  return items;
}

/**
 * Đầu trang "Khách hàng": khách đang xin gặp tư vấn viên — tiếp quản ngay, không phải mò trong
 * danh sách. Không có ai chờ thì không hiện gì.
 */
export function WaitingCustomers() {
  const router = useRouter();
  const now = useClock();
  const items = useWaitingConversations();
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  if (!items.length) return null;

  async function takeOver(conversationId: string) {
    setBusy(conversationId);
    setFailed(false);
    try {
      await joinAdvisorConversation(conversationId);
      router.push(`/advisor/conversations/${conversationId}`);
    } catch {
      setBusy(null);
      setFailed(true);
    }
  }

  return (
    <section aria-labelledby="waiting-customers-title" className="waiting-customers">
      <h2 id="waiting-customers-title">
        <Hand aria-hidden="true" size={16} /> Khách đang chờ gặp tư vấn viên ({items.length})
      </h2>
      {failed ? (
        <p role="alert">Không tiếp quản được — phiên đã có người nhận hoặc đã kết thúc.</p>
      ) : null}
      <ul>
        {items.map((item) => {
          const name = item.customer_display || (item.customer_id.startsWith("anon-") ? "Khách vãng lai" : item.customer_id);
          const age = relativeAge(item.last_activity_at, now);
          return (
            <li key={item.conversation_id}>
              <div>
                <strong>{name}</strong>
                <small>
                  {age ? `Chờ ${age === "Hôm qua" ? "từ hôm qua" : age}` : ""}
                  {item.last_message_preview ? ` · “${item.last_message_preview}”` : ""}
                </small>
              </div>
              {!item.customer_id.startsWith("anon-") ? (
                <Link href={customerProfileFromSessionHref(item.conversation_id)}>Hồ sơ</Link>
              ) : null}
              <button
                aria-label={`Tiếp quản ${name}`}
                className="primary-button"
                disabled={busy !== null}
                onClick={() => void takeOver(item.conversation_id)}
                type="button"
              >
                {busy === item.conversation_id ? "Đang tiếp quản..." : "Tiếp quản"}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
