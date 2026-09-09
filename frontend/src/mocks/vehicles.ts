import type { Vehicle } from "@/types/demo";

export const vehicles: Vehicle[] = [
  {
    id: "vf6-plus",
    modelName: "VF 6",
    variant: "Plus",
    vehicleType: "car",
    priceVnd: 749_000_000,
    rangeKm: 399,
    seats: 5,
    chargeMinutes: 25,
    warranty: "Theo chính sách hiện hành",
    dimensions: "SUV đô thị cỡ B",
    strongestAdvantage: "Cân bằng giữa không gian, chi phí và tầm hoạt động",
    tradeoff: "Khoang hành lý nhỏ hơn các SUV cỡ C",
    bestFor: "Gia đình 4–5 người di chuyển trong đô thị",
    assetStatus: "missing",
    availableColors: [
      { id: "blue", name: "Urban Blue", hex: "#315f89" },
      { id: "white", name: "Brahminy White", hex: "#e9edf2" },
      { id: "black", name: "Jet Black", hex: "#252a31" },
    ],
  },
  {
    id: "vf7-base",
    modelName: "VF 7",
    variant: "Base",
    vehicleType: "car",
    priceVnd: 799_000_000,
    rangeKm: 430,
    seats: 5,
    chargeMinutes: 35,
    warranty: "Theo chính sách hiện hành",
    dimensions: "SUV cỡ C",
    strongestAdvantage: "Không gian rộng và phong cách thể thao",
    tradeoff: "Chi phí ban đầu cao hơn VF 6",
    bestFor: "Gia đình ưu tiên không gian và trải nghiệm vận hành",
    assetStatus: "missing",
    availableColors: [
      { id: "blue", name: "Deep Ocean", hex: "#2c557d" },
      { id: "red", name: "Crimson Red", hex: "#8f3034" },
      { id: "grey", name: "Desat Silver", hex: "#9199a2" },
    ],
  },
  {
    id: "vf5-plus",
    modelName: "VF 5",
    variant: "Plus",
    vehicleType: "car",
    priceVnd: 529_000_000,
    rangeKm: 326,
    seats: 5,
    chargeMinutes: 33,
    warranty: "Theo chính sách hiện hành",
    dimensions: "SUV đô thị cỡ A",
    strongestAdvantage: "Chi phí tiếp cận thấp nhất trong nhóm",
    tradeoff: "Không gian và tầm hoạt động thấp hơn hai lựa chọn còn lại",
    bestFor: "Khách hàng ưu tiên chi phí và di chuyển nội đô",
    assetStatus: "missing",
    availableColors: [
      { id: "red", name: "Crimson Red", hex: "#8f3034" },
      { id: "white", name: "Brahminy White", hex: "#e9edf2" },
    ],
  },
  {
    id: "evo200",
    modelName: "Evo200",
    variant: "Standard",
    vehicleType: "electric_motorbike",
    priceVnd: 22_000_000,
    rangeKm: 203,
    chargeMinutes: 600,
    warranty: "Theo chính sách xe máy điện",
    dimensions: "Xe máy điện đô thị",
    strongestAdvantage: "Tầm hoạt động dài cho nhu cầu đi làm",
    tradeoff: "Không phù hợp để so sánh trực tiếp với ô tô",
    bestFor: "Đi làm và nhu cầu cá nhân hàng ngày",
    assetStatus: "missing",
    availableColors: [{ id: "white", name: "Trắng", hex: "#e9edf2" }],
  },
];

export function getVehicle(vehicleId: string): Vehicle {
  const vehicle = vehicles.find((item) => item.id === vehicleId);
  if (!vehicle) {
    throw new Error(`Unknown mock vehicle: ${vehicleId}`);
  }
  return vehicle;
}
