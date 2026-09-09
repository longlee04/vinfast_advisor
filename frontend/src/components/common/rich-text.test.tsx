// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { RichText } from "@/components/common/rich-text";

// `globals` tắt trong vitest.config.ts nên auto-cleanup của testing-library
// không tự chạy; phải tự gọi cleanup() sau mỗi test.
afterEach(() => {
  cleanup();
});

/**
 * Câu trả lời "thông tin xe vf 5" đúng như backend sinh ra
 * (`domain/catalog_reply.render_lookup_answer`).
 */
const VEHICLE_SHEET = [
  "Dạ, VinFast VF 5 All New là mẫu xe thuần điện của VinFast. Xe thuộc phân khúc SUV, 5 chỗ ngồi.",
  "",
  "1. **Thông số kỹ thuật**:",
  "* **Kích thước**: 3.967 x 1.723 x 1.578 mm",
  "* **Động cơ & Vận hành**: công suất 100 kW, mô-men xoắn 135 Nm",
  "",
  "2. **An toàn**:",
  "* **Trang bị an toàn**: ABS (chống bó cứng phanh)",
  "",
  "3. **Giá bán**: từ 436.000.000 đồng (đã bao gồm VAT).",
  "",
  "Hy vọng thông tin trên hữu ích với Quý khách.",
].join("\n");

describe("RichText", () => {
  it("giữ ranh giới giữa các mục thay vì dồn thành một đoạn văn", () => {
    const { container } = render(<RichText text={VEHICLE_SHEET} />);

    // Lỗi gốc: cả câu trả lời về một text node duy nhất, HTML nuốt hết `\n`.
    expect(container.querySelectorAll("p").length).toBeGreaterThan(1);
    expect(container.querySelectorAll("ul")).toHaveLength(2);
    expect(container.querySelectorAll("li")).toHaveLength(3);
  });

  it("in đậm tên trường và tiêu đề mục, không để lọt dấu sao ra màn hình", () => {
    const { container } = render(<RichText text={VEHICLE_SHEET} />);

    const bold = [...container.querySelectorAll("strong")].map((node) => node.textContent);
    expect(bold).toEqual([
      "Thông số kỹ thuật",
      "Kích thước",
      "Động cơ & Vận hành",
      "An toàn",
      "Trang bị an toàn",
      "Giá bán",
    ]);
    expect(container.textContent).not.toContain("*");
  });

  it("giữ nguyên số thứ tự do backend sinh, không để trình duyệt đánh số lần nữa", () => {
    const { container } = render(<RichText text={VEHICLE_SHEET} />);

    expect(container.querySelectorAll("ol")).toHaveLength(0);
    expect(screen.getByText(/Thông số kỹ thuật/).parentElement?.textContent).toContain("1. ");
  });

  it("xuống dòng thật giữa các dòng liền nhau trong cùng một đoạn", () => {
    const { container } = render(<RichText text={"dòng một\ndòng hai"} />);

    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(container.querySelectorAll("br")).toHaveLength(1);
  });

  it("không diễn giải HTML thô trong nội dung agent sinh ra", () => {
    const { container } = render(<RichText text={"<b>đậm</b> <script>x</script>"} />);

    expect(container.querySelector("b")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<b>đậm</b>");
  });

  it("văn xuôi một đoạn vẫn là một đoạn, không bị bẻ thành danh sách", () => {
    const { container } = render(
      <RichText text={"**VinFast VF 5** phù hợp với nhu cầu đi lại trong phố."} />,
    );

    expect(container.querySelectorAll("p")).toHaveLength(1);
    expect(container.querySelectorAll("ul")).toHaveLength(0);
    expect(container.querySelector("strong")?.textContent).toBe("VinFast VF 5");
  });

  it("hiển thị gợi ý giữa dấu sao đơn bằng chữ nghiêng và màu muted", () => {
    render(<RichText text="*Ví dụ: đi phố, ngân sách 500 triệu*" />);

    const hint = screen.getByText("Ví dụ: đi phố, ngân sách 500 triệu").closest("em");
    expect(hint).toHaveClass("rich-text-hint");
  });

  it("giữ in đậm và liên kết nội bộ bên trong gợi ý", () => {
    render(<RichText text="*Ví dụ: chọn **VF 5** hoặc [xem xe](/vehicles/vf-5)*" />);

    const hint = screen.getByText(/Ví dụ: chọn/).closest("em");
    expect(hint).not.toBeNull();
    expect(hint?.querySelector("strong")?.textContent).toBe("VF 5");
    expect(screen.getByRole("link", { name: "xem xe" })).toHaveAttribute(
      "href",
      "/vehicles/vf-5",
    );
  });

  it("giữ bullet dấu sao và marker gợi ý không khớp ở dạng nguyên văn", () => {
    const { container } = render(<RichText text={"* bullet thật\n\n*gợi ý chưa đóng"} />);

    expect(container.querySelectorAll("li")).toHaveLength(1);
    expect(container.querySelector("li")?.textContent).toBe("bullet thật");
    expect(container.querySelector("em")).toBeNull();
    expect(container.textContent).toContain("*gợi ý chưa đóng");
  });

  it("không diễn giải HTML thô bên trong gợi ý", () => {
    const { container } = render(<RichText text="*Ví dụ: <img src=x onerror=alert(1)>*" />);

    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("em")?.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});

// ── Liên kết nội bộ ─────────────────────────────────────────────────────────

describe("RichText lien ket noi bo", () => {
  it("dung the a cho duong dan tuong doi", () => {
    render(<RichText text="**VF 8**: SUV 5 chỗ. [Xem thêm](/vehicles/vinfast-vf-8-eco)" />);

    const link = screen.getByRole("link", { name: "Xem thêm" });
    expect(link).toHaveAttribute("href", "/vehicles/vinfast-vf-8-eco");
  });

  it("KHONG dung link tuyet doi hay javascript", () => {
    // Nội dung ở đây do LLM sinh. Mở `http(s)`/`javascript:` là mở đúng bề mặt
    // injection mà component này cố ý tránh khi từ chối `react-markdown`.
    render(
      <RichText text="[a](https://evil.com) [b](javascript:alert(1)) [c](//evil.com)" />,
    );

    expect(screen.queryByRole("link")).toBeNull();
    // Cú pháp không khớp thì đi qua NGUYÊN VĂN dưới dạng text, không biến mất.
    expect(screen.getByText(/evil\.com/)).toBeInTheDocument();
  });

  it("nhan cua link van in dam duoc", () => {
    render(<RichText text="[**Xem thêm**](/vehicles/vf-9)" />);

    const link = screen.getByRole("link");
    expect(link.querySelector("strong")?.textContent).toBe("Xem thêm");
  });

  it("render link Google Maps (allowlist duy nhất cho link tuyệt đối), mở tab mới", () => {
    render(<RichText text="Bấm [Chỉ đường tới showroom](https://www.google.com/maps/dir/?api=1&destination=VinFast%20VGC) nhé ạ." />);
    const link = screen.getByRole("link", { name: "Chỉ đường tới showroom" });
    expect(link).toHaveAttribute("href", "https://www.google.com/maps/dir/?api=1&destination=VinFast%20VGC");
    expect(link).toHaveAttribute("target", "_blank");
  });

  it("link tuyệt đối NGOÀI allowlist vẫn bị giữ nguyên dạng chữ", () => {
    render(<RichText text="xem [đây](https://evil.example/x) nhé" />);
    expect(screen.queryByRole("link", { name: "đây" })).toBeNull();
  });
});
