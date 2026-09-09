export type HomepageMetric = Readonly<{
  label: string;
  value: string;
}>;

export type HomepageVehicle = Readonly<{
  name: string;
  image: string;
  href: string;
  primaryLabel: "ĐẶT CỌC" | "MUA XE";
  metrics: readonly HomepageMetric[];
  originalPrice?: string;
}>;

export type HomepageAccessory = Readonly<{
  name: string;
  price: string;
  image: string;
  href: string;
}>;

export const homepageCars: readonly HomepageVehicle[] = [
  { name: "VF 2", image: "/media/vinfast/home/vf2.webp", href: "/vehicles/vf-2", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "MiniCar" }, { label: "Số chỗ ngồi", value: "4 chỗ" }, { label: "Quãng đường", value: "210 km (NEDC)" }, { label: "Giá bán từ", value: "178.600.000 VNĐ*" }], originalPrice: "188.000.000 VNĐ" },
  { name: "VF 8 All New", image: "/media/vinfast/home/vf8-all-new.webp", href: "/vehicles/vf-8-all-new", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "D-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "480-500 km" }, { label: "Giá bán từ", value: "854.050.000 VNĐ*" }], originalPrice: "899.000.000 VNĐ" },
  { name: "VF MPV 7", image: "/media/vinfast/home/mpv7.webp", href: "/vehicles/vf-mpv-7", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "MPV" }, { label: "Số chỗ ngồi", value: "7 chỗ" }, { label: "Quãng đường lên tới", value: "450 km (NEDC)" }, { label: "Giá bán từ", value: "712.500.000 VNĐ*" }], originalPrice: "750.000.000 VNĐ" },
  { name: "EC VAN", image: "/media/vinfast/home/ecvan.webp", href: "/vehicles", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "VAN" }, { label: "Số chỗ ngồi", value: "2 chỗ" }, { label: "Quãng đường lên tới", value: "175 km (NEDC)" }, { label: "Giá bán từ", value: "254.600.000 VNĐ*" }], originalPrice: "268.000.000 VNĐ" },
  { name: "Minio Green", image: "/media/vinfast/home/minio-green.webp", href: "/vehicles", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "MiniCar" }, { label: "Số chỗ ngồi", value: "4 chỗ" }, { label: "Quãng đường lên tới", value: "210 km (NEDC)" }, { label: "Giá bán từ", value: "178.600.000 VNĐ*" }], originalPrice: "188.000.000 VNĐ" },
  { name: "Herio Green", image: "/media/vinfast/home/herio-green.webp", href: "/vehicles", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "A-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "326 km (NEDC)" }, { label: "Giá bán từ", value: "427.500.000 VNĐ*" }], originalPrice: "450.000.000 VNĐ" },
  { name: "Nerio Green", image: "/media/vinfast/home/nerio-green.webp", href: "/vehicles", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "B-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "318,6 km (NEDC)" }, { label: "Giá từ", value: "668.000.000 VNĐ" }] },
  { name: "Limo Green", image: "/media/vinfast/home/limo-green.webp", href: "/vehicles", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "MPV" }, { label: "Số chỗ ngồi", value: "7 chỗ" }, { label: "Quãng đường lên tới", value: "450 km (NEDC)" }, { label: "Giá bán từ", value: "664.050.000 VNĐ*" }], originalPrice: "699.000.000 VNĐ" },
  { name: "VF 3", image: "/media/vinfast/home/vf3.webp", href: "/vehicles/vf-3", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "MiniCar" }, { label: "Số chỗ ngồi", value: "4 chỗ" }, { label: "Quãng đường lên tới", value: "210 km (NEDC)" }, { label: "Giá bán từ", value: "270.750.000 VNĐ*" }], originalPrice: "285.000.000 VNĐ" },
  { name: "VF 5", image: "/media/vinfast/home/vf5.webp", href: "/vehicles/vf-5", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "A-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "326,4 km (NEDC)" }, { label: "Giá bán từ", value: "471.200.000 VNĐ*" }], originalPrice: "496.000.000 VNĐ" },
  { name: "VF 6", image: "/media/vinfast/home/vf6.webp", href: "/vehicles/vf-6", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "B-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "485 km (NEDC)" }, { label: "Giá bán từ", value: "613.700.000 VNĐ*" }], originalPrice: "646.000.000 VNĐ" },
  { name: "VF 7", image: "/media/vinfast/home/vf7.webp", href: "/vehicles/vf-7", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "C-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "500,5 km (NEDC)" }, { label: "Giá bán từ", value: "703.000.000 VNĐ*" }], originalPrice: "740.000.000 VNĐ" },
  { name: "VF 8", image: "/media/vinfast/home/vf8.webp", href: "/vehicles/vf-8", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "D-SUV" }, { label: "Số chỗ ngồi", value: "5 chỗ" }, { label: "Quãng đường lên tới", value: "562 km (NEDC)" }, { label: "Giá bán từ", value: "853.100.000 VNĐ*" }], originalPrice: "898.000.000 VNĐ" },
  { name: "VF 9", image: "/media/vinfast/home/vf9.webp", href: "/vehicles/vf-9", primaryLabel: "ĐẶT CỌC", metrics: [{ label: "Dòng xe", value: "E-SUV" }, { label: "Số chỗ ngồi", value: "6-7 chỗ" }, { label: "Quãng đường lên tới", value: "626 km" }, { label: "Giá bán từ", value: "1.280.600.000 VNĐ*" }], originalPrice: "1.348.000.000 VNĐ" },
];

