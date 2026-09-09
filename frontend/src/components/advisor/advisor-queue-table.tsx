"use client";

import { AlertCircle, Inbox, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AdvisorQueuePollToast, useAdvisorQueuePoll } from "@/components/advisor/advisor-queue-poll";
import { StatusBadge } from "@/components/shared/status-badge";
import { AgentApiError, fetchBottleneckSignals, fetchReviews } from "@/lib/api/agent";
import type { BottleneckSignal, QueueEntry, ReviewQueueStatus } from "@/types/agent";
import { bottleneckLabel, OFFER_STATE_BADGES } from "./offer-state-labels";

type LoadState = "loading" | "ready" | "error";

type BadgeTone = "neutral" | "info" | "success" | "warning" | "danger";

/**
 * D11 — ba trạng thái ưu đãi phải phân biệt được bằng CẢ chữ lẫn màu. Tông màu
 * và nhãn lấy từ `offer-state-labels` (dùng chung với `advisor-review-panel.tsx`):
 * tư vấn viên nhìn badge ở hàng chờ rồi mở panel, hai màn phải nói cùng một
 * thứ tiếng. Thiếu `offer_state` (hàng cũ chưa có snapshot) rơi về xám.
 */
const QUEUE_STATUS_BADGES: Record<string, { readonly tone: BadgeTone; readonly label: string }> = {
  PENDING: { tone: "warning", label: "Chờ duyệt" },
  APPROVED: { tone: "success", label: "Đã duyệt" },
  REJECTED: { tone: "danger", label: "Đã từ chối" },
  EXPIRED: { tone: "neutral", label: "Quá hạn" },
};

const TABS: readonly { readonly status: ReviewQueueStatus; readonly label: string }[] = [
  { status: "pending", label: "Chờ duyệt" },
  { status: "approved", label: "Đã duyệt" },
  { status: "rejected", label: "Đã từ chối" },
];

const EMPTY_TEXT: Record<ReviewQueueStatus, string> = {
  pending: "Không có mục chờ duyệt",
  approved: "Chưa có mục đã duyệt",
  rejected: "Chưa có mục đã từ chối",
};

// Định dạng ngày giờ theo chuẩn Việt
function formatMoment(value: string): string {
  return new Date(value).toLocaleString("vi-VN");
}

// Tóm tắt nội dung duyệt
function summarize(content: string): string {
  const trimmed = content.trim().replaceAll(/\s+/g, " ");
  return trimmed.length > 90 ? `${trimmed.slice(0, 90)}…` : trimmed;
}

