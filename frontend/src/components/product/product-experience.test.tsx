// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProductExperience } from "@/components/product/product-experience";
import { getMotorbikeMenuEntry } from "@/mocks/motorbike-menu";
import { getVehicleMenuEntry } from "@/mocks/vehicle-menu";

vi.mock("next/image", () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} data-image-src={src} src={src} />
  ),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: React.ComponentProps<"a">) => <a href={href}>{children}</a>,
}));

describe("ProductExperience", () => {
  afterEach(() => cleanup());

  it("uses local media and specifications for VF 9", () => {
    const vehicle = getVehicleMenuEntry("vf-9")!;

    render(<ProductExperience category="car" categoryLabel={vehicle.categoryLabel} vehicle={vehicle} />);

    expect(screen.getByRole("heading", { level: 1, name: "VF 9" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "VinFast VF 9 trước kiến trúc hiện đại" })).toHaveAttribute("data-image-src", "/media/vinfast/vf9/hero.webp");
    expect(screen.getAllByText("626 km").length).toBeGreaterThan(0);
    expect(screen.getByText("620 Nm")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Đặt lịch lái thử" }).length).toBeGreaterThan(0);
  });

  it("uses the shared image-switching behavior for another car with color media", () => {
    const vehicle = getVehicleMenuEntry("vf-7")!;

    render(<ProductExperience category="car" categoryLabel={vehicle.categoryLabel} vehicle={vehicle} />);
    fireEvent.click(screen.getByRole("button", { name: "Urban Mint" }));

    expect(screen.getByRole("img", { name: "VinFast VF 7 màu Urban Mint" })).toHaveAttribute(
      "data-image-src",
      "/vehicles/vf7/urban-mint.webp",
    );
  });

  it("switches the Kyo image to the exact selected color", () => {
    const motorbike = getMotorbikeMenuEntry("kyo")!;

    render(<ProductExperience category="motorcycle" categoryLabel={motorbike.categoryLabel} vehicle={{ ...motorbike, imageUrl: motorbike.detailImageUrl }} />);

    expect(screen.getByRole("img", { name: "VinFast Kyo màu Nâu Ánh Kim" })).toHaveAttribute("data-image-src", "/media/vinfast/kyo/hero.webp");
    fireEvent.click(screen.getByRole("button", { name: "Trắng Ngọc Trai" }));
    expect(screen.getByRole("img", { name: "VinFast Kyo màu Trắng Ngọc Trai" })).toHaveAttribute("data-image-src", "/media/vinfast/kyo/color-white.webp");
    expect(screen.getByText(/35\.300\.000/)).toBeInTheDocument();
  });

  it("recreates the complete Vero X product story and uses the official same-angle color set", () => {
    const motorbike = getMotorbikeMenuEntry("vero-x")!;

    render(<ProductExperience category="motorcycle" categoryLabel={motorbike.categoryLabel} vehicle={{ ...motorbike, imageUrl: motorbike.detailImageUrl }} />);

    expect(screen.getByRole("heading", { level: 1, name: "Vero X" })).toBeInTheDocument();
    expect(screen.getByText("Xe máy điện 02 pin")).toBeInTheDocument();
    expect(screen.getAllByText("~262 km/1 lần sạc").length).toBeGreaterThan(0);
    expect(screen.getAllByText("35 lít").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/34\.900\.000/).length).toBeGreaterThan(0);
    const oliveImages = screen.getAllByRole("img", { name: "VinFast Vero X màu Xanh ô liu" });
    expect(oliveImages.length).toBeGreaterThan(0);
    expect(oliveImages[0]).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/vero-x/color-green.webp",
    );
    expect(screen.getByRole("heading", { name: "Smart Key" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Chống nước" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Nạp năng lượng ấn tượng" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Linh hoạt nâng cấp 02 pin" })).toBeInTheDocument();

    const displayFeature = screen.getByRole("img", { name: /màn hình TFT hiện đại/i });
    expect(displayFeature).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/vero-x/feature-display.webp",
    );
    expect(displayFeature.closest(".vf-reveal")).toHaveClass("from-right");
    expect(screen.getByRole("img", { name: /cốp 35L/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /sàn để chân/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /giảm xóc/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /phanh đĩa/i })).toBeInTheDocument();

    expect(screen.getByRole("heading", { name: "Công nghệ Pin tiên tiến" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Công nghệ Pin LFP" })).toBeInTheDocument();
    expect(screen.getAllByText(/Khoảng 6h30 phút từ 0 - 100%/).length).toBeGreaterThan(0);
    expect(screen.getByText("1295 mm")).toBeInTheDocument();
    expect(screen.getByText("2250 W")).toBeInTheDocument();
    expect(screen.getByText("BLDC Inhub")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tải Brochure" })).toHaveAttribute(
      "href",
      "https://storage.googleapis.com/vinfast-data-01/brochure/120226_VinFast_VEROX_Brochure.pdf",
    );

    fireEvent.click(screen.getByRole("button", { name: "Xanh rêu" }));

    for (const image of screen.getAllByRole("img", { name: "VinFast Vero X màu Xanh rêu" })) {
      expect(image).toHaveAttribute(
        "data-image-src",
        "/media/vinfast/motorbikes/vero-x/color-blue.webp",
      );
    }
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("Vero+X"),
    );
  });

  it("recreates the complete Evo Grand campaign, color carousel, cube features, and specifications", () => {
    const motorbike = getMotorbikeMenuEntry("evo-grand")!;

    render(<ProductExperience category="motorcycle" categoryLabel={motorbike.categoryLabel} vehicle={{ ...motorbike, imageUrl: motorbike.detailImageUrl }} />);

    expect(screen.getByRole("heading", { level: 1, name: "Evo Grand" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Chiến dịch VinFast Evo Grand" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/evo-grand/campaign-hero.webp",
    );
    expect(screen.getByRole("img", { name: "Evo Grand trên phố cùng khách hàng" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/evo-grand/overview.webp",
    );
    expect(screen.getByText("70 km/h*")).toBeInTheDocument();
    expect(screen.getByText("262 km/1 lần sạc*")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Đa dạng tùy chọn màu sắc" })).toBeInTheDocument();
    expect(screen.getAllByText("35 lít").length).toBeGreaterThan(0);
    expect(screen.getByText(/22\.500\.000/)).toBeInTheDocument();
    expect(screen.getByText("Giá đã bao gồm VAT, 1 pin và 1 bộ sạc")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Evo Grand đồng hành cùng nhịp sống đô thị" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/evo-grand/city-banner.webp",
    );

    const featureStage = screen.getByTestId("evo-grand-feature-stage");
    expect(featureStage).toHaveAttribute("data-effect", "cube");
    expect(screen.getByText("Thể tích cốp 35L tối ưu sức chứa – tối đa nhu cầu.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tính năng tiếp theo" }));
    expect(screen.getByText("Linh hoạt nâng cấp 02 pin kép, gấp đôi năng lượng, nâng tầm hiệu suất.")).toBeInTheDocument();

    const greenSwatch = screen.getByRole("button", { name: "Xanh ô liu" });
    fireEvent.click(greenSwatch);

    expect(greenSwatch).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("evo-grand-color-track")).toHaveStyle({
      "--desktop-color-offset": "-266.664%",
    });
    expect(screen.getByRole("img", { name: "VinFast Evo Grand màu Xanh ô liu" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/evo-grand/color-5.webp",
    );
    expect(screen.getByRole("img", { name: "Evo Grand chinh phục hành trình đô thị" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/evo-grand/closing-banner.webp",
    );
    expect(screen.getByText("Khoảng 6 giờ 30 phút (từ 0 đến 100%)")).toBeInTheDocument();
    expect(screen.getByText("Pin chính đặt dưới sàn để chân, pin phụ đặt ở cốp")).toBeInTheDocument();
    expect(screen.getByText("Khoảng 134 km (+128 Km khi lắp thêm pin phụ)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Tải brochure" })).toHaveAttribute(
      "href",
      "https://storage.googleapis.com/vinfast-data-01/brochure/05022026/030226_Vinfast_EvoGrand_Brochure.pdf",
    );
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("Evo+Grand"),
    );
  });

  it("renders the Kinet reference content and changes the vehicle image with its color", () => {
    const motorbike = getMotorbikeMenuEntry("kinet")!;

    render(<ProductExperience category="motorcycle" categoryLabel={motorbike.categoryLabel} vehicle={{ ...motorbike, imageUrl: motorbike.detailImageUrl }} />);

    expect(screen.getByRole("heading", { level: 1, name: "Kinet" })).toBeInTheDocument();
    expect(screen.getByText("Bật chất thể thao")).toBeInTheDocument();
    expect(screen.getAllByText("~90 km/h").length).toBeGreaterThan(0);
    expect(screen.getAllByText("~145 km/1 lần sạc").length).toBeGreaterThan(0);
    expect(screen.getByRole("img", { name: "VinFast Kinet màu Xám xi măng" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/kinet/color-cement-grey.webp",
    );
    expect(screen.getByRole("img", { name: /màn hình TFT/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /cốp 22 lít/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Đỏ đen" }));

    expect(screen.getByRole("img", { name: "VinFast Kinet màu Đỏ đen" })).toHaveAttribute(
      "data-image-src",
      "/media/vinfast/motorbikes/kinet/color-red-black.webp",
    );
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("Kinet"),
    );
  });

  it("opens the existing chat dock from the consultation CTA", () => {
    const listener = vi.fn();
    window.addEventListener("vinfast:open-agent-dock", listener);
    const vehicle = getVehicleMenuEntry("vf-9")!;

    render(<ProductExperience category="car" categoryLabel={vehicle.categoryLabel} vehicle={vehicle} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Tư vấn" })[0]);

    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("vinfast:open-agent-dock", listener);
  });

  it("uses the same advisor and ViVi choices for every shared vehicle page", () => {
    const vehicle = getVehicleMenuEntry("vf-9")!;

    render(<ProductExperience category="car" categoryLabel={vehicle.categoryLabel} vehicle={vehicle} />);

    expect(screen.queryByText(/đặt cọc/i)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /tư vấn viên/i })).toHaveAttribute("href", "/test-drive");
    expect(screen.getByRole("link", { name: /trợ lý ảo vivi/i })).toHaveAttribute(
      "href",
      expect.stringContaining("/consultation?"),
    );
  });
});
