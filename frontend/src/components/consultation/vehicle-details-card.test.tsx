import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { VehicleDetailsCard } from "@/components/consultation/vehicle-details-card";
import type { VehicleDetails } from "@/types/agent";

afterEach(cleanup);

/**
 * Vòng rà soát #4 gỡ ba khối điểm nổi bật / tính năng / an toàn: chúng chở trích
 * đoạn RAG thô, lọc duy nhất bằng trạng thái `ACTIVE` của TÀI LIỆU — không phải
 * dấu duyệt cho từng câu khẳng định. Thẻ giờ chỉ chở nhóm thông số đọc thẳng từ
 * danh mục.
 */
const FULL: VehicleDetails = {
  vehicle_name: "VinFast VF 5 All New",
  spec_groups: [
    { title: "Giá bán", rows: [["Bản tiêu chuẩn", "496.000.000 đồng"]] },
    { title: "Kích thước", rows: [["Dài", "4323 mm"]] },
    { title: "Vận hành", rows: [["Bản tiêu chuẩn — công suất", "100 kW"]] },
  ],
};

describe("VehicleDetailsCard", () => {
  it("hiện tên xe và từng nhóm thông số một tiêu đề", () => {
    render(<VehicleDetailsCard details={FULL} />);

    expect(screen.getByText("VinFast VF 5 All New")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Giá bán" })).toHaveTextContent("496.000.000 đồng");
    expect(screen.getByRole("region", { name: "Kích thước" })).toHaveTextContent("4323 mm");
    expect(screen.getByRole("region", { name: "Vận hành" })).toHaveTextContent("100 kW");
  });

  // ── Thiếu dữ liệu là BỎ BỚT, không bao giờ là ô rỗng ────────────────────────

  it("không có dữ liệu thì không vẽ gì", () => {
    const { container } = render(<VehicleDetailsCard details={null} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("không còn nhóm nào thì không vẽ cả thẻ", () => {
    const { container } = render(<VehicleDetailsCard details={{ ...FULL, spec_groups: [] }} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("nhóm thông số rỗng không được hiện thành một tiêu đề trống", () => {
    render(
      <VehicleDetailsCard
        details={{ ...FULL, spec_groups: [{ title: "Kích thước", rows: [] }] }}
      />,
    );

    expect(screen.queryByRole("region", { name: "Kích thước" })).not.toBeInTheDocument();
  });
});
