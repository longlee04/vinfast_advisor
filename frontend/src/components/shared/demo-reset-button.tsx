"use client";

import { RotateCcw } from "lucide-react";

import { useDemoStore } from "@/store/demo-store";

export function DemoResetButton({ compact = false }: Readonly<{ compact?: boolean }>) {
  const { resetDemo } = useDemoStore();

  return (
    <button className={compact ? "text-button text-button-compact" : "secondary-button"} onClick={resetDemo} type="button">
      <RotateCcw aria-hidden="true" size={15} />
      Đặt lại phiên
    </button>
  );
}
