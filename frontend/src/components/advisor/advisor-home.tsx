"use client";

import { useEffect, useState } from "react";

import { AdvisorDashboard } from "@/components/customer360/advisor-dashboard";
import { fetchCustomer360Meta } from "@/lib/api/agent";

import { NoticeCard } from "./notice-card";

/**
 * Nội dung "Tổng quan". Cờ `customer360_ui` bật → dashboard khách của tôi (kèm thông báo);
 * tắt → chỉ còn thông báo nội bộ (số liệu khách cần Customer 360 mới có ý nghĩa).
 */
export function AdvisorHome() {
  const [dashboard, setDashboard] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetchCustomer360Meta().then((meta) => {
      if (active) setDashboard(meta.enabled.ui);
    });
    return () => {
      active = false;
    };
  }, []);

  if (dashboard === null) return null;
  return dashboard ? <AdvisorDashboard /> : <NoticeCard />;
}
