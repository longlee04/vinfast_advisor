export type MotorbikeMenuCategoryId = "premium" | "mid-range" | "popular";

export type MotorbikeMenuItem = {
  id: string;
  name: string;
  href: string;
  imageUrl: string;
  detailImageUrl: string;
  catalogSlug: string;
};

export type MotorbikeMenuCategory = {
  id: MotorbikeMenuCategoryId;
  label: string;
  description: string;
  motorbikes: MotorbikeMenuItem[];
};

export type MotorbikeMenuEntry = MotorbikeMenuItem & {
  categoryId: MotorbikeMenuCategoryId;
  categoryLabel: string;
  categoryDescription: string;
};

const IMAGE_ROOT = "/vehicles/motorbikes";
const OFFICIAL_MENU_ROOT = "https://shop.vinfastauto.com/on/demandware.static/-/Sites-app_vinfast_vn-Library/default";
const MENU_IMAGES: Record<string, string> = {
  "vero-x": "dw3bf5d0be/images/mega-menu/scooter/VeroX.png",
  viper: "dw7111b9f7/images/mega-menu/scooter/Viper.png",
  kinet: "dw3f87e016/images/mega-menu/scooter/KINET.png",
  "feliz-2025": "dw1caba829/images/mega-menu/scooter/Feliz.png",
  "feliz-ii": "dw6d4141fa/images/mega-menu/scooter/FelizII.png",
  kyo: "dwa2eb461f/images/mega-menu/scooter/KYO.png",
  evo: "dw852bfc9b/images/mega-menu/scooter/Evo.png",
  "evo-lite": "dw89aa9ba7/images/mega-menu/scooter/EvoLite.png",
  "evo-grand": "dw221ac91e/images/mega-menu/scooter/Evo-Grand.png",
  "evo-grand-lite": "dw495647f7/images/mega-menu/scooter/Evo-Grand-Lite.png",
  "evo-lite-neo": "dw8b6d00c8/images/mega-menu/scooter/Evo-Lite-Neo.png",
  flazz: "dw7f58b193/images/mega-menu/scooter/Flazz.png",
  "flazz-max": "dwe90efb9b/images/mega-menu/scooter/Flazz-Max.png",
  zgoo: "dw567434db/images/mega-menu/scooter/ZGoo.png",
  amio: "dw6c8a3892/images/mega-menu/scooter/Amio.png",
  "amio-s": "dw488e79db/images/mega-menu/scooter/Amio-S.png",
  "amio-s2": "dw3c53a8c3/images/mega-menu/scooter/Amio-S2.png",
  "vf-drgnfly-ebike": "dwd68b325a/images/mega-menu/scooter/Drgnfly.png",
};

