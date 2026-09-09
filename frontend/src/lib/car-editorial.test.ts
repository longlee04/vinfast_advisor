import { describe, expect, it } from "vitest";

import { extractCarEditorial } from "@/lib/car-editorial";

describe("extractCarEditorial", () => {
  it("chỉ lấy phần tổng quan cô đọng từ tài liệu car_pdf", () => {
    const markdown = `---\ntitle: VF 6\nsource_url: https://example.com/vf6\n---\n# VF 6\n\n## Tổng quan\n\nCâu đầu tiên giới thiệu mẫu xe. Câu thứ hai mô tả nhóm khách hàng. Câu thứ ba không cần đưa lên hero.\n\n## Thiết kế ngoại thất\n\nNgoại thất trẻ trung.\n\n## Nội thất và tiện nghi\n\nKhoang lái rộng rãi.\n\n## Khả năng vận hành\n\nVận hành linh hoạt.\n\n## An toàn và hỗ trợ lái\n\nBảo vệ chủ động.`;

    expect(extractCarEditorial(markdown)).toEqual({
      summary: "Câu đầu tiên giới thiệu mẫu xe. Câu thứ hai mô tả nhóm khách hàng.",
      exterior: "Ngoại thất trẻ trung.",
      interior: "Khoang lái rộng rãi.",
      performance: "Vận hành linh hoạt.",
      safety: "Bảo vệ chủ động.",
      sourceUrl: "https://example.com/vf6",
    });
  });
});
