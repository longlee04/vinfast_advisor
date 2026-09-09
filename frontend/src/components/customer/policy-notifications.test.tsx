// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PolicyNotifications } from "@/components/customer/policy-notifications";
import * as api from "@/lib/api/policy-notifications";

vi.mock("@/lib/api/policy-notifications", () => ({
  listPublishedPolicyNotifications: vi.fn(),
  getDocumentDownloadUrl: vi.fn(),
}));

describe("PolicyNotifications", () => {
  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders only the published Admin-approved customer copy and opens detail modal on click", async () => {
    vi.mocked(api.listPublishedPolicyNotifications).mockResolvedValue([
      {
        id: "notice-1",
        title: "Admin đã duyệt",
        content: "VF7 được bảo hành pin 8 năm.",
        affected_models: ["VF7"],
        effective_from: "2026-09-01",
        effective_to: null,
        published_at: "2026-08-27T00:00:00Z",
        source_document_id: "doc-123",
      },
    ]);
    vi.mocked(api.getDocumentDownloadUrl).mockResolvedValue("https://minio.vinfast.vn/documents/doc-123.pdf");

    render(<PolicyNotifications />);

    expect(await screen.findByText("Admin đã duyệt")).toBeInTheDocument();
    expect(screen.getByText("VF7 được bảo hành pin 8 năm.")).toBeInTheDocument();
    expect(screen.getByText("Áp dụng: VF7")).toBeInTheDocument();
    expect(screen.queryByText(/confidence/i)).not.toBeInTheDocument();

    // Click card to open modal
    const card = screen.getByRole("button", { name: /Xem chi tiết chính sách: Admin đã duyệt/i });
    fireEvent.click(card);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Chính sách chính thức")).toBeInTheDocument();
    expect(screen.getByText("Hỏi Trợ lý AI về chính sách này")).toBeInTheDocument();
    expect(screen.getByText(/Xem \/ Tải tài liệu gốc do Admin tải lên/i)).toBeInTheDocument();

    // Close modal
    const closeBtn = screen.getByLabelText("Đóng");
    fireEvent.click(closeBtn);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

