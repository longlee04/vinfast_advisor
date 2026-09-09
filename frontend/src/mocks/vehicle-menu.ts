export type VehicleMenuCategoryId = "electric" | "gasoline" | "service";

export type VehicleMenuItem = {
  id: string;
  name: string;
  href: string;
  imageUrl: string;
  catalogSlug?: string;
};

export type VehicleMenuCategory = {
  id: VehicleMenuCategoryId;
  label: string;
  vehicles: VehicleMenuItem[];
};

export type VehicleMenuEntry = VehicleMenuItem & {
  categoryId: VehicleMenuCategoryId;
  categoryLabel: string;
};

export const vehicleMenuCategories: VehicleMenuCategory[] = [
  {
    id: "electric",
    label: "Động cơ điện",
    vehicles: [
      {
        id: "vf-2",
        name: "VF 2",
        href: "/vehicles/vf-2",
        imageUrl: "https://static-cms-prod.vinfastauto.com/vf2_home_page.png",
        catalogSlug: "vinfast-vf-2-all-new",
      },
      {
        id: "vf-3",
        name: "VF 3",
        href: "/vehicles/vf-3",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF3.webp",
        catalogSlug: "vinfast-vf-3-all-new",
      },
      {
        id: "vf-5",
        name: "VF 5",
        href: "/vehicles/vf-5",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF5.webp",
        catalogSlug: "vinfast-vf-5-all-new",
      },
      {
        id: "vf-6",
        name: "VF 6",
        href: "/vehicles/vf-6",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF6.webp",
        catalogSlug: "vinfast-vf-6-plus",
      },
      {
        id: "vf-mpv-7",
        name: "VF MPV 7",
        href: "/vehicles/vf-mpv-7",
        imageUrl: "https://static-cms-prod.vinfastauto.com/pdp/vf_mpv_7/Homepage_MPV7.webp",
      },
      {
        id: "vf-7",
        name: "VF 7",
        href: "/vehicles/vf-7",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF7.webp",
        catalogSlug: "vinfast-vf-7-all-new",
      },
      {
        id: "vf-8",
        name: "VF 8",
        href: "/vehicles/vf-8",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF8.webp",
        catalogSlug: "vinfast-vf-8-eco-extended-range",
      },
      {
        id: "vf-8-all-new",
        name: "VF 8 The All New",
        href: "/vehicles/vf-8-all-new",
        imageUrl: "https://static-cms-prod.vinfastauto.com/vf8-all-new.png",
        catalogSlug: "vinfast-vf-8-all-new",
      },
      {
        id: "vf-9",
        name: "VF 9",
        href: "/vehicles/vf-9",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/VF9.webp",
        catalogSlug: "vinfast-vf-9-all-new",
      },
    ],
  },
  {
    id: "gasoline",
    label: "Động cơ xăng",
    vehicles: [
      {
        id: "fadil",
        name: "Fadil",
        href: "/vehicles/fadil",
        imageUrl: "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dw09a0985f/images/Fadil/Hinh-anh-Mua-xe-VinFast-Fadil-ban-nang-cao-tra-gop-mau-do-Red.png",
      },
      {
        id: "lux-a2",
        name: "LUX A2.0",
        href: "/vehicles/lux-a2",
        imageUrl: "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwc1a7c1f3/images/Lux-A/hinh-anh-gia-xe-VinFast-Lux-A2.0-ban-tieu-chuan-mau-do-mystique-red.png",
      },
      {
        id: "lux-sa2",
        name: "LUX SA2.0",
        href: "/vehicles/lux-sa2",
        imageUrl: "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dw5c1adf16/images/Lux-SA/hinh-anh-gia-VinFast-Lux-SA2.0-ban-tieu-chuan-base-tra-gop-mau-do-red.png",
      },
      {
        id: "president",
        name: "President",
        href: "/vehicles/president",
        imageUrl: "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dw7ed3c56b/images/President/hinh-anh-gia-VinFast-President-V8-mau-do-red.png",
      },
    ],
  },
  {
    id: "service",
    label: "Dòng xe dịch vụ",
    vehicles: [
      {
        id: "minio-green",
        name: "Minio Green",
        href: "/vehicles/minio-green",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/MinioGreen.webp",
      },
      {
        id: "herio-green",
        name: "Herio Green",
        href: "/vehicles/herio-green",
        imageUrl: "https://static-cms-prod.vinfastauto.com/he.png",
      },
      {
        id: "nerio-green",
        name: "Nerio Green",
        href: "/vehicles/nerio-green",
        imageUrl: "https://static-cms-prod.vinfastauto.com/statics/img/homepage-v2/car/NerioGreen.webp",
      },
      {
        id: "limo-green",
        name: "Limo Green",
        href: "/vehicles/limo-green",
        imageUrl: "https://static-cms-prod.vinfastauto.com/limo.png",
      },
      {
        id: "ec-van",
        name: "EC Van",
        href: "/vehicles/ec-van",
        imageUrl: "https://static-cms-prod.vinfastauto.com/ecvan-02.webp",
      },
      {
        id: "ebus",
        name: "EBus",
        href: "/vehicles/ebus",
        imageUrl: "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default/dwc94d860f/landingpage/vgreen/ebus/ebus-img-05-sp.webp",
      },
    ],
  },
];

export function getVehicleMenuEntry(vehicleId: string): VehicleMenuEntry | undefined {
  for (const category of vehicleMenuCategories) {
    const vehicle = category.vehicles.find((item) => item.id === vehicleId);
    if (vehicle) {
      return {
        ...vehicle,
        categoryId: category.id,
        categoryLabel: category.label,
      };
    }
  }
  return undefined;
}
