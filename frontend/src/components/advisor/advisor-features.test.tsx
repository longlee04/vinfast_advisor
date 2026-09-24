// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ADVISOR_FEATURES, ADVISOR_MENU, AdvisorPageHeading } from "@/components/advisor/advisor-features";

afterEach(cleanup);

describe("Tính năng tư vấn viên (plan §17)", () => {
  it("menu gọn còn 5 tính năng (Hội thoại gộp vào Khách hàng), mỗi tính năng có một dòng mô tả nghiệp vụ", () => {
    expect(ADVISOR_MENU.map((key) => ADVISOR_FEATURES[key].label)).toEqual([
      "Tổng quan",
      "Khách hàng",
      "Duyệt nội dung AI",
      "Lịch lái thử",
      "Ưu đãi",
    ]);
    const hrefs = ADVISOR_MENU.map((key) => ADVISOR_FEATURES[key].href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    for (const key of ADVISOR_MENU) expect(ADVISOR_FEATURES[key].description.length).toBeGreaterThan(40);
  });

  it("tiêu đề trang lấy đúng tên + mô tả của tính năng", () => {
    render(<AdvisorPageHeading feature="review" />);
    expect(screen.getByRole("heading", { level: 1, name: "Duyệt nội dung AI" })).toBeInTheDocument();
    expect(screen.getByText(ADVISOR_FEATURES.review.description)).toBeInTheDocument();
  });
});
