import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { VehicleComparison } from "@/components/comparison/vehicle-comparison";
import { DemoStoreProvider } from "@/store/demo-store";

const { fetchVehicles } = vi.hoisted(() => ({ fetchVehicles: vi.fn() }));

vi.mock("@/lib/api/vehicles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/vehicles")>();
  return { ...actual, fetchVehicles };
});

vi.mock("next/image", () => ({
  default: ({ alt, onError, src }: { alt: string; onError?: () => void; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} onError={onError} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: React.ComponentProps<"a">) => <a href={href}>{children}</a>,
}));

const amio = {
  id: "amio-standard",
  slug: "vinfast-amio",
  modelName: "Amio",
  variant: "Standard",
  vehicleType: "electric_motorbike" as const,
  priceVnd: 12_000_000,
  priceType: "BATTERY_INCLUDED",
  rangeKm: 65,
  seats: null,
  chargeMinutes: 360,
  batteryCapacityKwh: 1.024,
  imageUrl: "https://catalog.example/amio-low-resolution.jpg",
  detailUrl: null,
};

const amioS = {
  ...amio,
  id: "amio-s",
  slug: "vinfast-amio-s-s",
  variant: "S",
  rangeKm: 30,
  imageUrl: null,
};

describe("VehicleComparison", () => {
  beforeEach(() => fetchVehicles.mockReset());

  it("hiển thị ảnh menu chất lượng cao cho từng xe mà không dùng ô chữ V", async () => {
    fetchVehicles.mockResolvedValue([amio, amioS]);
    const user = userEvent.setup();

    render(
      <DemoStoreProvider>
        <VehicleComparison />
      </DemoStoreProvider>,
    );

    await user.click(await screen.findByRole("button", { name: "Amio Standard" }));
    await user.click(screen.getByRole("button", { name: "Amio S" }));

    const images = screen.getAllByRole("img", { name: /ảnh xe amio/i });
    expect(images).toHaveLength(2);
    expect(images[0]).toHaveAttribute("data-image-src", "/vehicles/motorbikes/amio.webp");
    expect(images[1]).toHaveAttribute("data-image-src", "/vehicles/motorbikes/amio-s.webp");
    expect(screen.queryByText("V")).not.toBeInTheDocument();
  });

  it("hiển thị fallback gọn khi nguồn ảnh không tải được", async () => {
    fetchVehicles.mockResolvedValue([amio, amioS]);
    const user = userEvent.setup();

    render(
      <DemoStoreProvider>
        <VehicleComparison />
      </DemoStoreProvider>,
    );

    await user.click(await screen.findByRole("button", { name: "Amio Standard" }));
    await user.click(screen.getByRole("button", { name: "Amio S" }));
    fireEvent.error(screen.getAllByRole("img", { name: /ảnh xe amio/i })[0]);

    await waitFor(() => {
      expect(screen.getByLabelText("Chưa tải được ảnh xe Amio")).toBeInTheDocument();
    });
  });

  it("picker tách tab loại xe, thẻ xe có ảnh, bấm lại thì bỏ khỏi so sánh (Sếp 2026-08-31)", async () => {
    fetchVehicles.mockResolvedValue([amio, amioS]);
    const user = userEvent.setup();

    render(
      <DemoStoreProvider>
        <VehicleComparison />
      </DemoStoreProvider>,
    );

    // Catalog chỉ có xe máy → tab Xe máy điện tự active, danh sách không trộn loại.
    expect(await screen.findByRole("button", { name: "Xe máy điện" })).toHaveAttribute("aria-pressed", "true");

    const card = screen.getByRole("button", { name: "Amio Standard" });
    // Thẻ chọn xe mang ảnh (trang trí, alt rỗng) chứ không còn là nút chữ trần.
    expect(card.querySelector("img")).not.toBeNull();

    await user.click(card);
    expect(card).toHaveAttribute("aria-pressed", "true");
    await user.click(card);
    expect(card).toHaveAttribute("aria-pressed", "false");

    // Tab Ô tô điện: nhóm này chưa có xe → nói rõ, không bày lưới rỗng câm.
    await user.click(screen.getByRole("button", { name: "Ô tô điện" }));
    expect(screen.getByText("Chưa có xe thuộc nhóm này trong danh mục.")).toBeInTheDocument();
  });

  it("tích V theo SỐ THẬT từng hàng, không tô cột đầu vô điều kiện (Sếp 2026-08-31)", async () => {
    fetchVehicles.mockResolvedValue([amio, amioS]);
    const user = userEvent.setup();

    render(
      <DemoStoreProvider>
        <VehicleComparison />
      </DemoStoreProvider>,
    );

    await user.click(await screen.findByRole("button", { name: "Amio Standard" }));
    await user.click(screen.getByRole("button", { name: "Amio S" }));

    const rowFor = (label: string) => screen.getByText(label).closest("tr")!;
    // Giá hai xe BẰNG NHAU → không ai được tích.
    expect(rowFor("Giá niêm yết").querySelectorAll("td.is-highlight")).toHaveLength(0);
    // Tầm hoạt động: Amio Standard 65 km thắng Amio S 30 km → tích đúng cột thắng.
    const rangeCells = rowFor("Tầm hoạt động").querySelectorAll("td");
    expect(rangeCells[0]).toHaveClass("is-highlight");
    expect(rangeCells[1]).not.toHaveClass("is-highlight");
    // Không còn nhãn khen vô căn cứ.
    expect(screen.queryByText("Đề xuất hàng đầu")).toBeNull();
  });
});
