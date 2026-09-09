export type ProductMedia = {
  src: string;
  alt: string;
  role: "hero" | "exterior" | "interior" | "detail" | "technology" | "color" | "battery" | "safety";
  label?: string;
  swatch?: string;
  title?: string;
  description?: string;
};

export type ProductSpecification = Readonly<{
  key: string;
  label: string;
  value: string;
}>;

export type ProductExperienceData = {
  slug: string;
  model: string;
  category: "car" | "motorcycle";
  heroEyebrow?: string;
  motorcycleLayout?: "campaign" | "configurator" | "evo-grand" | "vero";
  storyLayout?: "details-first" | "editorial-first";
  tagline: string;
  hero: ProductMedia;
  gallery: ProductMedia[];
  statement: string;
  priceVnd: number | null;
  priceNote?: string;
  brochureUrl?: string;
  specificationNotes?: string[];
  metrics: Array<Readonly<{ label: string; value: string }>>;
  specificationGroups: Array<Readonly<{ title: string; items: ProductSpecification[] }>>;
};

export type LocalCatalogVehicle = Readonly<{
  id: string;
  modelName: string;
  vehicleType: "car" | "electric_motorbike";
  priceVnd: number | null;
  rangeKm: number | null;
  seats: number | null;
  chargeMinutes: number | null;
  batteryCapacityKwh: number | null;
  imageUrl: string;
  href: string;
  /** Thông số cho hộp "Thông số nhanh" — lấy từ bảng thông số của chính mẫu đó, không bịa. */
  quickSpecs: ReadonlyArray<Readonly<{ label: string; value: string }>>;
}>;

/** Thứ tự ưu tiên khi chọn thông số nhanh; khoá nào mẫu không có thì bỏ qua. */
const QUICK_SPEC_KEYS = ["range", "battery", "charge", "power", "torque", "speed", "seats", "configuration", "dimensions", "storage", "motor", "brakes", "weight"] as const;
const MAX_QUICK_SPECS = 8;

function quickSpecsOf(product: ProductExperienceData): Array<Readonly<{ label: string; value: string }>> {
  const items = product.specificationGroups.flatMap((group) => group.items);
  const picked = new Map<string, Readonly<{ label: string; value: string }>>();
  for (const key of QUICK_SPEC_KEYS) {
    const item = items.find((entry) => entry.key === key && entry.value.trim());
    if (item && !picked.has(item.label)) picked.set(item.label, { label: item.label, value: item.value });
  }
  for (const metric of product.metrics) {
    if (!picked.has(metric.label) && metric.value.trim()) picked.set(metric.label, metric);
  }
  return [...picked.values()].slice(0, MAX_QUICK_SPECS);
}

const mediaRoot = "/media/vinfast";

function specs(items: Array<[string, string, string]>): ProductSpecification[] {
  return items.map(([key, label, value]) => ({ key, label, value }));
}

function simpleProduct(options: Readonly<{
  slug: string;
  model: string;
  category: "car" | "motorcycle";
  hero: string;
  priceVnd: number | null;
  range: string;
  speedOrSeats: string;
  power: string;
}>): ProductExperienceData {
  const isCar = options.category === "car";
  const metrics = isCar
    ? [
      { label: "Quãng đường", value: options.range },
      { label: "Cấu hình ghế", value: options.speedOrSeats },
      { label: "Công suất", value: options.power },
    ]
    : [
      { label: "Tốc độ tối đa", value: options.speedOrSeats },
      { label: "Quãng đường", value: options.range },
      { label: "Công suất tối đa", value: options.power },
    ];
  return {
    slug: options.slug,
    model: options.model,
    category: options.category,
    tagline: isCar ? "Cùng bạn bứt phá mọi giới hạn." : "Linh hoạt trong từng hành trình.",
    statement: isCar
      ? "Thiết kế hiện đại, vận hành thuần điện và công nghệ thông minh cho nhịp sống mỗi ngày."
      : "Thiết kế gọn gàng, vận hành êm ái và tiện ích thực tế cho đô thị.",
    hero: { src: options.hero, alt: `VinFast ${options.model}`, role: "hero" },
    gallery: [],
    priceVnd: options.priceVnd,
    metrics,
    specificationGroups: [{
      title: isCar ? "Vận hành" : "Thông số chính",
      items: specs([
        ["range", "Quãng đường", options.range],
        ["configuration", isCar ? "Số chỗ" : "Tốc độ tối đa", options.speedOrSeats],
        ["power", "Công suất", options.power],
      ]),
    }],
  };
}

