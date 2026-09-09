// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PolicyDocumentManager } from "@/components/admin/policy-document-manager";
import * as api from "@/lib/api/policy-notifications";

vi.mock("@/lib/api/policy-notifications", () => ({
  PolicyNotificationApiError: class PolicyNotificationApiError extends Error {},
  listDocuments: vi.fn(),
  uploadPolicyDocument: vi.fn(),
  analyzePolicyDocument: vi.fn(),
  updatePolicyNotification: vi.fn(),
  publishPolicyNotification: vi.fn(),
}));

const draft: api.PolicyNotificationDraft = {
  id: "notice-1",
  source_document_id: "document-1",
  policy_type: "warranty_policy",
  topic: "battery_warranty",
  secondary_topics: [],
  affected_models: ["VF7"],
  effective_from: "2026-09-01",
  effective_to: null,
  facts: [{ label: "Thời hạn", value: "8 năm", evidence: "Pin VF7 được bảo hành 8 năm." }],
  evidence: [{ section: "3.2", quote: "Pin VF7 được bảo hành 8 năm." }],
  ai_confidence: 0.96,
  title: "Bản nháp AI",
  content: "Nội dung AI",
  status: "draft",
  created_at: "2026-08-27T00:00:00Z",
  updated_at: "2026-08-27T00:00:00Z",
  published_at: null,
  corpus_state: "DRAFT",
  corpus_chunk_count: 2,
  resolved_vehicles: [
    {
      vehicle_id: "vehicle-7",
      slug: "vinfast-vf-7-all-new",
      display_name: "VF 7 All New",
    },
  ],
  corpus_validation_errors: [],
};

describe("PolicyDocumentManager", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.mocked(api.listDocuments).mockResolvedValue([
      {
        id: "document-1",
        title: "Chính sách bảo hành pin VF7",
        original_filename: "policy.pdf",
        content_type: "application/pdf",
        created_at: "2026-08-27T00:00:00Z",
      },
    ]);
    vi.mocked(api.analyzePolicyDocument).mockResolvedValue(draft);
    vi.mocked(api.updatePolicyNotification).mockImplementation(async (_id, title, content) => ({
      ...draft,
      title,
      content,
    }));
    vi.mocked(api.publishPolicyNotification).mockResolvedValue({ ...draft, status: "published" });
  });

  it("shows structured analysis and publishes the Admin-edited copy", async () => {
    render(<PolicyDocumentManager />);
    const analyzeButton = await screen.findByRole("button", { name: /Analyze policy/i });
    fireEvent.click(analyzeButton);

    expect(await screen.findByText("Chính sách bảo hành")).toBeInTheDocument();
    expect(screen.getByText("Bảo hành pin")).toBeInTheDocument();
    expect(screen.getByText("96%")).toBeInTheDocument();
    expect(screen.getByText("DRAFT · 2 chunks")).toBeInTheDocument();
    expect(screen.getByText("VF 7 All New")).toBeInTheDocument();
    expect(screen.getAllByText("Pin VF7 được bảo hành 8 năm.", { exact: false })).toHaveLength(2);

    fireEvent.change(screen.getByLabelText("Tiêu đề thông báo"), {
      target: { value: "Admin đã duyệt" },
    });
    fireEvent.change(screen.getByLabelText("Nội dung thông báo"), {
      target: { value: "Nội dung do Admin chỉnh sửa." },
    });
    fireEvent.click(screen.getByRole("button", { name: /Publish/i }));

    await waitFor(() =>
      expect(api.updatePolicyNotification).toHaveBeenCalledWith(
        "notice-1",
        "Admin đã duyệt",
        "Nội dung do Admin chỉnh sửa.",
      ),
    );
    expect(api.publishPolicyNotification).toHaveBeenCalledWith("notice-1");
    expect(await screen.findByText("Đã công bố cho khách hàng")).toBeInTheDocument();
  });

  it("passes an explicit Admin decision when superseding a current revision", async () => {
    render(<PolicyDocumentManager />);
    fireEvent.click(await screen.findByRole("button", { name: /Analyze policy/i }));
    await screen.findByText("Chính sách bảo hành");

    fireEvent.change(screen.getByLabelText("Xử lý xung đột phiên bản"), {
      target: { value: "SUPERSEDE_DEFAULT" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Publish/i }));

    await waitFor(() =>
      expect(api.publishPolicyNotification).toHaveBeenCalledWith(
        "notice-1",
        "SUPERSEDE_DEFAULT",
      ),
    );
  });
});