export const homepageMotorbikes: readonly HomepageVehicle[] = [
  { name: "KYO", image: "/media/vinfast/home/kyo.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~160 km/lần sạc" }, { label: "Công suất tối đa", value: "3000 W" }, { label: "Giá từ", value: "30.000.000 VNĐ" }] },
  { name: "KINET", image: "/media/vinfast/home/kinet.webp", href: "/motorbikes/kinet", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "90 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~145 km/lần sạc" }, { label: "Công suất tối đa", value: "5200 W" }, { label: "Giá từ", value: "40.000.000 VNĐ" }] },
  { name: "AMIO S2", image: "/media/vinfast/home/amio-s2.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "25 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~65 km/lần sạc" }, { label: "Công suất tối đa", value: "800 W" }, { label: "Giá từ", value: "12.000.000 VNĐ" }] },
  { name: "FLAZZ MAX", image: "/media/vinfast/home/flazz-max.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "49 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~87 km/lần sạc" }, { label: "Công suất tối đa", value: "1500 W" }, { label: "Giá từ", value: "12.500.000 VNĐ" }] },
  { name: "AMIO S", image: "/media/vinfast/home/amio-s.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "25 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~65 km/lần sạc" }, { label: "Công suất tối đa", value: "800 W" }, { label: "Giá từ", value: "11.600.000 VNĐ" }] },
  { name: "EVO Lite", image: "/media/vinfast/home/evo-lite.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "49 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~165 km/lần sạc" }, { label: "Công suất tối đa", value: "2300 W" }, { label: "Giá từ", value: "14.300.000 VNĐ" }] },
  { name: "AMIO", image: "/media/vinfast/home/amio.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "30 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~65 km/lần sạc" }, { label: "Công suất tối đa", value: "800 W" }, { label: "Giá từ", value: "11.600.000 VNĐ" }] },
  { name: "VIPER", image: "/media/vinfast/home/viper.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~156 km/lần sạc" }, { label: "Công suất tối đa", value: "3000 W" }, { label: "Giá từ", value: "35.000.000 VNĐ" }] },
  { name: "FELIZ II", image: "/media/vinfast/home/feliz-ii.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường 1 lần sạc", value: "~156 km/lần sạc" }, { label: "Công suất tối đa", value: "3000 W" }, { label: "Giá từ", value: "23.000.000 VNĐ" }] },
  { name: "EVO", image: "/media/vinfast/home/evo.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường 1 lần sạc (2 pin)", value: "~165 km/lần sạc" }, { label: "Cốp xe", value: "12 lít" }, { label: "Giá từ", value: "18.800.000 VNĐ" }] },
  { name: "ZGoo", image: "/media/vinfast/home/zgoo.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "39 km/h" }, { label: "Quãng đường 1 lần sạc", value: "70 km" }, { label: "Cốp xe", value: "14 lít" }, { label: "Giá từ", value: "13.300.000 VNĐ" }] },
  { name: "FLAZZ", image: "/media/vinfast/home/flazz.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "39 km/h" }, { label: "Quãng đường đi được 1 lần sạc (2 pin)", value: "135 km" }, { label: "Cốp xe", value: "14 lít" }, { label: "Giá từ", value: "14.200.000 VNĐ" }] },
  { name: "VERO X", image: "/media/vinfast/home/vero-x.webp", href: "/motorbikes/vero-x", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường đi được 1 lần sạc (2 pin)", value: "262 km" }, { label: "Cốp xe", value: "35 lít" }, { label: "Giá từ", value: "34.900.000 VNĐ" }] },
  { name: "FELIZ 2025", image: "/media/vinfast/home/feliz-2025.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường đi được 1 lần sạc (2 pin)", value: "262 km" }, { label: "Cốp xe", value: "34 lít" }, { label: "Giá từ", value: "26.000.000 VNĐ" }] },
  { name: "EVO GRAND", image: "/media/vinfast/home/evo-grand.webp", href: "/motorbikes/evo-grand", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "70 km/h" }, { label: "Quãng đường đi được 1 lần sạc (2 pin)", value: "262 km" }, { label: "Cốp xe", value: "35 lít" }, { label: "Giá từ", value: "22.500.000 VNĐ" }] },
  { name: "EVO GRAND LITE", image: "/media/vinfast/home/evo-grand-lite.webp", href: "/motorbikes/evo-grand-lite", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "48 km/h" }, { label: "Quãng đường đi được 1 lần sạc (2 pin)", value: "198 km" }, { label: "Cốp xe", value: "35 lít" }, { label: "Giá từ", value: "16.500.000 VNĐ" }] },
  { name: "DRGNFLY", image: "/media/vinfast/home/drgnfly.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Công suất động cơ", value: "250 W" }, { label: "Quãng đường 1 lần sạc", value: "110 km" }, { label: "Pin Lithium Ion", value: "47,2V" }, { label: "Giá từ", value: "18.690.000 VNĐ" }] },
  { name: "EVO LITE NEO", image: "/media/vinfast/home/evo-lite-neo.webp", href: "/motorbikes", primaryLabel: "MUA XE", metrics: [{ label: "Tốc độ tối đa", value: "49 km/h" }, { label: "Quãng đường 1 lần sạc", value: "78 km" }, { label: "Cốp xe", value: "17 lít" }, { label: "Giá từ", value: "14.400.000 VNĐ" }] },
];

export const homepageAccessories: readonly HomepageAccessory[] = [
  { name: "Mô Hình Xe VinFast VF 3", price: "2.074.000 VNĐ", image: "/media/vinfast/home/accessory-vf3-model.webp", href: "/accessories" },
  { name: "Bộ Sạc Treo Tường AC 11 kW", price: "11.781.818 VNĐ", image: "/media/vinfast/home/accessory-wall-charger.webp", href: "/accessories" },
  { name: "VF 7 Tấm Che Pin Cao Áp", price: "6.881.000 VNĐ", image: "/media/vinfast/home/accessory-vf7-battery-cover.webp", href: "/accessories" },
  { name: "Ô Golf 2 Tầng", price: "404.000 VNĐ", image: "/media/vinfast/home/accessory-golf-umbrella.webp", href: "/accessories" },
];