const productData: Record<string, ProductExperienceData> = {
  "vf-2": simpleProduct({ slug: "vf-2", model: "VF 2", category: "car", hero: `${mediaRoot}/vf2/hero.webp`, priceVnd: null, range: "Đang cập nhật", speedOrSeats: "4 chỗ", power: "Đang cập nhật" }),
  "vf-3": simpleProduct({ slug: "vf-3", model: "VF 3", category: "car", hero: `${mediaRoot}/vf3/hero.webp`, priceVnd: 299_000_000, range: "210 km", speedOrSeats: "4 chỗ", power: "32 kW" }),
  "vf-5": simpleProduct({ slug: "vf-5", model: "VF 5", category: "car", hero: `${mediaRoot}/vf5/hero.webp`, priceVnd: 529_000_000, range: "326 km", speedOrSeats: "5 chỗ", power: "100 kW" }),
  "vf-6": simpleProduct({ slug: "vf-6", model: "VF 6", category: "car", hero: `${mediaRoot}/vf6/hero.webp`, priceVnd: 689_000_000, range: "399 km", speedOrSeats: "5 chỗ", power: "150 kW" }),
  "vf-mpv-7": simpleProduct({ slug: "vf-mpv-7", model: "VF MPV 7", category: "car", hero: `${mediaRoot}/vf7/hero.webp`, priceVnd: null, range: "Đang cập nhật", speedOrSeats: "7 chỗ", power: "Đang cập nhật" }),
  "vf-8": simpleProduct({ slug: "vf-8", model: "VF 8", category: "car", hero: `${mediaRoot}/vf8/hero.webp`, priceVnd: 1_019_000_000, range: "562 km", speedOrSeats: "5 chỗ", power: "300 kW" }),
  "vf-8-all-new": simpleProduct({ slug: "vf-8-all-new", model: "VF 8 The All New", category: "car", hero: `${mediaRoot}/vf8/hero.webp`, priceVnd: null, range: "Đang cập nhật", speedOrSeats: "5 chỗ", power: "Đang cập nhật" }),
  "vf-7": {
    ...simpleProduct({ slug: "vf-7", model: "VF 7", category: "car", hero: "/vehicles/vf7/design.webp", priceVnd: 799_000_000, range: "496 km", speedOrSeats: "5 chỗ", power: "260 kW" }),
    tagline: "Dấu ấn riêng trên mọi cung đường.",
    statement: "Một dáng xe giàu cảm xúc, được đặt trong bố cục tối giản để sản phẩm luôn là tâm điểm.",
    gallery: [
      { src: "/vehicles/vf7/solar-ruby.webp", alt: "VinFast VF 7 màu Solar Ruby", role: "color", label: "Solar Ruby", swatch: "#a80f26" },
      { src: "/vehicles/vf7/zenith-grey.webp", alt: "VinFast VF 7 màu Zenith Grey", role: "color", label: "Zenith Grey", swatch: "#73777a" },
      { src: "/vehicles/vf7/urban-mint.webp", alt: "VinFast VF 7 màu Urban Mint", role: "color", label: "Urban Mint", swatch: "#8b927f" },
      { src: "/vehicles/vf7/infinity-blanc.webp", alt: "VinFast VF 7 màu Infinity Blanc", role: "color", label: "Infinity Blanc", swatch: "#eeeeda" },
      { src: "/vehicles/vf7/jet-black.webp", alt: "VinFast VF 7 màu Jet Black", role: "color", label: "Jet Black", swatch: "#171819" },
      { src: "/vehicles/vf7/exterior.webp", alt: "Ngoại thất VinFast VF 7", role: "exterior" },
      { src: "/vehicles/vf7/interior.webp", alt: "Nội thất VinFast VF 7", role: "interior" },
      { src: "/vehicles/vf7/technology.webp", alt: "Công nghệ VinFast VF 7", role: "technology" },
    ],
  },
  "vf-9": {
    ...simpleProduct({ slug: "vf-9", model: "VF 9", category: "car", hero: `${mediaRoot}/vf9/hero.webp`, priceVnd: 1_499_000_000, range: "626 km", speedOrSeats: "7 chỗ", power: "300 kW" }),
    tagline: "Không gian cho những hành trình lớn.",
    hero: { src: `${mediaRoot}/vf9/hero.webp`, alt: "VinFast VF 9 trước kiến trúc hiện đại", role: "hero" },
    statement: "Tỷ lệ bề thế, khoang xe rộng và cách trình bày điềm tĩnh tạo nên trải nghiệm xứng tầm SUV cỡ lớn.",
    gallery: [
      { src: `${mediaRoot}/vf9/exterior-01.webp`, alt: "Thiết kế ngoại thất VinFast VF 9 nhìn từ trên cao", role: "exterior" },
      { src: `${mediaRoot}/vf9/exterior-grey.webp`, alt: "VinFast VF 9 màu Zenith Grey", role: "color", label: "Zenith Grey", swatch: "#777b80" },
      { src: `${mediaRoot}/vf9/exterior-white.webp`, alt: "VinFast VF 9 màu Infinity Blanc", role: "color", label: "Infinity Blanc", swatch: "#ecece7" },
      { src: `${mediaRoot}/vf9/exterior-red.webp`, alt: "VinFast VF 9 màu Crimson Red", role: "color", label: "Crimson Red", swatch: "#8f1d2d" },
      { src: `${mediaRoot}/vf9/interior-01.webp`, alt: "Khoang lái VinFast VF 9", role: "interior" },
      { src: `${mediaRoot}/vf9/interior-02.webp`, alt: "Hàng ghế VinFast VF 9", role: "detail" },
      { src: `${mediaRoot}/vf9/technology-01.webp`, alt: "Tiện nghi công nghệ VinFast VF 9", role: "technology" },
    ],
    specificationGroups: [
      { title: "Vận hành", items: specs([["range", "Quãng đường", "626 km"], ["power", "Công suất tối đa", "300 kW"], ["torque", "Mô-men xoắn", "620 Nm"]]) },
      { title: "Không gian", items: specs([["seats", "Số chỗ", "7 chỗ"], ["length", "Chiều dài", "5.118 mm"], ["wheelbase", "Chiều dài cơ sở", "3.150 mm"]]) },
    ],
  },
  kyo: {
    ...simpleProduct({ slug: "kyo", model: "Kyo", category: "motorcycle", hero: `${mediaRoot}/kyo/hero.webp`, priceVnd: 35_300_000, range: "82 km", speedOrSeats: "70 km/h", power: "3.000 W" }),
    tagline: "Linh hoạt đô thị. Sành điệu theo cách riêng.",
    hero: { src: `${mediaRoot}/kyo/hero.webp`, alt: "VinFast Kyo màu Nâu Ánh Kim", role: "hero" },
    statement: "Tỷ lệ thanh thoát, bảng màu phong phú và các tiện ích được trình bày qua từng góc nhìn riêng.",
    gallery: [
      { src: `${mediaRoot}/kyo/hero.webp`, alt: "VinFast Kyo màu Nâu Ánh Kim", role: "color", label: "Nâu Ánh Kim", swatch: "#66564a" },
      { src: `${mediaRoot}/kyo/color-white.webp`, alt: "VinFast Kyo màu Trắng Ngọc Trai", role: "color", label: "Trắng Ngọc Trai", swatch: "#eeeeda" },
      { src: `${mediaRoot}/kyo/color-red.webp`, alt: "VinFast Kyo màu Đỏ", role: "color", label: "Đỏ", swatch: "#9f1f26" },
      { src: `${mediaRoot}/kyo/color-black.webp`, alt: "VinFast Kyo màu Đen Bóng", role: "color", label: "Đen Bóng", swatch: "#171819" },
      { src: `${mediaRoot}/kyo/color-green.webp`, alt: "VinFast Kyo màu Xanh Oliu", role: "color", label: "Xanh Oliu", swatch: "#586153" },
      { src: `${mediaRoot}/kyo/technology-01.webp`, alt: "Màn hình và tay lái VinFast Kyo", role: "technology" },
      { src: `${mediaRoot}/kyo/storage-01.webp`, alt: "Cốp xe VinFast Kyo", role: "detail" },
      { src: `${mediaRoot}/kyo/comfort-01.webp`, alt: "Sàn để chân VinFast Kyo", role: "detail" },
      { src: `${mediaRoot}/kyo/safety-01.webp`, alt: "Bánh và hệ thống phanh VinFast Kyo", role: "safety" },
      { src: `${mediaRoot}/kyo/battery-01.webp`, alt: "VinFast Kyo nhìn nghiêng", role: "battery" },
    ],
  },
};

