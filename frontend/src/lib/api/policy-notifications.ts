import { csrfHeader, withSessionRetry } from "@/lib/api/session";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  (typeof window !== "undefined" ? "/api/v1" : "http://localhost:8000/api/v1");

export class PolicyNotificationApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "PolicyNotificationApiError";
  }
}

export interface StoredDocument {
  id: string;
  title: string;
  description?: string | null;
  document_type?: string | null;
  source_url?: string | null;
  source_authority?: "OFFICIAL" | "INTERNAL_APPROVED" | "UNKNOWN";
  source_revision?: string | null;
  source_published_at?: string | null;
  source_retrieved_at?: string | null;
  content_hash?: string;
  supersedes_document_id?: string | null;
  original_filename?: string | null;
  content_type?: string | null;
  byte_size?: number | null;
  created_at: string;
}

export interface PolicyFact {
  label: string;
  value: string;
  evidence: string;
}

export interface PolicyEvidence {
  section?: string | null;
  quote: string;
}

export interface PolicyNotificationDraft {
  id: string;
  source_document_id: string;
  policy_type: string;
  topic: string;
  secondary_topics: string[];
  affected_models: string[];
  effective_from?: string | null;
  effective_to?: string | null;
  facts: PolicyFact[];
  evidence: PolicyEvidence[];
  ai_confidence: number;
  title: string;
  content: string;
  status: "draft" | "published";
  created_at: string;
  updated_at: string;
  published_at?: string | null;
  corpus_state: "NOT_BUILT" | "DRAFT" | "ACTIVE" | "ERROR";
  corpus_chunk_count: number;
  resolved_vehicles: Array<{
    vehicle_id: string;
    slug: string;
    display_name: string;
  }>;
  corpus_validation_errors: string[];
  scopes?: Array<{
    scope_id: string;
    policy_type: string;
    topic: string;
    vehicle_type: string;
    component: string;
    battery_chemistry?: string | null;
    ownership_model?: string | null;
    usage_type: string;
    policy_active_from?: string | null;
    policy_active_to?: string | null;
    eligibility_basis: string;
    eligibility_from?: string | null;
    eligibility_to?: string | null;
    is_current_default: boolean;
    affected_models: string[];
    resolved_vehicle_ids: string[];
    evidence_quotes: string[];
    status: "DRAFT" | "ACTIVE" | "ARCHIVED";
  }>;
}

export interface PublishedPolicyNotification {
  id: string;
  title: string;
  content: string;
  affected_models: string[];
  effective_from?: string | null;
  effective_to?: string | null;
  published_at: string;
  source_document_id?: string | null;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const attempt = () =>
    fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: {
        "Cache-Control": "no-store",
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...init.headers,
        ...csrfHeader(),
      },
    });
  const response = await withSessionRetry(attempt);
  const body = await response.json().catch(() => ({}) as Record<string, unknown>);
  if (!response.ok) {
    const detail = (body as { detail?: unknown }).detail;
    const structuredMessage =
      typeof detail === "object" && detail !== null && "message" in detail
        ? (detail as { message?: unknown }).message
        : undefined;
    throw new PolicyNotificationApiError(
      response.status,
      typeof detail === "string"
        ? detail
        : typeof structuredMessage === "string"
          ? structuredMessage
          : "Không thể xử lý yêu cầu.",
    );
  }
  return body as T;
}

export async function listDocuments(): Promise<StoredDocument[]> {
  const page = await request<{ items: StoredDocument[] }>("/documents?page=1&page_size=100");
  return page.items;
}

export function uploadPolicyDocument(payload: {
  title: string;
  description?: string;
  sourceUrl: string;
  sourceAuthority?: "OFFICIAL" | "INTERNAL_APPROVED";
  sourceRevision?: string;
  file: File;
}): Promise<StoredDocument> {
  const body = new FormData();
  body.set("title", payload.title);
  body.set("document_type", "policy");
  body.set("source_url", payload.sourceUrl);
  body.set("source_authority", payload.sourceAuthority ?? "OFFICIAL");
  if (payload.sourceRevision) body.set("source_revision", payload.sourceRevision);
  if (payload.description) body.set("description", payload.description);
  body.set("file", payload.file);
  return request<StoredDocument>("/documents", { method: "POST", body });
}

export function analyzePolicyDocument(documentId: string): Promise<PolicyNotificationDraft> {
  return request<PolicyNotificationDraft>(`/documents/${encodeURIComponent(documentId)}/analyze-policy`, {
    method: "POST",
  });
}

export function updatePolicyNotification(
  notificationId: string,
  title: string,
  content: string,
  scopes?: PolicyNotificationDraft["scopes"],
): Promise<PolicyNotificationDraft> {
  const applicability = scopes?.map((scope) => ({
    scope_id: scope.scope_id,
    ownership_model: scope.ownership_model ?? null,
    usage_type: scope.usage_type,
    policy_active_from: scope.policy_active_from ?? null,
    policy_active_to: scope.policy_active_to ?? null,
    eligibility_basis: scope.eligibility_basis,
    eligibility_from: scope.eligibility_from ?? null,
    eligibility_to: scope.eligibility_to ?? null,
    is_current_default: scope.is_current_default,
  }));
  return request<PolicyNotificationDraft>(`/policy-notifications/${encodeURIComponent(notificationId)}`, {
    method: "PATCH",
    body: JSON.stringify({ title, content, ...(applicability ? { scopes: applicability } : {}) }),
  });
}

export function publishPolicyNotification(
  notificationId: string,
  resolution?: "COEXIST_BY_COHORT" | "SUPERSEDE_DEFAULT" | "CANCEL",
): Promise<PolicyNotificationDraft> {
  return request<PolicyNotificationDraft>(
    `/policy-notifications/${encodeURIComponent(notificationId)}/publish`,
    { method: "POST", ...(resolution ? { body: JSON.stringify({ resolution }) } : {}) },
  );
}

export async function listPublishedPolicyNotifications(): Promise<PublishedPolicyNotification[]> {
  const page = await request<{ items: PublishedPolicyNotification[] }>("/notifications?page=1&page_size=100");
  return page.items;
}

export async function getDocumentDownloadUrl(documentId: string): Promise<string> {
  const response = await request<{ url: string }>(`/documents/${encodeURIComponent(documentId)}/download`);
  return response.url;
}

