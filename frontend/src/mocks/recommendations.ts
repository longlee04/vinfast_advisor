import type { VehicleRecommendation } from "@/types/demo";

export const recommendations: VehicleRecommendation[] = [
  {
    id: "rec-vf6",
    vehicleId: "vf6-plus",
    rank: 1,
    reasons: [
      "Nằm trong ngân sách dự kiến 800 triệu đồng",
      "Không gian 5 chỗ phù hợp gia đình",
      "Tầm hoạt động đáp ứng quãng đường hàng tháng",
    ],
    tradeoff: "Khoang hành lý nhỏ hơn VF 7.",
    sourceLabels: ["Catalog xe v12", "Bảng giá 08/2026"],
    advisorReviewed: true,
  },
  {
    id: "rec-vf7",
    vehicleId: "vf7-base",
    rank: 2,
    reasons: [
      "Không gian rộng hơn cho gia đình",
      "Tầm hoạt động nổi bật trong nhóm",
      "Giá vẫn nằm sát ngân sách khai báo",
    ],
    tradeoff: "Chi phí ban đầu cao hơn VF 6.",
    sourceLabels: ["Catalog xe v12", "Thông số VF 7"],
    advisorReviewed: true,
  },
  {
    id: "rec-vf5",
    vehicleId: "vf5-plus",
    rank: 3,
    reasons: [
      "Tiết kiệm đáng kể so với ngân sách tối đa",
      "Kích thước phù hợp di chuyển nội đô",
    ],
    tradeoff: "Không gian và tầm hoạt động thấp hơn VF 6, VF 7.",
    sourceLabels: ["Catalog xe v11", "Bảng giá 08/2026"],
    advisorReviewed: true,
  },
];