const motorbikes: Array<Readonly<[string, string, string, number | null, string, string, string]>> = [
  ["vero-x", "Vero X", "vero-x.webp", 34_900_000, "134 km", "70 km/h", "3.000 W"],
  ["viper", "Viper", "viper.webp", null, "Đang cập nhật", "70 km/h", "3.000 W"],
  ["kinet", "Kinet", "kinet.webp", null, "Đang cập nhật", "70 km/h", "3.000 W"],
  ["feliz-2025", "Feliz 2025", "feliz-2025.webp", 26_900_000, "134 km", "70 km/h", "3.000 W"],
  ["feliz-ii", "Feliz II", "feliz-ii.webp", null, "Đang cập nhật", "70 km/h", "3.000 W"],
  ["evo", "Evo", "evo.webp", null, "Đang cập nhật", "70 km/h", "2.500 W"],
  ["evo-lite", "Evo Lite", "evo-lite.png", null, "Đang cập nhật", "49 km/h", "1.600 W"],
  ["evo-grand", "Evo Grand", "evo-grand.webp", 21_000_000, "262 km", "70 km/h", "2.250 W"],
  ["evo-grand-lite", "Evo Grand Lite", "evo-grand-lite.webp", 18_000_000, "198 km", "49 km/h", "1.900 W"],
  ["evo-lite-neo", "Evo Lite Neo", "evo-lite-neo.webp", 22_000_000, "78 km", "49 km/h", "1.600 W"],
  ["flazz", "Flazz", "flazz.webp", 16_000_000, "70 km", "49 km/h", "1.100 W"],
  ["flazz-max", "Flazz Max", "flazz-max.webp", null, "Đang cập nhật", "49 km/h", "1.100 W"],
  ["zgoo", "ZGoo", "zgoo.webp", 14_900_000, "70 km", "49 km/h", "1.100 W"],
  ["amio", "Amio", "amio.webp", null, "Đang cập nhật", "49 km/h", "1.100 W"],
  ["amio-s", "Amio S", "amio-s.webp", null, "Đang cập nhật", "49 km/h", "1.100 W"],
  ["amio-s2", "Amio S2", "amio-s2.png", null, "Đang cập nhật", "49 km/h", "1.100 W"],
  ["vf-drgnfly-ebike", "VF DrgnFly eBike", "vf-drgnfly-ebike.png", null, "Đang cập nhật", "32 km/h", "750 W"],
];

