import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: "http://localhost:8000/api/v1/:path*",
      },
    ];
  },
  images: {
    // Ảnh xe đến từ các trang nguồn được thu thập dữ liệu (catalog thật, không
    // phải mock). Danh sách hostname khớp `image_url` hiện có trong Postgres.
    remotePatterns: [
      { protocol: "https", hostname: "vinfastvietnam.com.vn" },
      { protocol: "https", hostname: "xedienvietthanh.com" },
      { protocol: "https", hostname: "ev-database.org" },
      { protocol: "https", hostname: "static-cms-prod.vinfastauto.com" },
      { protocol: "https", hostname: "shop.vinfastauto.com" },
      // Mười xe trong catalog dùng link Google Drive; `VehicleImage` đổi chúng
      // sang dạng phục vụ ảnh trực tiếp của Drive, và đó là host này.
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
    ],
    // BẮT BUỘC khai báo (Next 16): `/_next/image` từ chối mọi `q` không nằm
    // trong danh sách này bằng 400 `"q" parameter (quality) of 90 is not
    // allowed`. `VehicleImage` truyền `quality={90}`, nên thiếu dòng này thì
    // MỌI ảnh xe đi qua component đó đều hỏng — trên mọi màn, không riêng
    // đoạn chat (Sếp báo 2026-08-25 "ảnh trong đoạn chat không hiện").
    //
    // Giữ cả 75 vì đó là mặc định của Next, dùng ở những chỗ không truyền `quality`.
    qualities: [75, 90],
  },
};

export default nextConfig;
