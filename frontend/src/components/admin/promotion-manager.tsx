"use client";

import { CheckCircle2, Pencil, Plus, Power, RefreshCw, X, XCircle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { PROMOTION_TYPE_LABELS } from "@/components/advisor/offer-state-labels";
import { StatusBadge } from "@/components/shared/status-badge";
import {
  type AdminPromotion,
  activatePromotion,
  cancelPromotion,
  createPromotion,
  type EligibilityRules,
  fetchPromotionStats,
  fetchRuleSchema,
  listPromotions,
  PromotionApiError,
  type PromotionInput,
  type PromotionStats,
  type PromotionStatus,
  type PromotionTypeCode,
  publishPromotionNotice,
  updatePromotion,
  validatePromotionRules,
} from "@/lib/api/promotions";

import { EligibilityRuleBuilder } from "./eligibility-rule-builder";

const STATUS_BADGES: Record<PromotionStatus, { tone: "success" | "warning" | "neutral"; label: string }> = {
  ACTIVE: { tone: "success", label: "Đang áp dụng" },
  UNVERIFIED: { tone: "warning", label: "Chưa kiểm" },
  DRAFT: { tone: "neutral", label: "Nháp" },
  EXPIRED: { tone: "neutral", label: "Hết hạn" },
  CANCELLED: { tone: "neutral", label: "Đã huỷ" },
};

type Draft = PromotionInput & { readonly promotion_id?: string };

function errorText(error: unknown): string {
  if (error instanceof PromotionApiError) return error.errors.length ? `${error.code}: ${error.errors.join("; ")}` : error.code;
  return "Không thực hiện được thao tác.";
}

function toDateInput(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : "";
}

/**
 * `/admin/promotions` (plan Customer 360 §2.6): tạo/sửa/huỷ ưu đãi, dựng luật, duyệt
 * UNVERIFIED → ACTIVE, xem hiệu quả. Ưu đãi mới luôn là "Chưa kiểm" — chỉ nút Kích hoạt
 * (backend kiểm luật + hạn) mới đưa được lên "Đang áp dụng".
 */
export function PromotionManager() {
  const [items, setItems] = useState<readonly AdminPromotion[]>([]);
  const [stats, setStats] = useState<readonly PromotionStats[]>([]);
  const [fieldTypes, setFieldTypes] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState<PromotionStatus | "ALL">("ALL");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [notify, setNotify] = useState<AdminPromotion | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setError(null);
    try {
      const [list, stat] = await Promise.all([listPromotions(), fetchPromotionStats().catch(() => [])]);
      setItems(list);
      setStats(stat);
    } catch (err) {
      setError(errorText(err));
    }
  }, []);

  useEffect(() => {
    void reload();
    fetchRuleSchema()
      .then((schema) => setFieldTypes(schema.fields))
      .catch(() => setFieldTypes({}));
  }, [reload]);

  const statsByCode = useMemo(() => new Map(stats.map((item) => [item.promotion_code, item])), [stats]);
  const visible = filter === "ALL" ? items : items.filter((item) => item.status === filter);

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setMessage(done);
      await reload();
      return true;
    } catch (err) {
      setError(errorText(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    const { promotion_id: id, ...input } = draft;
    const ok = await run(() => (id ? updatePromotion(id, input) : createPromotion(input)), id ? "Đã lưu ưu đãi." : "Đã tạo ưu đãi (Chưa kiểm).");
    if (ok) setDraft(null);
  }

  async function checkRules(rules: EligibilityRules) {
    try {
      const result = await validatePromotionRules(rules);
      setMessage(result.ok ? "Luật hợp lệ." : null);
      setError(result.ok ? null : `Luật chưa hợp lệ: ${result.errors.join("; ")}`);
    } catch (err) {
      setError(errorText(err));
    }
  }

  async function activate(item: AdminPromotion) {
    if (await run(() => activatePromotion(item.promotion_id), `Đã kích hoạt ${item.promotion_code}.`)) setNotify(item);
  }

  return (
    <section className="ops-panel promotion-manager" aria-label="Quản trị ưu đãi">
      <div className="ops-panel-heading">
        <div>
          <h2>Ưu đãi</h2>
          <p>Ưu đãi &ldquo;Chưa kiểm&rdquo; không bao giờ đến tay khách. Kích hoạt đòi luật hợp lệ và còn hạn.</p>
        </div>
        <div className="promotion-manager-actions">
          <select aria-label="Lọc trạng thái" onChange={(event) => setFilter(event.target.value as PromotionStatus | "ALL")} value={filter}>
            <option value="ALL">Tất cả</option>
            {(Object.keys(STATUS_BADGES) as PromotionStatus[]).map((status) => (
              <option key={status} value={status}>
                {STATUS_BADGES[status].label}
              </option>
            ))}
          </select>
          <button className="secondary-button" onClick={() => void reload()} type="button">
            <RefreshCw size={14} /> Làm mới
          </button>
          <button
            className="primary-button"
            onClick={() => setDraft({ promotion_type: "FIXED_DISCOUNT", eligibility_rules: {}, requires_advisor_approval: true, priority: 100 })}
            type="button"
          >
            <Plus size={15} /> Tạo ưu đãi
          </button>
        </div>
      </div>

      {message ? (
        <p className="inline-success" role="status">
          <CheckCircle2 size={15} /> {message}
        </p>
      ) : null}
      {error ? (
        <p className="inline-warning" role="alert">
          {error}
        </p>
      ) : null}

      <div className="chat-table-wrap">
        <table className="chat-table">
          <thead>
            <tr>
              <th>Mã / tên</th>
              <th>Loại</th>
              <th>Trạng thái</th>
              <th>Luật</th>
              <th>Suất</th>
              <th>Hiệu quả</th>
              <th>
                <span className="sr-only">Hành động</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {visible.map((item) => {
              const badge = STATUS_BADGES[item.status];
              const stat = statsByCode.get(item.promotion_code);
              return (
                <tr key={item.promotion_id}>
                  <td data-label="Mã / tên">
                    <strong className="mono-text">{item.promotion_code}</strong>
                    <small>{item.title}</small>
                  </td>
                  <td data-label="Loại">{PROMOTION_TYPE_LABELS[item.promotion_type as PromotionTypeCode] ?? item.promotion_type}</td>
                  <td data-label="Trạng thái">
                    <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>
                  </td>
                  <td data-label="Luật">
                    {item.rules_valid ? (
                      <small>{Object.keys(item.eligibility_rules ?? {}).length ? "Có điều kiện" : "Không điều kiện"}</small>
                    ) : (
                      <StatusBadge tone="warning">Cần dựng luật</StatusBadge>
                    )}
                  </td>
                  <td data-label="Suất">
                    {item.used_count}
                    {item.max_uses ? ` / ${item.max_uses}` : ""}
                  </td>
                  <td data-label="Hiệu quả">
                    {stat ? (
                      <small>
                        Gửi {stat.sent ?? 0} · Chốt {stat.converted ?? 0} ({Math.round(stat.conversion_rate * 100)}%)
                      </small>
                    ) : (
                      <small>—</small>
                    )}
                  </td>
                  <td>
                    <div className="chat-row-actions">
                      <button
                        className="text-button"
                        onClick={() =>
                          setDraft({
                            promotion_id: item.promotion_id,
                            title: item.title,
                            description: item.description,
                            promotion_type: item.promotion_type,
                            discount_amount_vnd: item.discount_amount_vnd,
                            discount_percent: item.discount_percent,
                            eligibility_rules: item.eligibility_rules,
                            valid_from: item.valid_from,
                            valid_to: item.valid_to,
                            stackable: item.stackable,
                            priority: item.priority,
                            max_uses: item.max_uses,
                            requires_advisor_approval: item.requires_advisor_approval,
                            advisor_max_discount_vnd: item.advisor_max_discount_vnd,
                          })
                        }
                        type="button"
                      >
                        <Pencil size={13} /> Sửa
                      </button>
                      {item.status !== "ACTIVE" && item.status !== "CANCELLED" ? (
                        <button className="text-button" disabled={busy || !item.rules_valid} onClick={() => void activate(item)} type="button">
                          <Power size={13} /> Kích hoạt
                        </button>
                      ) : null}
                      {item.status !== "CANCELLED" ? (
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() => void run(() => cancelPromotion(item.promotion_id), `Đã huỷ ${item.promotion_code}.`)}
                          type="button"
                        >
                          <XCircle size={13} /> Huỷ
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              );
            })}
            {visible.length === 0 ? (
              <tr>
                <td colSpan={7}>Chưa có ưu đãi nào.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {draft ? (
        <div className="dialog-layer" role="dialog" aria-modal="true" aria-labelledby="promotion-dialog-title">
          <button aria-label="Đóng" className="dialog-backdrop" onClick={() => setDraft(null)} type="button" />
          <section className="mock-dialog promotion-dialog">
            <div className="dialog-heading">
              <h2 id="promotion-dialog-title">{draft.promotion_id ? "Sửa ưu đãi" : "Tạo ưu đãi"}</h2>
              <button aria-label="Đóng" className="icon-button" onClick={() => setDraft(null)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="promotion-form">
              {!draft.promotion_id ? (
                <label className="field-label">
                  Mã ưu đãi
                  <input onChange={(event) => setDraft({ ...draft, promotion_code: event.target.value })} value={draft.promotion_code ?? ""} />
                </label>
              ) : null}
              <label className="field-label">
                Tên
                <input onChange={(event) => setDraft({ ...draft, title: event.target.value })} value={draft.title ?? ""} />
              </label>
              <label className="field-label">
                Loại
                <select onChange={(event) => setDraft({ ...draft, promotion_type: event.target.value as PromotionTypeCode })} value={draft.promotion_type}>
                  {Object.entries(PROMOTION_TYPE_LABELS).map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                Giảm (VND)
                <input
                  min={0}
                  onChange={(event) => setDraft({ ...draft, discount_amount_vnd: event.target.value ? Number(event.target.value) : null })}
                  type="number"
                  value={draft.discount_amount_vnd ?? ""}
                />
              </label>
              <label className="field-label">
                Từ ngày
                <input onChange={(event) => setDraft({ ...draft, valid_from: event.target.value })} type="date" value={toDateInput(draft.valid_from)} />
              </label>
              <label className="field-label">
                Đến ngày
                <input
                  onChange={(event) => setDraft({ ...draft, valid_to: event.target.value || null })}
                  type="date"
                  value={toDateInput(draft.valid_to)}
                />
              </label>
              <label className="field-label">
                Ưu tiên (nhỏ = trước)
                <input onChange={(event) => setDraft({ ...draft, priority: Number(event.target.value) })} type="number" value={draft.priority ?? 100} />
              </label>
              <label className="field-label">
                Số suất tối đa
                <input
                  min={1}
                  onChange={(event) => setDraft({ ...draft, max_uses: event.target.value ? Number(event.target.value) : null })}
                  type="number"
                  value={draft.max_uses ?? ""}
                />
              </label>
              <label className="field-label">
                Ngưỡng TVV tự duyệt (VND)
                <input
                  min={0}
                  onChange={(event) => setDraft({ ...draft, advisor_max_discount_vnd: event.target.value ? Number(event.target.value) : null })}
                  placeholder="Trống = mọi mức có tiền cần quản lý duyệt"
                  type="number"
                  value={draft.advisor_max_discount_vnd ?? ""}
                />
              </label>
              <label className="checkbox-label">
                <input checked={draft.stackable ?? false} onChange={(event) => setDraft({ ...draft, stackable: event.target.checked })} type="checkbox" />
                Cộng dồn với ưu đãi khác
              </label>
              <label className="checkbox-label">
                <input
                  checked={draft.requires_advisor_approval ?? true}
                  onChange={(event) => setDraft({ ...draft, requires_advisor_approval: event.target.checked })}
                  type="checkbox"
                />
                TVV phải duyệt trước khi gửi
              </label>
            </div>
            <fieldset className="promotion-rules">
              <legend>Điều kiện áp dụng</legend>
              <EligibilityRuleBuilder
                fieldTypes={fieldTypes}
                onChange={(rules) => setDraft({ ...draft, eligibility_rules: rules })}
                value={draft.eligibility_rules ?? {}}
              />
              <button className="secondary-button" onClick={() => void checkRules(draft.eligibility_rules ?? {})} type="button">
                Kiểm tra luật
              </button>
            </fieldset>
            <div className="dialog-actions">
              <button className="secondary-button" onClick={() => setDraft(null)} type="button">
                Huỷ
              </button>
              <button className="primary-button" disabled={busy} onClick={() => void save()} type="button">
                Lưu
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {notify ? (
        <div className="inline-success promotion-notify" role="status">
          Tạo thông báo nội bộ cho tư vấn viên về ưu đãi <strong>{notify.promotion_code}</strong>?
          <button
            className="text-button"
            onClick={() =>
              void run(
                () => publishPromotionNotice(`Ưu đãi mới: ${notify.title}`, `Ưu đãi ${notify.promotion_code} đã được kích hoạt.`),
                "Đã gửi thông báo cho tư vấn viên.",
              ).then(() => setNotify(null))
            }
            type="button"
          >
            Tạo thông báo
          </button>
          <button className="text-button" onClick={() => setNotify(null)} type="button">
            Bỏ qua
          </button>
        </div>
      ) : null}
    </section>
  );
}