for (const [slug, model, image, priceVnd, range, speed, power] of motorbikes) {
  productData[slug] = simpleProduct({
    slug,
    model,
    category: "motorcycle",
    hero: `/vehicles/motorbikes/${image}`,
    priceVnd,
    range,
    speedOrSeats: speed,
    power,
  });
}

const veroX = productData["vero-x"];
if (veroX) {
  productData["vero-x"] = {
    ...veroX,
    motorcycleLayout: "vero",
    heroEyebrow: "Xe máy điện 02 pin",
    tagline: "Nạp năng lượng ấn tượng, thêm hành trình hứng khởi.",
    statement: "Hai pin linh hoạt mở rộng hành trình, kết hợp cốp xe rộng và khả năng vận hành phù hợp nhịp sống đô thị.",
    priceNote: "Đã bao gồm VAT, 01 pin và 01 bộ sạc.",
    brochureUrl: "https://storage.googleapis.com/vinfast-data-01/brochure/120226_VinFast_VEROX_Brochure.pdf",
    specificationNotes: [
      "Hình ảnh xe mang tính minh họa. Phiên bản thực tế có thể có một số điểm khác biệt.",
      "Quãng đường di chuyển 1 lần sạc khi lắp 2 pin (theo điều kiện kiểm thử của VinFast tại 30km/h). Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định, phụ thuộc vào tốc độ lái xe, nhiệt độ, địa hình, thói quen sử dụng của người lái, chế độ lái được cài đặt, số lượng hành khách và các điều kiện giao thông khác.",
    ],
    metrics: [
      { label: "Tốc độ tối đa", value: "70 km/h" },
      { label: "Quãng đường di chuyển", value: "~262 km/1 lần sạc" },
      { label: "Dung tích cốp xe", value: "35 lít" },
    ],
    specificationGroups: [
      {
        title: "Kích thước và trang bị",
        items: specs([
          ["colors", "Màu sắc", "Xanh Rêu; Xanh Oliu; Đen nhám; Trắng Ngọc Trai"],
          ["wheelbase", "Khoảng cách trục bánh Trước-Sau", "1295 mm"],
          ["storage", "Thể tích cốp", "35L (16L Khi lắp pin phụ)"],
          ["dimensions", "Dài x Rộng x Cao (mm)", "1858 x 690 x 1100 mm"],
          ["ground-clearance", "Khoảng sáng gầm", "133 mm"],
          ["seat-height", "Chiều cao yên", "770 mm"],
          ["tires", "Kích thước lốp Trước - Sau", "90/90-12 | 90/90-12"],
          ["suspension", "Giảm xóc trước và sau", "Ống lồng-giảm chấn thủy lực; Giảm xóc đôi, giảm chấn thủy lực"],
          ["smart-key", "Khóa xe", "Khóa thông minh"],
        ]),
      },
      {
        title: "Pin",
        items: specs([
          ["battery-capacity", "Dung lượng pin", "2.4 kWh (Tùy chọn thêm 1 pin 2.4 kWh)"],
          ["battery-type", "Loại pin", "LFP"],
          ["battery-weight", "Trọng lượng pin", "18 kg"],
          ["charge-time", "Thời gian sạc tiêu chuẩn", "Khoảng 6h30 phút từ 0 - 100%"],
          ["standard-range", "Quãng đường đi được 1 lần sạc (Điều kiện tiêu chuẩn 30 km/h, 1 người nặng 65kg)", "Khoảng 134 km (+128 km khi lắp thêm pin phụ)"],
        ]),
      },
      {
        title: "Vận hành",
        items: specs([
          ["rated-power", "Công suất danh định", "1500 W"],
          ["maximum-power", "Công suất tối đa", "2250 W"],
          ["motor", "Loại động cơ", "BLDC Inhub"],
          ["speed", "Tốc độ tối đa (1 người 65 kg)", "70 km/h"],
          ["acceleration", "Gia tốc tăng tốc 0 - 50 km/h", "<15s (1 người 65 Kg)"],
        ]),
      },
    ],
  };
}