function formatAge(minutes: number): string {
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} giờ` : `${hours} giờ ${rest} phút`;
}

/**
 * T13.5 — cờ tuổi: quá 30 phút thì vàng, quá 60 phút (chạm SLA lazy-expire) thì
 * đỏ. Hàng cũ chưa có `age_minutes` thì để trống chứ không bịa số.
 */
function AgeCell({ minutes }: Readonly<{ minutes: number | null }>) {
  if (minutes === null) return <>—</>;
  const rounded = Math.max(0, Math.round(minutes));
  const label = formatAge(rounded);
  if (rounded > 60) return <StatusBadge tone="danger">{label}</StatusBadge>;
  if (rounded > 30) return <StatusBadge tone="warning">{label}</StatusBadge>;
  return <>{label}</>;
}

export function AdvisorQueueTable() {
  const [tab, setTab] = useState<ReviewQueueStatus>("pending");
  const [items, setItems] = useState<readonly QueueEntry[]>([]);
  const [signals, setSignals] = useState<readonly BottleneckSignal[]>([]);
  const [status, setStatus] = useState<LoadState>("loading");
  const [reloadToken, setReloadToken] = useState(0);
  const [errorText, setErrorText] = useState("");
  const poll = useAdvisorQueuePoll();

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchReviews({ status: tab }),
      fetchBottleneckSignals({ status: tab === "approved" ? "correct" : tab === "rejected" ? "incorrect" : "pending" }),
    ])
      .then(([queue, signalQueue]) => {
        if (!active) return;
        setItems(queue);
        setSignals(signalQueue);
        setStatus("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setErrorText(
          error instanceof AgentApiError && error.status === 403
            ? "Tài khoản này không có quyền xem hàng đợi duyệt."
            : "Không tải được hàng đợi duyệt.",
        );
        setStatus("error");
      });
    return () => {
      active = false;
    };
  }, [reloadToken, tab]);

  // Bấm vào tab là một lần làm mới có chủ đích: tải lại đúng tab đó và coi như
  // tư vấn viên đã nhìn hàng chờ (xoá badge "mục mới").
  const selectTab = (next: ReviewQueueStatus) => {
    setTab(next);
    setStatus("loading");
    setReloadToken((token) => token + 1);
    if (next === "pending") poll.acknowledge();
  };

  // Số chờ duyệt lấy từ lượt poll gần nhất; chưa poll lần nào thì dùng chính
  // bảng đang mở (chỉ đúng khi đang ở tab "Chờ duyệt").
  const pendingBadge =
    poll.entries === null
      ? tab === "pending" && status === "ready"
        ? items.length
        : 0
      : poll.pendingCount;

  return (
    <section className="ops-panel">
      <div className="queue-tabs">
        {TABS.map((entry) => (
          <button
            aria-pressed={tab === entry.status}
            className={tab === entry.status ? "is-active" : undefined}
            key={entry.status}
            onClick={() => {
              selectTab(entry.status);
            }}
            type="button"
          >
            {entry.label}
            {entry.status === "pending" && pendingBadge > 0 ? <span>{pendingBadge}</span> : null}
            {entry.status === "pending" && poll.newCount > 0 ? (
              <StatusBadge tone="danger">+{poll.newCount} mới</StatusBadge>
            ) : null}
          </button>
        ))}
      </div>
      <AdvisorQueuePollToast count={poll.newCount} onDismiss={poll.acknowledge} />
      <QueueBody
        errorText={errorText}
        items={items}
        signals={signals}
        onRetry={() => {
          setStatus("loading");
          setReloadToken((token) => token + 1);
        }}
        status={status}
        tab={tab}
      />
    </section>
  );
}

function QueueBody({
  errorText,
  items,
  signals,
  onRetry,
  status,
  tab,
}: Readonly<{
  errorText: string;
  items: readonly QueueEntry[];
  signals: readonly BottleneckSignal[];
  onRetry: () => void;
  status: LoadState;
  tab: ReviewQueueStatus;
}>) {
  if (status === "loading") {
    return (
      <div className="ops-state"><LoaderCircle className="spin" size={32} /><h2>Đang tải hàng đợi</h2></div>
    );
  }

  if (status === "error") {
    return (
      <div className="ops-state"><AlertCircle size={32} /><h2>{errorText}</h2><button className="primary-button" onClick={onRetry} type="button">Thử lại</button></div>
    );
  }

  if (items.length === 0 && signals.length === 0) {
    return (
      <div className="ops-state"><Inbox size={32} /><h2>{EMPTY_TEXT[tab]}</h2><p>Bản nháp và signal mới sẽ xuất hiện ngay tại đây.</p></div>
    );
  }

  return (
    <div className="queue-table-wrap">
      <table className="queue-table">
        <thead>
          <tr>
            <th>Bản nháp</th>
            <th>Trạng thái ưu đãi</th>
            <th>Tuổi</th>
            <th>Gửi lúc</th>
            <th>Người giữ</th>
            <th>Cờ</th>
            <th>Trạng thái</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {signals.map((signal) => (
            <tr key={signal.signal_id}>
              <td data-label="Bản nháp"><StatusBadge tone="info">Xác nhận nút thắt</StatusBadge> {summarize(signal.evidence_quote)}</td>
              <td data-label="Trạng thái ưu đãi">{bottleneckLabel(signal.label)}</td>
              <td data-label="Tuổi">—</td>
              <td data-label="Gửi lúc">{formatMoment(signal.created_at)}</td>
              <td data-label="Người giữ">{signal.claimed_by ?? "—"}</td>
              <td data-label="Cờ">{signal.lease_expires_at === null ? "—" : `Lease ${formatMoment(signal.lease_expires_at)}`}</td>
              <td data-label="Trạng thái"><StatusBadge tone={signal.status === "CORRECT" ? "success" : signal.status === "INCORRECT" ? "danger" : "warning"}>{signal.status === "CORRECT" ? "Đúng" : signal.status === "INCORRECT" ? "Sai" : "Chờ xác nhận"}</StatusBadge></td>
              <td><Link className="table-action" href={`/advisor/bottleneck-signals/${signal.signal_id}`}>Xác nhận →</Link></td>
            </tr>
          ))}
          {items.map((item) => {
            const offer = OFFER_STATE_BADGES[item.offer_state ?? "NONE_BOTTLENECK"];
            const queueStatus = QUEUE_STATUS_BADGES[item.status] ?? {
              tone: "neutral" as const,
              label: item.status,
            };
            return (
              <tr key={item.review_id}>
                <td data-label="Bản nháp"><StatusBadge tone="neutral">Duyệt nội dung</StatusBadge> {summarize(item.content)}</td>
                <td data-label="Trạng thái ưu đãi">
                  <StatusBadge tone={offer.tone}>{offer.label}</StatusBadge>
                </td>
                <td data-label="Tuổi">
                  <AgeCell minutes={item.age_minutes} />
                </td>
                <td data-label="Gửi lúc">{formatMoment(item.created_at)}</td>
                <td data-label="Người giữ">{item.claimed_by ?? "—"}</td>
                <td data-label="Cờ">
                  {item.handoff_requested ? (
                    <StatusBadge tone="info">Chuyển tư vấn trực tiếp</StatusBadge>
                  ) : null}
                  {item.offer_suggestion_ignored ? (
                    <StatusBadge tone="warning">Bỏ qua ưu đãi đề xuất</StatusBadge>
                  ) : null}
                  {!item.handoff_requested && !item.offer_suggestion_ignored ? "—" : null}
                </td>
                <td data-label="Trạng thái">
                  <StatusBadge tone={queueStatus.tone}>{queueStatus.label}</StatusBadge>
                </td>
                <td>
                  <Link
                    className="table-action"
                    href={`/advisor/recommendations/${item.review_id}`}
                  >
                    Xem &amp; duyệt →
                  </Link>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
