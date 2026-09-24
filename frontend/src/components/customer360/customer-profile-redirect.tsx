"use client";

import { LoaderCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { fetchAdvisorConversation } from "@/lib/api/agent";
import { useAuth } from "@/store/auth-store";

/**
 * Tra khách của một phiên rồi thay URL bằng hồ sơ khách. Backend chỉ trả phiên trong phạm
 * vi người xem (Phase 0), nên phiên ngoài phạm vi dừng ở thông báo thay vì lộ `customer_id`.
 */
export function CustomerProfileRedirect({ sessionId }: Readonly<{ sessionId: string }>) {
  const router = useRouter();
  const { user } = useAuth();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let active = true;
    fetchAdvisorConversation(sessionId)
      .then((detail) => {
        if (!active) return;
        const base = user?.role === "admin" ? "/admin/customers" : "/advisor/customers";
        router.replace(`${base}/${encodeURIComponent(detail.customer_id)}`);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
    };
  }, [router, sessionId, user?.role]);

  return failed ? (
    <div className="ops-state" role="alert">
      <h2>Không mở được hồ sơ khách</h2>
      <p>Phiên này không thuộc phạm vi phụ trách của bạn, hoặc không tồn tại.</p>
    </div>
  ) : (
    <div aria-busy="true" className="ops-state">
      <LoaderCircle className="spin" size={24} />
      <p>Đang mở hồ sơ khách...</p>
    </div>
  );
}