const evoGrand = productData["evo-grand"];
if (evoGrand) {
  productData["evo-grand"] = {
    ...evoGrand,
    motorcycleLayout: "evo-grand",
    hero: {
      src: "/media/vinfast/motorbikes/evo-grand/campaign-hero.webp",
      alt: "Chiến dịch VinFast Evo Grand",
      role: "hero",
    },
    tagline: "Vận hành bền bỉ, chinh phục mọi hành trình.",
    statement: "Thể tích cốp 35 lít tối ưu sức chứa, đáp ứng linh hoạt nhu cầu di chuyển mỗi ngày.",
    priceVnd: 22_500_000,
    priceNote: "Giá đã bao gồm VAT, 1 pin và 1 bộ sạc",
    brochureUrl: "https://storage.googleapis.com/vinfast-data-01/brochure/05022026/030226_Vinfast_EvoGrand_Brochure.pdf",
    metrics: [
      { label: "Tốc độ tối đa", value: "70 km/h*" },
      { label: "Quãng đường di chuyển", value: "262 km/1 lần sạc*" },
      { label: "Dung tích cốp xe", value: "35 lít" },
    ],
    specificationNotes: [
      "*Theo điều kiện kiểm thử của VinFast khi di chuyển 1 người 65 kg với tốc độ 30 km/h.",
    ],
    specificationGroups: [
      {
        title: "Vận hành",
        items: specs([
          ["colors", "Màu sắc", "Trắng ngọc trai, Đen nhám, Xanh Oliu, Đỏ tươi, Vàng cát"],
          ["charge-time", "Thời gian sạc tiêu chuẩn", "Khoảng 6 giờ 30 phút (từ 0 đến 100%)"],
          ["motor", "Động cơ", "Inhub"],
          ["power", "Công suất", "2250W"],
        ]),
      },
      {
        title: "Khung xe & pin",
        items: specs([
          ["suspension", "Giảm xóc trước và sau", "Ống lồng-giảm chấn thủy lực; giảm xóc đôi, giảm chấn thủy lực"],
          ["battery-position", "Vị trí lắp pin", "Pin chính đặt dưới sàn để chân, pin phụ đặt ở cốp"],
          ["battery-type", "Loại Pin", "Pin LFP"],
          ["speed", "Tốc độ tối đa (1 người 65kg)", "70 km/h"],
        ]),
      },
      {
        title: "Kích thước & trang bị",
        items: specs([
          ["range", "Quãng đường đi được 1 lần sạc*", "Khoảng 134 km (+128 Km khi lắp thêm pin phụ)"],
          ["weight", "Trọng lượng xe và pin", "Khoảng 92 kg (110Kg khi lắp thêm pin phụ)"],
          ["ground-clearance", "Khoảng sáng gầm xe", "133 mm"],
          ["brakes", "Phanh trước và sau", "Phanh đĩa/ Cơ"],
        ]),
      },
    ],
  };
}

