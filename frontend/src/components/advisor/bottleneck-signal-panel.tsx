"use client";

import { AlertCircle, ArrowLeft, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { OfferPicker } from "@/components/advisor/offer-picker";
import { StatusBadge } from "@/components/shared/status-badge";
import { AgentApiError, claimBottleneckSignal, fetchBottleneckSignalDetail, sendBottleneckSignalOffer, sendBottleneckSignalVerdict } from "@/lib/api/agent";
import type { BottleneckSignalDetail, BottleneckSignalVerdict, OfferAdjustment } from "@/types/agent";
import { bottleneckLabel } from "./offer-state-labels";

type LoadState = "loading" | "ready" | "error";

function errorMessage(error: unknown): string {
  if (error instanceof AgentApiError && error.status === 403) return "Tài khoản này không có quyền xác nhận nút thắt.";
  if (error instanceof AgentApiError && error.code === "signal_not_claimable_or_lease_invalid") return "Signal đang do tư vấn viên khác xử lý hoặc lease đã hết hạn.";
  if (error instanceof AgentApiError && error.code === "promotion_expired") return "Chương trình ưu đãi đã hết hiệu lực — chọn chương trình khác.";
  if (error instanceof AgentApiError && error.code === "adjustment_out_of_bounds") return "Ưu đãi vượt biên độ ADMIN cấu hình — chỉnh lại trong biên rồi gửi.";
  if (error instanceof AgentApiError && error.code === "signal_offer_unavailable") return "Ưu đãi chưa khả dụng. Tải lại trạng thái signal rồi thử lại.";
  if (error instanceof AgentApiError && error.status === 404) return "Signal không còn tồn tại.";
  return "Không thực hiện được thao tác. Vui lòng thử lại.";
}

const STATUS = {
  PENDING: { label: "Chờ xác nhận", tone: "warning" },
  CORRECT: { label: "Đã xác nhận đúng", tone: "success" },
  INCORRECT: { label: "Đã xác nhận sai", tone: "danger" },
} as const;

export function BottleneckSignalPanel({ signalId }: Readonly<{ signalId: string }>) {
  const [detail, setDetail] = useState<BottleneckSignalDetail | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [claimed, setClaimed] = useState(false);
  const busyRef = useRef(false);

  const load = useCallback(async () => {
    try {
      setDetail(await fetchBottleneckSignalDetail(signalId));
      setLoadState("ready");
    } catch (error) {
      setNotice(errorMessage(error));
      setLoadState("error");
    }
  }, [signalId]);

  useEffect(() => {
    void fetchBottleneckSignalDetail(signalId).then(
      (signal) => {
        setDetail(signal);
        setLoadState("ready");
      },
      (error: unknown) => {
        setNotice(errorMessage(error));
        setLoadState("error");
      },
    );
  }, [signalId]);

  async function run(action: () => Promise<void>): Promise<void> {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setNotice("");
    try { await action(); } catch (error) { setNotice(errorMessage(error)); } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  function claim(): void {
    void run(async () => {
      const signal = await claimBottleneckSignal(signalId);
      setClaimed(true);
      setDetail((current) => current === null ? current : { ...current, ...signal });
    });
  }

  function verdict(value: BottleneckSignalVerdict): void {
    void run(async () => {
      const signal = await sendBottleneckSignalVerdict(signalId, value);
      if (signal.status === "CORRECT") {
        const confirmed = await fetchBottleneckSignalDetail(signalId);
        setDetail(confirmed);
      } else {
        setDetail((current) => current === null ? current : { ...current, ...signal });
        setNotice("Signal đã đánh dấu sai. Không cấp ưu đãi từ bằng chứng này.");
      }
    });
  }

  function offer(adjustment: OfferAdjustment): void {
    void run(async () => {
      await sendBottleneckSignalOffer(signalId, adjustment);
      setNotice("Ưu đãi đã được ghi nhận cho signal này.");
    });
  }

  if (loadState === "loading") return <div className="ops-state"><LoaderCircle className="spin" size={32} /><h2>Đang tải signal</h2></div>;
  if (loadState === "error" || detail === null) return <div className="ops-state"><AlertCircle size={32} /><h2>{notice}</h2><button className="primary-button" onClick={() => void load()} type="button">Thử lại</button></div>;

  const meta = STATUS[detail.status];
  const lease = detail.lease_expires_at === null ? "Chưa có lease" : `Lease đến ${new Date(detail.lease_expires_at).toLocaleString("vi-VN")}`;
  return <div className="signal-detail"><Link className="vehicle-detail-back" href="/advisor"><ArrowLeft size={16} /> Hàng đợi</Link><header className="signal-detail-heading"><div><span className="eyebrow">Xác nhận nút thắt</span><h1>{bottleneckLabel(detail.label)}</h1><p>Kiểm tra bằng chứng đã ẩn dữ liệu nhạy cảm trước khi mở quyền cấp ưu đãi.</p></div><StatusBadge tone={meta.tone}>{meta.label}</StatusBadge></header><section className="ops-panel signal-evidence" aria-label="Bằng chứng signal"><h2>Bằng chứng đã lược danh tính</h2><blockquote>{detail.evidence_quote}</blockquote><dl><div><dt>Người giữ</dt><dd>{detail.claimed_by ?? "Chưa có"}</dd></div><div><dt>Lease</dt><dd>{lease}</dd></div></dl></section>{notice ? <div className="inline-warning" role="status">{notice}</div> : null}{detail.status === "PENDING" ? <section className="signal-actions">{!claimed ? <button className="primary-button" disabled={busy} onClick={claim} type="button">Nhận xử lý</button> : <><button className="primary-button" disabled={busy} onClick={() => verdict("CORRECT")} type="button">Đúng</button><button className="danger-button" disabled={busy} onClick={() => verdict("INCORRECT")} type="button">Sai</button></>}</section> : null}{detail.status === "CORRECT" ? <OfferPicker busy={busy} onSubmit={offer} policies={detail.adjustment_policies} promotions={detail.matched_promotions} /> : null}</div>;
}
