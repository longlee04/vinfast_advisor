"use client";

import { ImageOff } from "lucide-react";
import Image from "next/image";
import { useState } from "react";

/**
 * Link Google Drive dạng "xem" → URL ẢNH THẬT.
 *
 * Catalog có `image_url` ở HAI dạng link xem: `drive.google.com/file/d/<id>/view`
 * (CSV seed) và `drive.google.com/uc?export=view&id=<id>` (bản ghi cũ đã seed
 * trong Postgres prod từ trước khi CSV đổi dạng). Cả hai đều trả về một TRANG
 * HTML, nên `<img>` không bao giờ hiện được — Sếp báo 2026-08-25 "ảnh trong
 * đoạn chat đang không hiện" và 2026-08-26 "case tư vấn đề xuất ảnh không lên"
 * (DB prod vẫn còn toàn bộ dạng `uc`). `lh3.googleusercontent.com/d/<id>` là
 * dạng phục vụ ảnh trực tiếp của cùng file đó, dùng cho cả hai.
 *
 * Sửa ở tầng hiển thị chứ không sửa dữ liệu: mọi mặt khách nhìn thấy đều đi qua
 * component này, còn sửa CSV/DB thì phải seed lại prod. Dọn dữ liệu vẫn nên làm,
 * nhưng không nên là điều kiện để ảnh hiện được.
 */
const DRIVE_VIEW = /^https:\/\/drive\.google\.com\/file\/d\/([^/?#]+)/;
const DRIVE_UC_VIEW = /^https:\/\/drive\.google\.com\/uc\?.*?[?&]id=([^&#]+)/;

export function toDirectImageUrl(src: string | null | undefined): string | null | undefined {
  if (!src) return src;
  const view = DRIVE_VIEW.exec(src);
  if (view) return `https://lh3.googleusercontent.com/d/${view[1]}`;
  const ucView = DRIVE_UC_VIEW.exec(src);
  if (ucView) return `https://lh3.googleusercontent.com/d/${ucView[1]}`;
  return src;
}

export function VehicleImage({
  alt,
  className,
  preload = false,
  sizes,
  src,
}: Readonly<{
  alt: string;
  className?: string;
  preload?: boolean;
  sizes: string;
  src: string | null | undefined;
}>) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const resolved = toDirectImageUrl(src);
  const failed = Boolean(resolved && failedSrc === resolved);

  if (!resolved || failed) {
    const fallbackLabel = `Chưa tải được ${alt.charAt(0).toLocaleLowerCase("vi")}${alt.slice(1)}`;
    return (
      <div aria-label={fallbackLabel} className={`vehicle-image-fallback ${className ?? ""}`} role="img">
        <ImageOff aria-hidden="true" size={24} strokeWidth={1.5} />
        <span>Ảnh đang được cập nhật</span>
      </div>
    );
  }

  return (
    <div className={`vehicle-image-frame ${className ?? ""}`}>
      <Image
        alt={alt}
        fill
        loading={preload ? "eager" : undefined}
        onError={() => setFailedSrc(resolved)}
        priority={preload}
        quality={90}
        sizes={sizes}
        src={resolved}
      />
    </div>
  );
}