const kinet = productData.kinet;
if (kinet) {
  productData.kinet = {
    ...kinet,
    heroEyebrow: "Bật chất thể thao",
    storyLayout: "details-first",
    tagline: "Đánh thức đam mê – làm chủ mọi cung đường.",
    statement: "Đánh thức đam mê – làm chủ mọi cung đường.",
    priceVnd: 49_900_000,
    priceNote: "Giá xe không kèm pin: 40.000.000 ₫ · Đã bao gồm VAT, 01 bộ sạc.",
    hero: {
      src: `${mediaRoot}/motorbikes/kinet/color-cement-grey.webp`,
      alt: "VinFast Kinet màu Xám xi măng",
      role: "hero",
    },
    metrics: [
      { label: "Tốc độ tối đa", value: "~90 km/h" },
      { label: "Quãng đường di chuyển", value: "~145 km/1 lần sạc" },
      { label: "Công suất tối đa", value: "~5.200 W" },
    ],
    gallery: [
      {
        src: `${mediaRoot}/motorbikes/kinet/feature-battery.webp`,
        alt: "VinFast Kinet với công nghệ pin LFP",
        role: "battery",
        title: "Công nghệ pin tiên tiến.",
        description: "Hai pin LFP chạy song song, duy trì khả năng vận hành ổn định và an toàn hơn.",
      },
      {
        src: `${mediaRoot}/motorbikes/kinet/feature-display.webp`,
        alt: "Màn hình TFT VinFast Kinet",
        role: "technology",
        title: "Màn hình TFT kết nối Bluetooth.",
      },
      {
        src: `${mediaRoot}/motorbikes/kinet/feature-storage.webp`,
        alt: "Cốp 22 lít VinFast Kinet",
        role: "detail",
        title: "Cốp xe rộng 22 lít.",
      },
      {
        src: `${mediaRoot}/motorbikes/kinet/feature-suspension.webp`,
        alt: "Bánh trước và giảm xóc VinFast Kinet",
        role: "safety",
        title: "Giảm chấn thủy lực êm ái.",
      },
      {
        src: `${mediaRoot}/motorbikes/kinet/feature-brake.webp`,
        alt: "Bánh sau và hệ thống phanh VinFast Kinet",
        role: "safety",
        title: "Hỗ trợ khởi hành ngang dốc.",
      },
    ],
    specificationGroups: [{
      title: "Thông số chính",
      items: specs([
        ["colors", "Màu sắc", "Xám xi măng; Đen bóng; Đỏ đen; Trắng ngọc trai; Nâu ánh kim"],
        ["wheelbase", "Khoảng cách trục bánh", "1.360 mm"],
        ["storage", "Thể tích cốp", "22 lít"],
        ["dimensions", "Dài x Rộng x Cao", "2.021 x 713 x 1.135 mm"],
        ["ground-clearance", "Khoảng sáng gầm", "160 mm"],
        ["seat-height", "Chiều cao yên", "785 mm"],
        ["battery", "Dung lượng pin", "2 x 1,5 kWh"],
        ["charge", "Thời gian sạc tiêu chuẩn", "Khoảng 9 giờ"],
        ["power", "Công suất tối đa", "~5.200 W"],
        ["speed", "Tốc độ tối đa", "90 km/h"],
      ]),
    }],
  };
}

