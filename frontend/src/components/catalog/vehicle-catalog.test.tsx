// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VehicleCatalog } from "@/components/catalog/vehicle-catalog";
import { localCatalogVehicles } from "@/data/product-experience";
import { DemoStoreProvider } from "@/store/demo-store";

vi.mock("next/link", () => ({
  default: ({ children, href, ...props }: React.ComponentProps<"a">) => (
    <a href={href} {...props}>{children}</a>
  ),
}));

vi.mock("next/image", () => ({
  // eslint-disable-next-line @next/next/no-img-element -- mock next/image trong test
  default: ({ fill: _fill, ...props }: React.ComponentProps<"img"> & { fill?: boolean }) => <img alt="" {...props} />,
}));

function renderCatalog() {
  return render(<DemoStoreProvider><VehicleCatalog initialFilter="car" /></DemoStoreProvider>);
}

describe("VehicleCatalog — hành động trên thẻ xe (Sếp 2026-08-29)", () => {
  beforeEach(() => cleanup());

  it("mỗi mẫu có đủ thông số nhanh, không chỉ giá và quãng đường", () => {
    for (const vehicle of localCatalogVehicles) {
      expect(vehicle.quickSpecs.length, vehicle.modelName).toBeGreaterThanOrEqual(3);
      expect(vehicle.quickSpecs.length).toBeLessThanOrEqual(8);
      expect(new Set(vehicle.quickSpecs.map((spec) => spec.label)).size).toBe(vehicle.quickSpecs.length);
    }
  });

  it("hộp thông số nhanh nối thẳng sang xem chi tiết và so sánh", () => {
    renderCatalog();
    const first = localCatalogVehicles.find((vehicle) => vehicle.vehicleType === "car");
    if (!first) throw new Error("catalog local không có ô tô");
    const card = document.getElementById(first.id);
    if (!card) throw new Error("không thấy thẻ xe");

    fireEvent.click(within(card).getByRole("button", { name: /thông số nhanh/i }));
    const dialog = screen.getByRole("dialog");
    for (const spec of first.quickSpecs) {
      expect(within(dialog).getByText(spec.label)).toBeInTheDocument();
    }
    expect(within(dialog).getByRole("link", { name: /xem chi tiết/i })).toHaveAttribute("href", first.href);

    const compare = within(dialog).getByRole("button", { name: /thêm so sánh/i });
    fireEvent.click(compare);
    expect(within(dialog).getByRole("button", { name: /đã chọn so sánh/i })).toHaveAttribute("aria-pressed", "true");
    // Trạng thái chọn so sánh đồng bộ ngược ra thẻ ngoài.
    expect(within(card).getByRole("button", { name: /đã chọn so sánh/i })).toBeInTheDocument();
  });

  it("không lộ chữ nội bộ 'Thông tin sản phẩm local' ra khách", () => {
    renderCatalog();
    expect(screen.queryByText(/thông tin sản phẩm local/i)).not.toBeInTheDocument();
  });

  it("thẻ xe: một nút chính 'Xem chi tiết', hai việc phụ là nút icon tròn có tên đọc được", () => {
    renderCatalog();
    const first = localCatalogVehicles.find((vehicle) => vehicle.vehicleType === "car");
    if (!first) throw new Error("catalog local không có ô tô");
    const card = document.getElementById(first.id);
    if (!card) throw new Error("không thấy thẻ xe");

    expect(within(card).getByRole("link", { name: /xem chi tiết/i })).toHaveClass("catalog-action-primary");
    const info = within(card).getByRole("button", { name: /thông số nhanh/i });
    const compare = within(card).getByRole("button", { name: /so sánh/i });
    expect(info).toHaveClass("catalog-action-icon");
    expect(compare).toHaveClass("catalog-action-icon");
    // Icon tròn không có chữ bên trong — tên nằm ở aria-label + title.
    expect(info).toHaveAttribute("title");
    expect(compare).toHaveAttribute("title");
    expect(info.textContent).toBe("");
  });

  it("thanh so sánh dính đáy CHỈ hiện khi đã chọn ≥1 xe, kèm link 'So sánh ngay'", () => {
    renderCatalog();
    // Chưa chọn xe nào: không có thanh nào nói về số xe đang chọn.
    expect(screen.queryByText(/đang được chọn để so sánh/i)).not.toBeInTheDocument();

    const first = localCatalogVehicles.find((vehicle) => vehicle.vehicleType === "car");
    if (!first) throw new Error("catalog local không có ô tô");
    const card = document.getElementById(first.id);
    if (!card) throw new Error("không thấy thẻ xe");
    fireEvent.click(within(card).getByRole("button", { name: /so sánh/i }));

    const tray = screen.getByText(/1 xe đang được chọn để so sánh/i).closest(".catalog-compare-tray");
    if (!tray) throw new Error("không thấy thanh so sánh");
    expect(within(tray as HTMLElement).getByRole("link", { name: /so sánh ngay/i })).toHaveAttribute("href", "/compare");
  });
});