const motorbikeCategoriesWithDetailImages = [
  {
    id: "premium",
    label: "Cao cấp",
    description: "Dòng xe máy điện cao cấp với thiết kế nổi bật, khả năng vận hành mạnh mẽ và trang bị hiện đại.",
    motorbikes: [
      {
        id: "vero-x",
        name: "Vero X",
        href: "/motorbikes/vero-x",
        imageUrl: `${IMAGE_ROOT}/vero-x.webp`,
        catalogSlug: "vinfast-vero-x",
      },
      {
        id: "viper",
        name: "Viper",
        href: "/motorbikes/viper",
        imageUrl: `${IMAGE_ROOT}/viper.webp`,
        catalogSlug: "vinfast-viper-thuê-pin",
      },
      {
        id: "kinet",
        name: "Kinet",
        href: "/motorbikes/kinet",
        imageUrl: `${IMAGE_ROOT}/kinet.webp`,
        catalogSlug: "vinfast-kinet-thuê-pin",
      },
    ],
  },
  {
    id: "mid-range",
    label: "Trung cấp",
    description: "Lựa chọn cân bằng giữa phong cách, tiện ích và hiệu quả cho nhu cầu di chuyển hằng ngày.",
    motorbikes: [
      {
        id: "feliz-2025",
        name: "Feliz 2025",
        href: "/motorbikes/feliz-2025",
        imageUrl: `${IMAGE_ROOT}/feliz-2025.webp`,
        catalogSlug: "vinfast-feliz",
      },
      {
        id: "feliz-ii",
        name: "Feliz II",
        href: "/motorbikes/feliz-ii",
        imageUrl: `${IMAGE_ROOT}/feliz-ii.webp`,
        catalogSlug: "vinfast-feliz-ii-thuê-pin",
      },
      {
        id: "kyo",
        name: "Kyo",
        href: "/motorbikes/kyo",
        imageUrl: `${IMAGE_ROOT}/kyo.webp`,
        catalogSlug: "vinfast-kyo-thuê-pin",
      },
    ],
  },
  {
    id: "popular",
    label: "Phổ thông",
    description: "Các mẫu xe điện dễ tiếp cận, linh hoạt và phù hợp với nhiều nhu cầu đi lại trong đô thị.",
    motorbikes: [
      {
        id: "evo",
        name: "Evo",
        href: "/motorbikes/evo",
        imageUrl: `${IMAGE_ROOT}/evo.webp`,
        catalogSlug: "vinfast-evo-thuê-pin",
      },
      {
        id: "evo-lite",
        name: "Evo Lite",
        href: "/motorbikes/evo-lite",
        imageUrl: `${IMAGE_ROOT}/evo-lite.png`,
        catalogSlug: "vinfast-evo-lite-kèm-pin",
      },
      {
        id: "evo-grand",
        name: "Evo Grand",
        href: "/motorbikes/evo-grand",
        imageUrl: `${IMAGE_ROOT}/evo-grand.webp`,
        catalogSlug: "vinfast-evo-grand-grand",
      },
      {
        id: "evo-grand-lite",
        name: "Evo Grand Lite",
        href: "/motorbikes/evo-grand-lite",
        imageUrl: `${IMAGE_ROOT}/evo-grand-lite.webp`,
        catalogSlug: "vinfast-evo-grand-lite-lite",
      },
      {
        id: "evo-lite-neo",
        name: "Evo Lite Neo",
        href: "/motorbikes/evo-lite-neo",
        imageUrl: `${IMAGE_ROOT}/evo-lite-neo.webp`,
        catalogSlug: "vinfast-evo-lite-neo-lite",
      },
      {
        id: "flazz",
        name: "Flazz",
        href: "/motorbikes/flazz",
        imageUrl: `${IMAGE_ROOT}/flazz.webp`,
        catalogSlug: "vinfast-flazz",
      },
      {
        id: "flazz-max",
        name: "Flazz Max",
        href: "/motorbikes/flazz-max",
        imageUrl: `${IMAGE_ROOT}/flazz-max.webp`,
        catalogSlug: "vinfast-flazz-max-thuê-pin",
      },
      {
        id: "zgoo",
        name: "ZGoo",
        href: "/motorbikes/zgoo",
        imageUrl: `${IMAGE_ROOT}/zgoo.webp`,
        catalogSlug: "vinfast-zgoo",
      },
      {
        id: "amio",
        name: "Amio",
        href: "/motorbikes/amio",
        imageUrl: `${IMAGE_ROOT}/amio.webp`,
        catalogSlug: "vinfast-amio",
      },
      {
        id: "amio-s",
        name: "Amio S",
        href: "/motorbikes/amio-s",
        imageUrl: `${IMAGE_ROOT}/amio-s.webp`,
        catalogSlug: "vinfast-amio-s-s",
      },
      {
        id: "amio-s2",
        name: "Amio S2",
        href: "/motorbikes/amio-s2",
        imageUrl: `${IMAGE_ROOT}/amio-s2.png`,
        catalogSlug: "vinfast-amio-s2-s",
      },
      {
        id: "vf-drgnfly-ebike",
        name: "VF DrgnFly eBike",
        href: "/motorbikes/vf-drgnfly-ebike",
        imageUrl: `${IMAGE_ROOT}/vf-drgnfly-ebike.png`,
        catalogSlug: "vinfast-drgnfly",
      },
    ],
  },
] satisfies Array<Omit<MotorbikeMenuCategory, "motorbikes"> & { motorbikes: Array<Omit<MotorbikeMenuItem, "detailImageUrl">> }>;

export const motorbikeMenuCategories: MotorbikeMenuCategory[] = motorbikeCategoriesWithDetailImages.map(
  (category) => ({
    ...category,
    motorbikes: category.motorbikes.map((motorbike) => ({
      ...motorbike,
      detailImageUrl: motorbike.imageUrl,
      imageUrl: `${OFFICIAL_MENU_ROOT}/${MENU_IMAGES[motorbike.id]}`,
    })),
  }),
);

export function getMotorbikeMenuEntry(motorbikeId: string): MotorbikeMenuEntry | undefined {
  for (const category of motorbikeMenuCategories) {
    const motorbike = category.motorbikes.find((item) => item.id === motorbikeId);
    if (motorbike) {
      return {
        ...motorbike,
        categoryId: category.id,
        categoryLabel: category.label,
        categoryDescription: category.description,
      };
    }
  }
  return undefined;
}
