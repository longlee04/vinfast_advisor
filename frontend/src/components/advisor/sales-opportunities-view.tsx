"use client";

import { useEffect, useState } from "react";

import { OpportunityQueue } from "@/components/customer360/opportunity-queue";
import { fetchCustomer360Meta } from "@/lib/api/agent";

import { SalesOpportunityList } from "./sales-opportunity-list";

/** Cờ `customer360_ui` bật → danh sách theo CƠ HỘI + hàng chờ; tắt → danh sách theo phiên cũ. */
export function SalesOpportunitiesView() {
  const [useOpportunities, setUseOpportunities] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    fetchCustomer360Meta().then((meta) => {
      if (active) setUseOpportunities(meta.enabled.ui);
    });
    return () => {
      active = false;
    };
  }, []);

  if (useOpportunities === null) return null;
  return useOpportunities ? <OpportunityQueue /> : <SalesOpportunityList />;
}