const motorbikeColorSets: Readonly<Record<string, Array<Readonly<[string, string, string]>>>> = {
  "vero-x": [["color-green.webp", "Xanh ô liu", "#a8af9d"], ["color-black.webp", "Đen nhám", "#17191b"], ["color-blue.webp", "Xanh rêu", "#173f34"], ["color-white.webp", "Trắng ngọc trai", "#efeee7"]],
  kinet: [["color-cement-grey.webp", "Xám xi măng", "#6f7774"], ["color-black-gloss.webp", "Đen bóng", "#17191b"], ["color-red-black.webp", "Đỏ đen", "#9f202b"], ["color-white-pearl.webp", "Trắng ngọc trai", "#efeee7"], ["color-metallic-brown.webp", "Nâu ánh kim", "#66564a"]],
  "feliz-2025": [["color-green.webp", "Xanh ô liu", "#6d775c"], ["color-black.webp", "Đen bóng", "#17191b"], ["color-white.webp", "Trắng ngọc trai", "#efeee7"], ["color-light-green.webp", "Xanh mint", "#a8c4af"]],
  flazz: [["color-red.webp", "Đỏ", "#9f202b"], ["color-black.webp", "Đen", "#17191b"], ["color-blue.webp", "Xanh dương", "#315f8c"], ["color-white.webp", "Trắng", "#efeee7"]],
  zgoo: [["color-red.webp", "Đỏ", "#a31d2a"], ["color-black.webp", "Đen", "#17191b"], ["color-white.webp", "Trắng", "#efeee7"], ["color-green.webp", "Xanh lá", "#7b8960"]],
  "evo-lite-neo": [["color-red.webp", "Đỏ", "#a31d2a"], ["color-blue.webp", "Xanh dương", "#315f8c"], ["color-black.webp", "Đen", "#17191b"], ["color-white.webp", "Trắng", "#efeee7"], ["color-green.webp", "Xanh rêu", "#6d775c"]],
  "evo-grand": [["color-1.webp", "Đen nhám", "#17191b"], ["color-2.webp", "Đỏ tươi", "#a31d2a"], ["color-3.webp", "Trắng ngọc trai", "#efeee7"], ["color-4.webp", "Vàng cát", "#b6a26c"], ["color-5.webp", "Xanh ô liu", "#89968a"]],
  "evo-grand-lite": [["color-1.webp", "Đỏ", "#a31d2a"], ["color-2.webp", "Trắng", "#efeee7"], ["color-3.webp", "Đen", "#17191b"], ["color-4.webp", "Xanh", "#526d73"]],
};

for (const [slug, colors] of Object.entries(motorbikeColorSets)) {
  const product = productData[slug];
  if (!product) continue;
  const stories = product.gallery.filter((media) => media.role !== "color");
  product.gallery = [...colors.map(([filename, label, swatch]) => ({
    src: `${mediaRoot}/motorbikes/${slug}/${filename}`,
    alt: `VinFast ${product.model} màu ${label}`,
    role: "color" as const,
    label,
    swatch,
  })), ...stories];
}

/** Return locally authored product content; customer pages never call `/api/vehicles`. */
export function getProductExperience(slug: string): ProductExperienceData | null {
  return productData[slug] ?? null;
}

export const homeProducts = ["vf-2", "vf-3", "vf-5", "vf-6", "vf-7", "vf-8", "vf-9"]
  .map((slug) => productData[slug])
  .filter((product): product is ProductExperienceData => product !== undefined);

export const localCatalogVehicles: LocalCatalogVehicle[] = Object.values(productData).map((product) => {
  const rangeMetric = product.metrics.find((metric) => metric.label.startsWith("Quãng đường"))?.value;
  const rangeMatch = rangeMetric?.match(/\d+/);
  const rangeKm = rangeMatch ? Number.parseInt(rangeMatch[0], 10) : null;
  const seatMetric = product.metrics.find((metric) => metric.label === "Cấu hình ghế")?.value;
  const seats = seatMetric && /^\d+/.test(seatMetric) ? Number.parseInt(seatMetric, 10) : null;
  return {
    id: product.slug,
    modelName: product.model,
    vehicleType: product.category === "car" ? "car" : "electric_motorbike",
    priceVnd: product.priceVnd,
    rangeKm,
    seats,
    chargeMinutes: null,
    batteryCapacityKwh: null,
    imageUrl: product.hero.src,
    href: product.category === "car" ? `/vehicles/${product.slug}` : `/motorbikes/${product.slug}`,
    quickSpecs: quickSpecsOf(product),
  };
});
