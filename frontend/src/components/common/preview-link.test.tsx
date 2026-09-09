// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PreviewLink } from "@/components/common/preview-link";

describe("PreviewLink", () => {
  beforeEach(() => {
    // DOM của test trước còn nằm lại (bộ test này không bật auto-cleanup), nên
    // `getByRole("link")` sẽ thấy nhiều thẻ và ném "Found multiple elements".
    cleanup();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it("chua re du lau thi KHONG nap trang nao", () => {
    // Lướt chuột ngang một đoạn có bảy liên kết mà nạp bảy trang là tự làm treo
    // máy khách. Độ trễ chính là thứ chặn việc đó.
    render(<PreviewLink href="/vehicles/vf-8">Xem thêm</PreviewLink>);

    fireEvent.mouseEnter(screen.getByRole("link"));
    vi.advanceTimersByTime(100);

    expect(document.querySelector("iframe")).toBeNull();
  });

  it("re du lau thi hien cua so xem truoc cua dung trang do", () => {
    render(<PreviewLink href="/vehicles/vf-8">Xem thêm</PreviewLink>);

    fireEvent.mouseEnter(screen.getByRole("link"));
    // `act` chứ không `waitFor`: `waitFor` chờ bằng đồng hồ THẬT, mà bộ test này
    // đang chạy đồng hồ giả — nó sẽ treo tới hết timeout rồi mới đỏ.
    act(() => void vi.advanceTimersByTime(400));

    const frame = document.querySelector("iframe");
    expect(frame).not.toBeNull();
    expect(frame).toHaveAttribute("src", "/vehicles/vf-8");
  });

  it("roi chuot thi GO HAN iframe, khong chi giau di", () => {
    // Một iframe an van chay script va giu bo nho.
    render(<PreviewLink href="/vehicles/vf-8">Xem thêm</PreviewLink>);
    const link = screen.getByRole("link");

    fireEvent.mouseEnter(link);
    act(() => void vi.advanceTimersByTime(400));
    expect(document.querySelector("iframe")).not.toBeNull();

    act(() => void fireEvent.mouseLeave(link));

    expect(document.querySelector("iframe")).toBeNull();
  });

  it("roi chuot truoc khi het gio thi khong nap gi", () => {
    render(<PreviewLink href="/vehicles/vf-8">Xem thêm</PreviewLink>);
    const link = screen.getByRole("link");

    fireEvent.mouseEnter(link);
    vi.advanceTimersByTime(200);
    fireEvent.mouseLeave(link);
    vi.advanceTimersByTime(1000);

    expect(document.querySelector("iframe")).toBeNull();
  });
});
