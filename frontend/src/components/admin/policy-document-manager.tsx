"use client";

import { AlertTriangle, CheckCircle2, FileText, Loader2, Send, Sparkles, Upload } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { StatusBadge } from "@/components/shared/status-badge";
import {
  analyzePolicyDocument,
  listDocuments,
  PolicyNotificationApiError,
  type PolicyNotificationDraft,
  publishPolicyNotification,
  type StoredDocument,
  updatePolicyNotification,
  uploadPolicyDocument,
} from "@/lib/api/policy-notifications";

const policyLabels: Record<string, string> = {
  battery_policy: "Chính sách pin",
  warranty_policy: "Chính sách bảo hành",
  price_policy: "Chính sách giá",
  promotion_policy: "Chính sách ưu đãi",
  other_policy: "Chính sách khác",
  unknown: "Chưa xác định",
};

const topicLabels: Record<string, string> = {
  battery_rental: "Thuê pin",
  battery_purchase: "Mua pin",
  battery_usage: "Sử dụng pin",
  battery_replacement: "Thay thế pin",
  vehicle_warranty: "Bảo hành xe",
  battery_warranty: "Bảo hành pin",
  spare_part_warranty: "Bảo hành phụ tùng",
  vehicle_price: "Giá xe",
  promotion: "Ưu đãi",
  other: "Khác",
  unknown: "Chưa xác định",
};

function safeMessage(error: unknown): string {
  if (error instanceof PolicyNotificationApiError) return error.message;
  return "Không thể kết nối dịch vụ tài liệu. Vui lòng thử lại.";
}

