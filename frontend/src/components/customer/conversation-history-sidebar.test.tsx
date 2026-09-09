// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConversationHistorySidebar } from "./conversation-history-sidebar";
import * as agentApi from "@/lib/api/agent";
import type { ConversationSummary } from "@/types/agent";

vi.mock("@/lib/api/agent", () => ({
  fetchConversations: vi.fn(),
  deleteConversation: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/consultation",
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

describe("ConversationHistorySidebar", () => {
  const onNewConversation = vi.fn();
  const onClose = vi.fn();

  const mockConversations: ConversationSummary[] = [
    {
      conversation_id: "c1111111-1111-1111-1111-111111111111",
      session_id: "s1111111-1111-1111-1111-111111111111",
      title: "Tư vấn VF 7",
      status: "ACTIVE",
      state: "ACTIVE",
      created_at: "2026-08-01T00:00:00Z",
      archived_at: null,
      assigned_advisor_id: null,
      last_activity_at: new Date().toISOString(),
    },
    {
      conversation_id: "c2222222-2222-2222-2222-222222222222",
      session_id: "s2222222-2222-2222-2222-222222222222",
      title: "Tìm trạm sạc Hà Nội",
      status: "ACTIVE",
      state: "ACTIVE",
      created_at: "2026-08-01T00:00:00Z",
      archived_at: null,
      assigned_advisor_id: null,
      last_activity_at: new Date().toISOString(),
    },
    {
      conversation_id: "c3333333-3333-3333-3333-333333333333",
      session_id: "s3333333-3333-3333-3333-333333333333",
      title: "So sánh VF 6 và VF 7",
      status: "ACTIVE",
      state: "ACTIVE",
      created_at: "2026-08-01T00:00:00Z",
      archived_at: null,
      assigned_advisor_id: "advisor@vinfast.vn",
      last_activity_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  beforeEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(agentApi.fetchConversations).mockResolvedValue({ items: mockConversations });
    vi.mocked(agentApi.deleteConversation).mockResolvedValue(undefined);
  });

  it("renders conversation list with group headers, 3-tier items, and short IDs", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    // Group headers
    expect(screen.getByText("HÔM NAY")).toBeInTheDocument();
    expect(screen.getByText("HÔM QUA")).toBeInTheDocument();

    // Short IDs
    expect(screen.getByText("#CV-C111")).toBeInTheDocument();
    expect(screen.getByText("#CV-C222")).toBeInTheDocument();
    expect(screen.getByText("#CV-C333")).toBeInTheDocument();

    // Advisor badge for c3
    expect(screen.getByText("Tư vấn viên")).toBeInTheDocument();

    // Active state
    const activeItem = screen.getByText("Tư vấn VF 7").closest(".conversation-history-item");
    expect(activeItem).toHaveClass("is-active");
  });

  it("filters conversation items when searching", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText("Tìm cuộc trò chuyện...");
    fireEvent.change(searchInput, { target: { value: "trạm sạc" } });

    await waitFor(() => {
      expect(screen.getByText("Tìm trạm sạc Hà Nội")).toBeInTheDocument();
      expect(screen.queryByText("Tư vấn VF 7")).not.toBeInTheDocument();
    });

    // Clear search
    const clearBtn = screen.getByLabelText("Xóa tìm kiếm");
    fireEvent.click(clearBtn);

    await waitFor(() => {
      expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument();
    });
  });

  it("shows empty search state when no match is found", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    const searchInput = screen.getByPlaceholderText("Tìm cuộc trò chuyện...");
    fireEvent.change(searchInput, { target: { value: "từ khóa không tồn tại xyz" } });

    await waitFor(() => {
      expect(screen.getByText("Không tìm thấy cuộc trò chuyện nào phù hợp.")).toBeInTheDocument();
    });

    const resetBtn = screen.getByText("Xóa tìm kiếm");
    fireEvent.click(resetBtn);

    await waitFor(() => {
      expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument();
    });
  });

  it("triggers onNewConversation when clicking primary button", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    const newBtn = screen.getByRole("button", { name: /Bắt đầu cuộc trò chuyện mới/i });
    fireEvent.click(newBtn);

    expect(onNewConversation).toHaveBeenCalled();
  });

  it("pins and unpins a conversation via context menu", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    // Open context menu for first item
    const moreBtn = screen.getByLabelText(/Tùy chọn cho Tư vấn VF 7/i);
    fireEvent.click(moreBtn);

    const pinBtn = await screen.findByRole("menuitem", { name: /Ghim/i });
    fireEvent.click(pinBtn);

    // After pinning, "ĐÃ GHIM" group header should appear
    await waitFor(() => {
      expect(screen.getByText("ĐÃ GHIM")).toBeInTheDocument();
    });
  });

  it("renames a conversation with the rename dialog", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    const moreBtn = screen.getByLabelText(/Tùy chọn cho Tư vấn VF 7/i);
    fireEvent.click(moreBtn);

    const renameMenuItem = await screen.findByRole("menuitem", { name: /Đổi tên/i });
    fireEvent.click(renameMenuItem);

    await waitFor(() => {
      expect(screen.getByText("Đổi tên cuộc trò chuyện")).toBeInTheDocument();
    });

    const renameInput = screen.getByPlaceholderText("Nhập tên cuộc trò chuyện...");
    fireEvent.change(renameInput, { target: { value: "Tư vấn VF 7 Plus màu Đỏ" } });

    const saveBtn = screen.getByRole("button", { name: "Lưu tên mới" });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(screen.getByText("Tư vấn VF 7 Plus màu Đỏ")).toBeInTheDocument();
    });
  });

  it("opens delete confirmation modal before deleting conversation", async () => {
    render(
      <ConversationHistorySidebar
        activeConversationId="c1111111-1111-1111-1111-111111111111"
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => expect(screen.getByText("Tư vấn VF 7")).toBeInTheDocument());

    const moreBtn = screen.getByLabelText(/Tùy chọn cho Tư vấn VF 7/i);
    fireEvent.click(moreBtn);

    const deleteMenuItem = await screen.findByRole("menuitem", { name: /Xóa/i });
    fireEvent.click(deleteMenuItem);

    // Modal dialog appears
    await waitFor(() => {
      expect(screen.getByText("Xóa cuộc trò chuyện này?")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/và toàn bộ lịch sử tin nhắn sẽ bị xóa vĩnh viễn và không thể khôi phục/i),
    ).toBeInTheDocument();

    // Confirm deletion
    const confirmDeleteBtn = screen.getByRole("button", { name: "Xác nhận xóa" });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(agentApi.deleteConversation).toHaveBeenCalledWith("c1111111-1111-1111-1111-111111111111");
    });
  });

  it("renders empty state when there are 0 conversations", async () => {
    vi.mocked(agentApi.fetchConversations).mockResolvedValue({ items: [] });

    render(
      <ConversationHistorySidebar
        activeConversationId=""
        onClose={onClose}
        onNewConversation={onNewConversation}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Chưa có cuộc trò chuyện")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Bắt đầu trò chuyện với VinFast AI để được tư vấn chọn xe, báo giá và chính sách."),
    ).toBeInTheDocument();
  });
});