export function PolicyDocumentManager() {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [analysis, setAnalysis] = useState<PolicyNotificationDraft | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [scopeDrafts, setScopeDrafts] = useState<NonNullable<PolicyNotificationDraft["scopes"]>>([]);
  const [conflictResolution, setConflictResolution] = useState<
    "" | "COEXIST_BY_COHORT" | "SUPERSEDE_DEFAULT"
  >("");
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      setLoading(true);
      setDocuments(await listDocuments());
      setError(null);
    } catch (requestError) {
      setError(safeMessage(requestError));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const loadTimer = window.setTimeout(() => {
      void loadDocuments();
    }, 0);
    return () => window.clearTimeout(loadTimer);
  }, [loadDocuments]);

  async function handleUpload(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const file = formData.get("file");
    const uploadTitle = String(formData.get("title") ?? "").trim();
    const sourceUrl = String(formData.get("source_url") ?? "").trim();
    if (!(file instanceof File) || file.size === 0 || !uploadTitle || !sourceUrl) return;
    try {
      setBusyId("upload");
      setError(null);
      await uploadPolicyDocument({
        title: uploadTitle,
        description: String(formData.get("description") ?? "").trim(),
        sourceUrl,
        sourceAuthority: "OFFICIAL",
        sourceRevision: String(formData.get("source_revision") ?? "").trim(),
        file,
      });
      form.reset();
      await loadDocuments();
    } catch (requestError) {
      setError(safeMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  async function handleAnalyze(documentId: string): Promise<void> {
    try {
      setBusyId(documentId);
      setError(null);
      const result = await analyzePolicyDocument(documentId);
      setAnalysis(result);
      setTitle(result.title);
      setContent(result.content);
      setScopeDrafts(result.scopes ?? []);
      setConflictResolution("");
    } catch (requestError) {
      setError(safeMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  async function handleSave(): Promise<void> {
    if (!analysis) return;
    try {
      setBusyId("save");
      setError(null);
      const result = scopeDrafts.length
        ? await updatePolicyNotification(analysis.id, title, content, scopeDrafts)
        : await updatePolicyNotification(analysis.id, title, content);
      setAnalysis(result);
      setTitle(result.title);
      setContent(result.content);
      setScopeDrafts(result.scopes ?? []);
    } catch (requestError) {
      setError(safeMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  async function handlePublish(): Promise<void> {
    if (!analysis) return;
    try {
      setBusyId("publish");
      setError(null);
      const saved = scopeDrafts.length
        ? await updatePolicyNotification(analysis.id, title, content, scopeDrafts)
        : await updatePolicyNotification(analysis.id, title, content);
      const published = conflictResolution
        ? await publishPolicyNotification(saved.id, conflictResolution)
        : await publishPolicyNotification(saved.id);
      setAnalysis(published);
      setTitle(published.title);
      setContent(published.content);
      setScopeDrafts(published.scopes ?? []);
    } catch (requestError) {
      setError(safeMessage(requestError));
    } finally {
      setBusyId(null);
    }
  }

  const immutable = analysis?.status === "published";
  const corpusReady = Boolean(
    analysis &&
      analysis.corpus_chunk_count > 0 &&
      (analysis.corpus_state === "DRAFT" || analysis.corpus_state === "ACTIVE") &&
      analysis.corpus_validation_errors.length === 0,
  );

  return (
    <div className="policy-admin-grid">
      <section className="ops-panel policy-document-panel">
        <div className="ops-panel-heading">
          <div>
            <h2>Tài liệu chính sách</h2>
            <p>PDF có text, DOCX hoặc TXT; file scan chưa hỗ trợ OCR.</p>
          </div>
        </div>

        <form className="policy-upload-form" onSubmit={handleUpload}>
          <label>
            <span>Tiêu đề tài liệu</span>
            <input name="title" required placeholder="Ví dụ: Chính sách bảo hành pin VF7" />
          </label>
          <label>
            <span>Mô tả</span>
            <input name="description" placeholder="Nguồn và phạm vi áp dụng" />
          </label>
          <label>
            <span>Nguồn chính thức</span>
            <input
              name="source_url"
              required
              type="url"
              placeholder="https://vinfastauto.com/..."
            />
          </label>
          <label>
            <span>Phiên bản nguồn (nếu có)</span>
            <input name="source_revision" placeholder="Ví dụ: 2.2 hoặc 2025-08-16" />
          </label>
          <label className="policy-file-input">
            <span>File chính sách</span>
            <input name="file" required type="file" accept=".pdf,.docx,.txt,.html,.htm" />
          </label>
          <button className="secondary-button" disabled={busyId === "upload"} type="submit">
            {busyId === "upload" ? <Loader2 className="spin" size={16} /> : <Upload size={16} />}
            Tải tài liệu
          </button>
        </form>

        {error ? <div className="policy-error"><AlertTriangle size={17} />{error}</div> : null}

        {loading ? (
          <div className="ops-state"><Loader2 className="spin" size={20} /> Đang tải tài liệu...</div>
        ) : (
          <div className="policy-document-list">
            {documents.map((document) => (
              <article key={document.id}>
                <FileText size={21} />
                <div>
                  <strong>{document.title}</strong>
                  <small>{document.original_filename ?? "Tài liệu"} · {document.content_type ?? "Không rõ loại"}</small>
                  <small>{document.source_authority ?? "UNKNOWN"} · {document.source_revision ?? "chưa gắn phiên bản"}</small>
                  {document.content_hash ? <small>SHA-256: {document.content_hash.slice(0, 12)}…</small> : null}
                  {document.source_retrieved_at ? (
                    <small>Lấy nguồn: {new Date(document.source_retrieved_at).toLocaleString("vi-VN")}</small>
                  ) : null}
                  {document.supersedes_document_id ? (
                    <small>
                      Thay thế bản {documents.find((item) => item.id === document.supersedes_document_id)?.source_revision
                        ?? document.supersedes_document_id.slice(0, 8)}
                    </small>
                  ) : null}
                  {document.source_url ? (
                    <a href={document.source_url} rel="noreferrer" target="_blank">Mở nguồn gốc</a>
                  ) : null}
                </div>
                <button
                  className="primary-button"
                  disabled={busyId === document.id}
                  onClick={() => void handleAnalyze(document.id)}
                  type="button"
                >
                  {busyId === document.id ? <Loader2 className="spin" size={15} /> : <Sparkles size={15} />}
                  Analyze policy
                </button>
              </article>
            ))}
            {documents.length === 0 ? <p className="policy-empty">Chưa có tài liệu đang hoạt động.</p> : null}
          </div>
        )}
      </section>

      {analysis ? (
        <section className="ops-panel policy-analysis-panel">
          <div className="ops-panel-heading">
            <div>
              <span className="eyebrow">AI Policy Analysis</span>
              <h2>Bản nháp chờ Admin duyệt</h2>
            </div>
            <StatusBadge tone={immutable ? "success" : "warning"}>
              {immutable ? "Published" : "Draft"}
            </StatusBadge>
          </div>

          {analysis.ai_confidence < 0.8 ? (
            <div className="policy-warning">
              <AlertTriangle size={17} /> AI không chắc chắn, vui lòng kiểm tra loại chính sách và nội dung trước khi đăng.
            </div>
          ) : null}

          <dl className="policy-analysis-meta">
            <div><dt>Policy type</dt><dd>{policyLabels[analysis.policy_type] ?? analysis.policy_type}</dd></div>
            <div><dt>Topic</dt><dd>{topicLabels[analysis.topic] ?? analysis.topic}</dd></div>
            <div><dt>Xe ảnh hưởng</dt><dd>{analysis.affected_models.join(", ") || "Không xác định"}</dd></div>
            <div><dt>Hiệu lực</dt><dd>{analysis.effective_from ?? "Không xác định"}</dd></div>
            <div><dt>Confidence</dt><dd>{Math.round(analysis.ai_confidence * 100)}%</dd></div>
            <div>
              <dt>RAG corpus</dt>
              <dd>{analysis.corpus_state} · {analysis.corpus_chunk_count} chunks</dd>
            </div>
          </dl>

          <div className="policy-analysis-section" aria-label="Phạm vi RAG đã xác thực">
            <h3>Xe đã đối chiếu chính xác</h3>
            {analysis.resolved_vehicles.length > 0 ? (
              analysis.resolved_vehicles.map((vehicle) => (
                <article key={vehicle.vehicle_id}>
                  <strong>{vehicle.display_name}</strong>
                  <span>{vehicle.slug}</span>
                </article>
              ))
            ) : (
              <p>Chưa có mẫu xe nào được đối chiếu để tạo evidence.</p>
            )}
            {analysis.corpus_validation_errors.map((message) => (
              <div className="policy-warning" key={message}>
                <AlertTriangle size={17} /> {message}
              </div>
            ))}
          </div>

          <div className="policy-analysis-section" aria-label="Phạm vi chính sách có cấu trúc">
            <h3>Phạm vi và phiên bản áp dụng</h3>
            {scopeDrafts.map((scope, scopeIndex) => (
              <article key={scope.scope_id}>
                <strong>{topicLabels[scope.topic] ?? scope.topic}</strong>
                <span>{scope.vehicle_type} · {scope.component} · {scope.usage_type}</span>
                <small>
                  {scope.battery_chemistry ?? "không phụ thuộc loại pin"} · {scope.ownership_model ?? "không phụ thuộc sở hữu"}
                </small>
                <small>
                  {scope.eligibility_basis}: {scope.eligibility_from ?? "đầu kỳ"} → {scope.eligibility_to ?? "không giới hạn"}
                </small>
                <label>
                  <span>Mốc xác định cohort</span>
                  <select
                    disabled={immutable}
                    value={scope.eligibility_basis}
                    onChange={(event) => setScopeDrafts((items) => items.map((item, index) => (
                      index === scopeIndex ? { ...item, eligibility_basis: event.target.value } : item
                    )))}
                  >
                    <option value="NONE">Không phụ thuộc ngày</option>
                    <option value="INVOICE_DATE">Ngày hóa đơn</option>
                    <option value="WARRANTY_ACTIVATION_DATE">Ngày kích hoạt bảo hành</option>
                    <option value="CONTRACT_ACTIVATION_DATE">Ngày kích hoạt hợp đồng</option>
                    <option value="PURCHASE_DATE">Ngày mua</option>
                  </select>
                </label>
                <label>
                  <span>Từ ngày</span>
                  <input
                    disabled={immutable}
                    type="date"
                    value={scope.eligibility_from ?? ""}
                    onChange={(event) => setScopeDrafts((items) => items.map((item, index) => (
                      index === scopeIndex ? { ...item, eligibility_from: event.target.value || null } : item
                    )))}
                  />
                </label>
                <label>
                  <span>Đến ngày</span>
                  <input
                    disabled={immutable}
                    type="date"
                    value={scope.eligibility_to ?? ""}
                    onChange={(event) => setScopeDrafts((items) => items.map((item, index) => (
                      index === scopeIndex ? { ...item, eligibility_to: event.target.value || null } : item
                    )))}
                  />
                </label>
                <label>
                  <input
                    checked={scope.is_current_default}
                    disabled={immutable}
                    type="checkbox"
                    onChange={(event) => setScopeDrafts((items) => items.map((item, index) => (
                      index === scopeIndex ? { ...item, is_current_default: event.target.checked } : item
                    )))}
                  />
                  <span>Dùng làm chính sách mặc định hiện tại</span>
                </label>
              </article>
            ))}
          </div>

          <div className="policy-analysis-section">
            <h3>Extracted facts</h3>
            {analysis.facts.map((fact) => (
              <article key={`${fact.label}-${fact.value}`}>
                <strong>{fact.label}</strong><span>{fact.value}</span><small>“{fact.evidence}”</small>
              </article>
            ))}
          </div>

          <div className="policy-analysis-section">
            <h3>Evidence</h3>
            {analysis.evidence.map((item, index) => (
              <blockquote key={`${item.section ?? "source"}-${index}`}>
                {item.section ? <strong>§ {item.section}</strong> : null} “{item.quote}”
              </blockquote>
            ))}
          </div>

          <label className="field-label">
            Tiêu đề thông báo
            <input disabled={immutable} onChange={(event) => setTitle(event.target.value)} value={title} />
          </label>
          <label className="field-label">
            Nội dung thông báo
            <textarea disabled={immutable} onChange={(event) => setContent(event.target.value)} rows={6} value={content} />
          </label>

          <label className="field-label">
            Xử lý khi trùng phiên bản đang áp dụng
            <select
              aria-label="Xử lý xung đột phiên bản"
              disabled={immutable}
              onChange={(event) => setConflictResolution(
                event.target.value as "" | "COEXIST_BY_COHORT" | "SUPERSEDE_DEFAULT"
              )}
              value={conflictResolution}
            >
              <option value="">Dừng và báo lỗi để kiểm tra</option>
              <option value="COEXIST_BY_COHORT">Cùng tồn tại vì cohort không giao nhau</option>
              <option value="SUPERSEDE_DEFAULT">Thay mặc định, giữ bản cũ cho cohort cũ</option>
            </select>
          </label>

          <div className="policy-actions">
            {immutable ? <span className="policy-published-note"><CheckCircle2 size={17} /> Đã công bố cho khách hàng</span> : null}
            <button className="secondary-button" disabled={immutable || busyId === "save"} onClick={() => void handleSave()} type="button">
              {busyId === "save" ? <Loader2 className="spin" size={16} /> : null} Lưu bản nháp
            </button>
            <button className="primary-button" disabled={immutable || !corpusReady || busyId === "publish"} onClick={() => void handlePublish()} type="button">
              {busyId === "publish" ? <Loader2 className="spin" size={16} /> : <Send size={16} />} Publish
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}
